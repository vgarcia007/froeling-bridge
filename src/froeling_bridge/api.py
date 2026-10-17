"""Versioned local HTTP API. The physical controller is never opened here."""
from datetime import datetime
from importlib.resources import files
import json

from .errors import ReadOnlyViolation, ValidationError
from .messages import ParameterType
from .menu import visible_menu, demo_time_program_catalog
from .service import QueueBusy, ServiceStopped, public
from .storage import DatabaseUnavailable, ZONE
from . import __version__
from .recording import automatic_recording


def create_app(service):
    from flask import Flask, jsonify, request, render_template
    from werkzeug.exceptions import HTTPException
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16384
    if not hasattr(app, "json"):
        raise ImportError("Flask 3.1 service dependencies required")
    app.json.ensure_ascii = False
    prefix = "/api/v1"

    def response(value, status=200):
        return jsonify(public(value)), status

    def integer(name, default=None):
        value = request.args.get(name, default)
        try:
            if value is None:
                raise ValueError()
            return int(value)
        except (TypeError, ValueError):
            raise ValidationError(f"{name} must be an integer") from None

    def args_only(*names):
        if set(request.args) - set(names) or any(len(request.args.getlist(k)) != 1 for k in request.args):
            raise ValidationError("unknown or repeated query parameter")

    @app.after_request
    def headers(result):
        result.headers["X-Content-Type-Options"] = "nosniff"
        result.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.path.startswith(prefix):
            result.headers["Cache-Control"] = "no-store"
        return result

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.errorhandler(ReadOnlyViolation)
    def readonly(exc):
        return response(dict(error=dict(code="read_only", message=str(exc))), 403)

    @app.errorhandler(ValidationError)
    def invalid(exc):
        return response(dict(error=dict(code="validation_error", message=str(exc))), 400)

    @app.errorhandler(DatabaseUnavailable)
    def unavailable(exc):
        if service.mode in ("hardware-read", "hardware-live"):
            service.abort("database_unavailable")
        return response(dict(error=dict(code="database_unavailable", message="database operation failed")), 503)

    @app.errorhandler(QueueBusy)
    @app.errorhandler(ServiceStopped)
    def busy(exc):
        return response(dict(error=dict(code="service_busy", message="worker unavailable or queue full")), 503)

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return response(dict(error=dict(code=exc.name, message=exc.description)), exc.code)

    @app.errorhandler(Exception)
    def internal_error(exc):
        # Never expose driver errors, connection configuration or traceback data.
        return response(dict(error=dict(code="internal_error", message="request failed")), 500)

    @app.get(prefix + "/errors")
    def controller_errors():
        args_only("source", "limit", "offset")
        runtime = getattr(service, "runtime", None)
        if runtime is None:
            raise ValidationError("heating error memory requires standalone mode")
        return response(runtime.errors_view(request.args.get("source", "auto"),
                                            integer("limit", 100), integer("offset", 0)))

    @app.get(prefix + "/health")
    def health():
        return response(dict(mode=service.mode, version=__version__, hardware_verified=False,
                             read_connection_verified=service.read_connection_verified,
                             fatal_reason=service.fatal_reason,
                             controller_connection=service.runtime.client.status() if getattr(service, "runtime", None) else None,
                             startup_phase=service.runtime.phase if getattr(service, "runtime", None) else None,
                             capabilities=dict(controller_read=service.worker is not None, heating_write=service.can_write,
                                               sensor_configuration=getattr(service.repository, "configurable", False)),
                             worker="unavailable" if not service.worker else (
                                 "running" if service.worker.thread.is_alive() else "stopped"),
                             database_available=service.repository.available,
                             write_operations=sorted(getattr(service, "allowed_write_operations", ("write_parameter", "write_time_range"))) if service.can_write else [],
                             jobs_persistent=False, timezone="Europe/Berlin"))

    @app.get(prefix + "/runtime")
    def runtime_status():
        runtime = getattr(service, 'runtime', None)
        return response(runtime.status() if runtime else dict(phase='legacy-mode', history=None))

    @app.patch(prefix + "/sensors/<sensor_type>/<int:address>")
    def configure_sensor(sensor_type, address):
        if not getattr(service.repository, 'configurable', False):
            raise ReadOnlyViolation('sensor configuration is unavailable in this mode')
        args_only()
        row = service.repository.patch_sensor(sensor_type, address, request.get_json())
        return response(dict(item=row))

    def latest_values():
        rows = service.cached_values()
        failures = {(e.get('address'), e.get('type')) for e in service.collector_status()['errors']}
        now = datetime.now(ZONE)
        for row in rows:
            row['age_seconds'] = max(0, (now - datetime.fromisoformat(row['observed_at'])).total_seconds())
            row['origin'] = row.get('origin', 'controller')
            interval = 10 if service.mode in ('standalone', 'standalone-demo') and row['type'] == 'UD' and row['address'] in (1,2) else service.interval
            row['stale'] = row['age_seconds'] > interval * 2 or row['origin'] == 'local-persisted' or (row['address'], row['type']) in failures
            if getattr(service, 'runtime', None) and not service.runtime.client.status()['connected']:
                row['stale'] = True
        return rows

    @app.get(prefix + "/collector")
    def collector():
        return response(service.collector_status())

    @app.get(prefix + "/menu")
    def menu():
        args_only("parent")
        parent = integer("parent", 1)
        if not 0 <= parent <= 65535:
            raise ValidationError("invalid menu parent")
        items = visible_menu(service.repository.menu(parent))
        for item in items:
            item["editable"] = service.can_write and "write_parameter" in getattr(service, "allowed_write_operations", ("write_parameter", "write_time_range")) and item["type"] in set(ParameterType)
        return response(dict(source=service.repository.source, parent=parent, items=items,
                             cached=True, timezone="Europe/Berlin"))

    @app.get(prefix + "/menu/search")
    def search_menu():
        args_only("q")
        query = request.args.get("q", "").strip()
        if not 1 <= len(query) <= 100:
            raise ValidationError("search query must contain 1..100 characters")
        items = visible_menu(service.repository.search_menu(query))
        for item in items:
            item["editable"] = service.can_write and "write_parameter" in getattr(service, "allowed_write_operations", ("write_parameter", "write_time_range")) and item["type"] in set(ParameterType)
        return response(dict(source=service.repository.source, items=items))

    @app.get(prefix + "/time-programs")
    def time_programs():
        args_only()
        programs = service.repository.time_programs()
        if not programs and service.mode in ("demo", "demo-db"):
            programs = demo_time_program_catalog()
        return response(dict(source=service.repository.source, programs=programs,
                             cache=service.time_program_cache()))

    @app.get(prefix + "/sensors")
    def sensors():
        args_only()
        from .local_store import supported
        latest = {(row['type'],row['address']): row for row in latest_values()}
        items = [dict(row, supported=supported(row), active=row['state']=='A', recording=row['record']=='A' or automatic_recording(row, service.mode),
                      configured_recording=row['record']=='A', recording_required=automatic_recording(row, service.mode),
                      latest=latest.get((row['type'],row['address']))) for row in service.repository.sensors()]
        return response(dict(source=service.repository.source, items=items))

    @app.get(prefix + "/values")
    def values():
        args_only()
        if service.mode == "database":
            return response(dict(error=dict(code="controller_unavailable", message="use history for stored database values")), 409)
        rows = latest_values()
        return response(dict(source=service.source, items=rows))

    @app.get(prefix + "/history")
    def history():
        args_only("address", "type", "start", "end", "aggregate", "limit")
        try:
            start = datetime.fromisoformat(request.args["start"])
            end = datetime.fromisoformat(request.args["end"])
        except (KeyError, ValueError):
            raise ValidationError("start/end must be ISO local timestamps") from None
        rows = service.repository.history(integer("address"), request.args.get("type"), start, end,
                                          request.args.get("aggregate", "S"), integer("limit", 1000))
        return response(dict(source=service.repository.source, timezone="Europe/Berlin", items=rows))

    @app.post(prefix + "/jobs")
    def submit_job():
        if service.mode == "database":
            return response(dict(error=dict(code="controller_unavailable", message="database mode is read-only")), 409)
        data = request.get_json()
        identifier = service.submit_job(data)
        result, code = response(dict(id=identifier, url=prefix + "/jobs/" + identifier), 202)
        result.headers["Location"] = prefix + "/jobs/" + identifier
        return result, code

    @app.get(prefix + "/jobs/<identifier>")
    def job(identifier):
        item = service.get_job(identifier)
        if item is None:
            return response(dict(error=dict(code="not_found", message="job absent or expired")), 404)
        return response(item)

    @app.get(prefix + "/openapi.json")
    def openapi():
        return response(json.loads(files("froeling_bridge").joinpath("openapi.json").read_text(encoding="utf-8")))

    return app
