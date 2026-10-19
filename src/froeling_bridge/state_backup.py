"""Consistent private catalogue/config backups. Historical MariaDB data is separate."""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from .errors import ValidationError

NAMES = {"catalogue.sqlite3", "auth.sqlite3", "time-programs-cache.json", "settings.json"}


def backup(state_dir, config, output):
    state_dir, output = Path(state_dir), Path(output)
    with tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        source = state_dir / "catalogue.sqlite3"
        if source.is_symlink():
            raise ValidationError("catalogue symlink refused")
        with (
            closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src,
            closing(sqlite3.connect(temporary / "catalogue.sqlite3")) as dst,
        ):
            src.backup(dst)
        source = state_dir / 'auth.sqlite3'
        if source.is_symlink():
            raise ValidationError('authentication database symlink refused')
        if source.is_file():
            with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro', uri=True)) as src, closing(sqlite3.connect(temporary/'auth.sqlite3')) as dst:
                src.backup(dst)
        for source, name in (
            (state_dir / "time-programs-cache.json", "time-programs-cache.json"),
            (Path(config), "settings.json"),
        ):
            if source.is_symlink():
                raise ValidationError("backup source symlink refused")
            if source.is_file():
                shutil.copyfile(source, temporary / name)
        fd = os.open(
            output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with (
            os.fdopen(fd, "wb") as stream,
            ZipFile(stream, "w", ZIP_DEFLATED) as archive,
        ):
            for file in temporary.iterdir():
                archive.write(file, file.name)


def restore(archive_path, state_dir, config):
    state_dir, config = Path(state_dir), Path(config)
    if state_dir.exists() and any(state_dir.iterdir()) or config.exists():
        raise ValidationError(
            "restore requires an empty state directory and absent destination configuration"
        )
    with ZipFile(archive_path) as archive, tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        names = archive.namelist()
        if (
            len(names) != len(set(names))
            or not set(names) <= NAMES
            or "catalogue.sqlite3" not in names
        ):
            raise ValidationError("unsupported backup contents")
        for item in archive.infolist():
            if item.file_size > 128 * 1024 * 1024:
                raise ValidationError("oversized backup entry")
            (temporary / item.filename).write_bytes(archive.read(item))
        with sqlite3.connect(temporary / "catalogue.sqlite3") as db:
            if (
                db.execute("PRAGMA quick_check").fetchone()[0] != "ok"
                or db.execute("PRAGMA user_version").fetchone()[0] != 1
            ):
                raise ValidationError("unsupported or damaged catalogue backup")
        settings = None
        if 'auth.sqlite3' in names:
            with closing(sqlite3.connect(temporary/'auth.sqlite3')) as db:
                if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or db.execute('PRAGMA user_version').fetchone()[0] != 1:
                    raise ValidationError('unsupported or damaged authentication backup')
                db.execute('DELETE FROM sessions')
                db.commit()
                db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        if "settings.json" in names:
            from .configure import validate_settings

            settings = json.loads((temporary / "settings.json").read_text())
            settings.pop(
                "write_validation", None
            )  # Never transfer heating-write authorization to another host/device.
            validate_settings(settings)
        state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name in names:
            if name == "settings.json":
                continue
            target = state_dir / name
            with target.open("xb") as stream:
                stream.write((temporary / name).read_bytes())
            target.chmod(0o600)
        if settings is not None:
            config.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
            with config.open("x") as stream:
                json.dump(settings, stream, indent=2)
            config.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(
        description="Private catalogue/config backup; does not back up MariaDB history"
    )
    parser.add_argument("action", choices=("backup", "restore"))
    parser.add_argument("--state-dir", default="/var/lib/froeling-bridge")
    parser.add_argument("--config", default="/etc/froeling-bridge/settings.json")
    parser.add_argument("--archive", required=True)
    args = parser.parse_args()
    if args.action == "restore":
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", "froeling-bridge.service"],
            capture_output=True,
        )
        if result.returncode == 0:
            raise ValidationError("stop the Bridge before restoring its state")
        restore(args.archive, args.state_dir, args.config)
    else:
        backup(args.state_dir, args.config, args.archive)
    print("Private backup operation completed. MariaDB history is not included.")


if __name__ == "__main__":
    main()
