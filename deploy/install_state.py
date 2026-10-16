"""Private setup state operations; no live database or heating access."""

import argparse
import grp
import json
import os
from pathlib import Path
import secrets


def atomic(path, data, mode=0o600, gid=None):
    temp = path.with_name(path.name + ".install-tmp")
    # Never follow a pre-existing temporary symlink.
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if gid is not None:
            os.chown(temp, 0, gid)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def check_release(bundle, release, protected):
    marker = release / "release.json"
    if marker.is_symlink() or release.is_symlink():
        raise ValueError("Release paths must not be symlinks.")
    if marker.exists():
        if marker.read_bytes() != (bundle / "release.json").read_bytes():
            raise ValueError(
                "Existing release differs from this bundle; refusing an upgrade."
            )
    elif release.exists() or any(path.exists() for path in protected):
        raise ValueError("Unidentified existing installation; no files overwritten.")


def source_config(source, target):
    if target.exists():
        if target.is_symlink() or json.loads(target.read_text()) != json.loads(
            source.read_text()
        ):
            raise ValueError(
                "Existing source DB configuration differs; preserved without changes."
            )


def credentials(root, gid):
    env = root / "test-db.env"
    config = root / "test-db.json"
    for path in (env, config):
        if path.is_symlink():
            raise ValueError("Credential paths must not be symlinks.")
    password = None
    if env.exists():
        content = env.read_text()
        prefix = "MARIADB_ROOT_PASSWORD="
        if not content.startswith(prefix) or content.count("\n") != 1:
            raise ValueError("Unrecognized test DB environment file; preserved.")
        password = content[len(prefix) : -1]
    if config.exists():
        existing = json.loads(config.read_text())
        if (
            existing.get("host") != "127.0.0.1"
            or existing.get("port") != 33079
            or existing.get("user") != "root"
            or existing.get("database") != "froeling_bridge_test_initial"
        ):
            raise ValueError("Unexpected test DB configuration; preserved.")
        if password is not None and password != existing.get("password"):
            raise ValueError("Test DB credentials disagree; neither file changed.")
        password = existing.get("password")
        if not isinstance(password, str) or not password:
            raise ValueError("Missing password in existing test DB configuration.")
    if password is None:
        password = secrets.token_hex(32)
    if (
        not isinstance(password, str)
        or not password
        or "\n" in password
        or "\r" in password
    ):
        raise ValueError("Invalid test DB password; existing files preserved.")
    if not env.exists():
        atomic(env, "MARIADB_ROOT_PASSWORD=" + password + "\n")
    if not config.exists():
        atomic(
            config,
            json.dumps(
                dict(
                    host="127.0.0.1",
                    port=33079,
                    database="froeling_bridge_test_initial",
                    user="root",
                    password=password,
                )
            )
            + "\n",
            0o640,
            gid,
        )


def container_owned(data, password):
    item = data[0]
    if (
        (item["Config"]["Labels"] or {}).get("org.froeling-bridge.role")
        != "hardware-test"
        or item["Config"]["Image"] != "mariadb:10.11"
        or item["HostConfig"]["PortBindings"]
        != {"3306/tcp": [{"HostIp": "127.0.0.1", "HostPort": "33079"}]}
        or "MARIADB_ROOT_PASSWORD=" + password not in item["Config"]["Env"]
        or not any(
            m.get("Type") == "volume"
            and m.get("Name") == "froeling-bridge-test-data"
            and m.get("Destination") == "/var/lib/mysql"
            for m in item["Mounts"]
        )
    ):
        raise ValueError(
            "Existing test container does not match this installation; preserved."
        )


def initialize_schema(config):
    """Resume empty test-schema creation without clearing existing tables or rows."""
    config.require_test()
    from dataclasses import replace
    import json
    from importlib.resources import files

    schema = json.loads(
        files("froeling_bridge").joinpath("test-schema.json").read_text()
    )
    conn = replace(config, database="").connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{config.database}` CHARACTER SET utf8mb3"
            )
            cursor.execute(f"USE `{config.database}`")
            cursor.execute("SHOW TABLES")
            existing = {
                next(iter(row.values())) if isinstance(row, dict) else row[0]
                for row in cursor.fetchall()
            }
            if existing - set(schema):
                raise ValueError("Unexpected tables in test database; preserved.")
            for table, columns in schema.items():
                if table in existing:
                    cursor.execute(f"SHOW COLUMNS FROM `{table}`")
                    actual = cursor.fetchall()
                    if [
                        (
                            row["Field"],
                            row["Type"].lower(),
                            row["Null"] == "YES",
                            row["Key"] == "PRI",
                            "auto_increment" in row["Extra"],
                        )
                        for row in actual
                    ] != [
                        (
                            c["name"],
                            c["type"].lower(),
                            c["nullable"],
                            c["primary"],
                            c["auto_increment"],
                        )
                        for c in columns
                    ]:
                        raise ValueError("Existing test schema differs; preserved.")
            for table, columns in schema.items():
                if table in existing:
                    continue
                definitions = [
                    f"`{c['name']}` {c['type']} {'NULL' if c['nullable'] else 'NOT NULL'} {'AUTO_INCREMENT' if c['auto_increment'] else ''}"
                    for c in columns
                ]
                definitions.append(
                    "PRIMARY KEY ("
                    + ",".join(f"`{c['name']}`" for c in columns if c["primary"])
                    + ")"
                )
                if table == "samples":
                    definitions.append("INDEX addr_type_time (address,type,time)")
                cursor.execute(
                    f"CREATE TABLE `{table}` ("
                    + ",".join(definitions)
                    + ") ENGINE=InnoDB"
                )
        conn.commit()
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("check", "credentials", "container", "database")
    )
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    root = Path("/etc/froeling-bridge-test")
    try:
        if args.action == "check":
            check_release(
                args.bundle,
                Path("/opt/froeling-bridge/0.3.0"),
                [
                    root,
                    Path("/var/lib/froeling-bridge-coordinator"),
                    Path("/usr/local/sbin/froeling-bridge-test"),
                ],
            )
            source_config(args.bundle / "source-db.json", root / "source-db.json")
        elif args.action == "credentials":
            credentials(root, grp.getgrnam("froeling-bridge-test").gr_gid)
        elif args.action == "database":
            from dataclasses import replace
            import time
            from froeling_bridge.storage import DatabaseConfig

            config = DatabaseConfig.load(root / "test-db.json")
            config.require_test()
            for attempt in range(60):
                try:
                    conn = replace(config, database="").connect()
                    conn.close()
                    break
                except Exception:
                    time.sleep(1)
            else:
                raise ValueError("Separate test database did not become ready.")
            initialize_schema(config)
        else:
            import sys

            container_owned(
                json.load(sys.stdin),
                json.loads((root / "test-db.json").read_text())["password"],
            )
    except (ValueError, KeyError, OSError, IndexError):
        # Do not expose configuration contents via JSON or subprocess errors.
        raise SystemExit(
            "Setup state check failed ("
            + args.action
            + "); existing configuration/data preserved."
        )


if __name__ == "__main__":
    main()
