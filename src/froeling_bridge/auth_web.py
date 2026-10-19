"""HTTP authentication and deny-by-default operation authorization."""
import hmac
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from .auth import AuthStore, AuthUnavailable, Throttled, COOKIE, READ_JOBS, WRITE_JOBS
from .errors import ReadOnlyViolation, ValidationError


class WebAuth:
    def __init__(self, app, service, enabled):
        from flask import g, request, jsonify, redirect, render_template, make_response
        from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
        self.enabled = enabled
        self.store = None
        self.origin = (getattr(service, "auth_config", None) or {}).get("public_origin", "")
        signer = URLSafeTimedSerializer(secrets.token_bytes(32), salt="login-csrf")
        if enabled:
            origin = urlsplit(self.origin)
            valid_origin = origin.scheme == "https" and origin.hostname and not origin.username and not origin.password and not origin.query and not origin.fragment and origin.path in ("", "/")
            self.origin = self.origin.rstrip("/") if valid_origin else ""
            if self.origin:
                app.config["TRUSTED_HOSTS"] = [origin.hostname, "127.0.0.1", "localhost", "[::1]"]
            state = getattr(service, "auth_state_dir", None)
            if not state and hasattr(service.repository, "path"):
                state = Path(service.repository.path).parent
            if state:
                try:
                    self.store = AuthStore(Path(state) / "auth.sqlite3")
                except (AuthUnavailable, OSError, ValidationError):
                    pass  # HTTP fails closed; the independent collector stays alive.
            service.auth_store = self.store
            service.authentication_required = True

        def error(code, message, status):
            result = jsonify(error=dict(code=code, message=message))
            result.status_code = status
            if status == 401:
                result.headers["WWW-Authenticate"] = "Bearer"
            if status == 429:
                result.headers["Retry-After"] = "60"
            return result

        def require_store():
            if not self.store or not self.origin:
                raise AuthUnavailable()
            return self.store

        def login_page(message=None, status=200):
            nonce = secrets.token_urlsafe(32)
            result = make_response(render_template("login.html", csrf=signer.dumps(nonce), message=message), status)
            result.set_cookie("__Host-froeling_login", nonce, secure=True, httponly=True,
                              samesite="Strict", path="/", max_age=600)
            return result

        @app.errorhandler(AuthUnavailable)
        def unavailable(exc):
            return error("authentication_unavailable", "Anmeldung vorübergehend nicht verfügbar.", 503)

        @app.errorhandler(Throttled)
        def limited(exc):
            result = error("rate_limited", "Zu viele Anfragen. Bitte später erneut versuchen.", 429)
            result.headers['Retry-After'] = str(exc.retry_after)
            return result

        @app.before_request
        def authenticate():
            g.actor = None
            if not enabled:
                return None
            if request.path == "/healthz" or request.path.startswith("/static/"):
                return None
            store = require_store()
            # Forwarded scheme is accepted by Waitress only from the configured peer.
            if not request.is_secure and request.remote_addr not in ("127.0.0.1", "::1"):
                if request.method == "GET" and not request.path.startswith("/api/"):
                    return redirect(self.origin + "/login", code=303)
                return error("https_required", "HTTPS required.", 400)
            if request.path in ("/login", "/api/v1/auth/login"):
                return None
            authorization = request.headers.get("Authorization")
            if authorization is not None:
                # Never silently fall back to a cookie after a bad Bearer header.
                parts = authorization.split()
                if len(parts) != 2 or parts[0].lower() != "bearer":
                    return error("authentication_required", "Anmeldung erforderlich.", 401)
                actor = store.authenticate(parts[1], "key")
            else:
                actor = store.authenticate(request.cookies.get(COOKIE), "session")
            if actor is None:
                if request.method == "GET" and request.path in ("/", "/anlage"):
                    return redirect("/login", code=303)
                return error("authentication_required", "Anmeldung erforderlich.", 401)
            g.actor = actor
            store.limit("api:" + actor["kind"] + ":" + actor["id"], 300, 60)
            if request.method not in ("GET", "HEAD", "OPTIONS") and actor["kind"] == "session":
                if request.headers.get("Origin") != self.origin or not hmac.compare_digest(
                        request.headers.get("X-CSRF-Token", ""), actor["csrf"]):
                    return error("csrf_failed", "Anfrage nicht bestätigt. Bitte neu anmelden.", 403)
            if request.method == "PATCH" or request.path == "/api/v1/plant/activate":
                if actor["role"] != "write":
                    raise ReadOnlyViolation("write permission required")
                store.event("configuration_attempt", actor, request.path)
            if request.path == "/api/v1/jobs" and request.method == "POST":
                data = request.get_json()
                operation = data.get("operation") if isinstance(data, dict) else None
                if not isinstance(operation, str) or operation not in READ_JOBS | WRITE_JOBS:
                    raise ValidationError("unknown job operation")
                store.limit("jobs:" + str(actor["user_id"]), 120, 60)
                if operation in WRITE_JOBS:
                    store.assert_writer(actor)
            # No unclassified mutation routes can accidentally become public later.
            elif request.method not in ("GET", "HEAD", "OPTIONS") and not (
                    request.method == "PATCH" and request.path.startswith("/api/v1/sensors/")) and request.path not in (
                    "/api/v1/plant/activate", "/api/v1/auth/logout"):
                raise ReadOnlyViolation("operation is not authorized")
            return None

        @app.get("/healthz")
        def healthz():
            return jsonify(status="ok")

        @app.get("/login")
        def login_form():
            if not enabled:
                return redirect("/")
            require_store()
            if not request.is_secure:
                return redirect(self.origin + "/login", code=303)
            return login_page()

        @app.post("/api/v1/auth/login")
        def login():
            if not enabled:
                return error("authentication_unavailable", "Login is not used in this simulator.", 404)
            store = require_store()
            if not request.is_secure or request.headers.get("Origin") != self.origin:
                return error("csrf_failed", "HTTPS and same-origin login required.", 403)
            data = request.get_json() if request.is_json else request.form
            if not data or set(data) != {"username", "password", "csrf"}:
                raise ValidationError("login requires username, password and csrf")
            if any(not isinstance(data[k], str) for k in ("username", "password", "csrf")):
                raise ValidationError("login fields must be strings")
            try:
                nonce = signer.loads(data["csrf"], max_age=600)
                valid = isinstance(nonce, str) and hmac.compare_digest(nonce, request.cookies.get("__Host-froeling_login", ""))
            except (BadSignature, SignatureExpired, TypeError):
                valid = False
            if not valid:
                return error("csrf_failed", "Login expired. Please reload the login page.", 403)
            token = store.login(data["username"], data["password"], request.remote_addr or "unknown")
            if not token:
                return error("invalid_credentials", "Anmeldung fehlgeschlagen.", 401) if request.is_json else login_page("Anmeldung fehlgeschlagen.", 401)
            old = store.authenticate(request.cookies.get(COOKIE), "session")
            if old:
                store.logout(old)
            result = jsonify(authenticated=True) if request.is_json else redirect("/anlage", code=303)
            result.set_cookie(COOKIE, token, secure=True, httponly=True, samesite="Strict", path="/", max_age=43200)
            result.delete_cookie("__Host-froeling_login", secure=True, httponly=True, samesite="Strict", path="/")
            return result

        @app.get("/api/v1/auth/me")
        def me():
            actor = g.actor
            return jsonify(authenticated=bool(actor), username=actor["username"] if actor else None,
                           role=actor["role"] if actor else "write", csrf=actor.get("csrf") if actor else None)

        @app.post("/api/v1/auth/logout")
        def logout():
            if enabled and g.actor["kind"] != "session":
                raise ReadOnlyViolation("API keys are revoked on the console")
            if enabled:
                require_store().logout(g.actor)
            result = jsonify(logged_out=True)
            result.delete_cookie(COOKIE, secure=True, httponly=True, samesite="Strict", path="/")
            return result

    def writer(self):
        from flask import g
        return not self.enabled or (g.actor is not None and g.actor["role"] == "write")

    def actor(self):
        from flask import g
        return g.actor if self.enabled else None


def proxy_options(config):
    import ipaddress
    proxy = (config or {}).get("trusted_proxy")
    if not proxy:
        return {}
    try:
        ipaddress.ip_address(proxy)
    except ValueError:
        raise ValidationError("trusted_proxy must be one explicit IP address") from None
    return dict(trusted_proxy=proxy, trusted_proxy_count=1,
                trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto"},
                clear_untrusted_proxy_headers=True)
