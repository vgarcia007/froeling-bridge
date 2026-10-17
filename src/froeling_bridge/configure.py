"""Interactive/private-file configuration for the native installer; no SQL work here."""

import argparse
import getpass
import json
import os
import uuid
from pathlib import Path

from .errors import ValidationError


def choose_device():
    devices = sorted(Path("/dev/serial/by-id").glob("*"))
    if not devices:
        devices = sorted(Path("/dev").glob("ttyUSB*"))
    if len(devices) == 1:
        return str(devices[0])
    if devices:
        print("Serielle Adapter:")
        for device in devices:
            print(" ", device)
    device = input("Pfad des Heizungsadapters: ").strip()
    if not device:
        raise ValidationError("serial adapter must be selected")
    return device


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", help="private JSON configuration file instead of prompts"
    )
    parser.add_argument("--output", default="/etc/froeling-bridge/settings.json")
    args = parser.parse_args(argv)
    output = Path(args.output)
    if output.exists() and not args.config:
        print("Vorhandene Konfiguration bleibt erhalten.")
        return 0
    if args.config:
        settings = json.loads(Path(args.config).read_text())
    else:
        settings = dict(device=choose_device(), host="0.0.0.0", port=8000, interval=60)
        legacy = Path("/etc/froeling-bridge-test/source-db.json")
        if legacy.is_file():
            settings["history"] = json.loads(legacy.read_text())
            print(
                "Vorhandene p4d-Datenbankverbindung wird übernommen; keine Neuinitialisierung des Bestands."
            )
        elif (
            input("MariaDB für optionale Historie einrichten? [j/N] ").strip().lower()
            == "j"
        ):
            settings["history"] = dict(
                host=input("MariaDB-Host [127.0.0.1]: ").strip() or "127.0.0.1",
                port=int(input("MariaDB-Port [3306]: ").strip() or "3306"),
                database=input("Datenbankname [froeling]: ").strip() or "froeling",
                user=input("Datenbankbenutzer: ").strip(),
                password=getpass.getpass("Datenbankpasswort: "),
            )
    validate_settings(settings)
    settings.setdefault("host", "0.0.0.0")
    settings.setdefault("port", 8000)
    settings.setdefault("interval", 60)
    settings.setdefault("state_dir", "/var/lib/froeling-bridge")
    settings.setdefault(
        "reply_profile", {"43": ["42"]}
    )  # Profile observed on the target S3200; installer config can override it.
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    temporary = output.with_name(output.name + ".new-" + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(settings, stream, indent=2)
        stream.write("\n")
    os.replace(temporary, output)
    print("Konfiguration gespeichert. Zugangsdaten werden nicht ausgegeben.")
    return 0


def validate_settings(settings):
    import math

    if not isinstance(settings, dict) or set(settings) - {
        "device",
        "host",
        "port",
        "interval",
        "state_dir",
        "history",
        "reply_profile",
        "write_validation",
    }:
        raise ValidationError("unknown installation configuration fields")
    if (
        not isinstance(settings.get("device"), str)
        or not settings["device"].startswith("/dev/")
        or "\n" in settings["device"]
    ):
        raise ValidationError("select an absolute /dev/ serial device path")
    if (
        settings.get("state_dir", "/var/lib/froeling-bridge")
        != "/var/lib/froeling-bridge"
    ):
        raise ValidationError(
            "native service state directory is /var/lib/froeling-bridge; use CLI for a custom location"
        )
    if (
        type(settings.get("port", 8000)) is not int
        or not 1 <= settings.get("port", 8000) <= 65535
    ):
        raise ValidationError("invalid HTTP port")
    interval = settings.get("interval", 60)
    if (
        type(interval) not in (int, float)
        or not math.isfinite(interval)
        or interval <= 0
    ):
        raise ValidationError("invalid collection interval")
    if "history" in settings:
        from .storage import DatabaseConfig

        history = settings["history"]
        if not isinstance(history, dict) or set(history) - {
            "database",
            "user",
            "password",
            "host",
            "port",
        }:
            raise ValidationError("invalid history configuration")
        try:
            config = DatabaseConfig(**history)
            if (
                not config.database
                or not config.user
                or type(config.port) is not int
                or not 1 <= config.port <= 65535
            ):
                raise ValueError()
        except (TypeError, ValueError):
            raise ValidationError("invalid history configuration") from None


if __name__ == "__main__":
    raise SystemExit(main())
