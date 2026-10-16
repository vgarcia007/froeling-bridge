"""Explicit initialization of a new local, synthetic test database only."""
from dataclasses import replace
from importlib.resources import files
import json

from .errors import ValidationError
from .storage import demo_menu, demo_sensors


def initialize(config):
    config.require_test()
    # Identifiers are validated by require_test; all DDL types come from our
    # packaged, sanitized schema snapshot, never from a request or DB response.
    connection = replace(config, database="").connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{config.database}` CHARACTER SET utf8mb3")
            cursor.execute(f"USE `{config.database}`")
            cursor.execute("SHOW TABLES")
            if cursor.fetchall():
                raise ValidationError("test database must be empty; existing tables will not be changed")
            schema = json.loads(files("froeling_bridge").joinpath("test-schema.json").read_text(encoding="utf-8"))
            for table, columns in schema.items():
                definitions = [f"`{c['name']}` {c['type']} {'NULL' if c['nullable'] else 'NOT NULL'} {'AUTO_INCREMENT' if c['auto_increment'] else ''}"
                               for c in columns]
                primary = [f"`{c['name']}`" for c in columns if c['primary']]
                definitions.append("PRIMARY KEY (" + ",".join(primary) + ")")
                if table == "samples":
                    definitions.append("INDEX addr_type_time (address,type,time)")
                cursor.execute(f"CREATE TABLE `{table}` (" + ",".join(definitions) + ") ENGINE=InnoDB")
            for sensor in demo_sensors():
                keys = list(sensor)
                cursor.execute("INSERT INTO valuefacts (" + ",".join(f"`{k}`" for k in keys)
                               + ") VALUES (" + ",".join(["%s"] * len(keys)) + ")", tuple(sensor.values()))
            for item in demo_menu():
                keys = list(item)
                cursor.execute("INSERT INTO menu (" + ",".join(f"`{k}`" for k in keys)
                               + ") VALUES (" + ",".join(["%s"] * len(keys)) + ")", tuple(item.values()))
        connection.commit()
    finally:
        connection.close()
