"""Recovery checks for private host setup, without host/root modifications."""

from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

spec = importlib.util.spec_from_file_location(
    "install_state", Path(__file__).resolve().parents[1] / "deploy/install_state.py"
)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class InstallRecoveryTests(unittest.TestCase):
    def test_interrupted_release_is_adopted_only_for_identical_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, release = root / "bundle", root / "release"
            bundle.mkdir()
            (bundle / "release.json").write_text('{"commit":"one"}')
            setup.check_release(bundle, release, [root / "config"])
            release.mkdir()
            with self.assertRaises(ValueError):
                setup.check_release(bundle, release, [])
            (release / "release.json").write_bytes(
                (bundle / "release.json").read_bytes()
            )
            setup.check_release(bundle, release, [])
            (bundle / "release.json").write_text('{"commit":"two"}')
            with self.assertRaises(ValueError):
                setup.check_release(bundle, release, [])

    def test_repeated_setup_and_either_missing_credential_preserve_password(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(setup.os, "chown"),
        ):
            root = Path(directory)
            previous_umask = os.umask(0o077)
            try:
                setup.credentials(root, os.getgid())
            finally:
                os.umask(previous_umask)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            setup.credentials(root, os.getgid())
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            for name in ("test-db.json", "test-db.env"):
                (root / name).unlink()
                setup.credentials(root, os.getgid())
                self.assertEqual(
                    before, {p.name: p.read_bytes() for p in root.iterdir()}
                )
            self.assertEqual((root / "test-db.env").stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / "test-db.json").stat().st_mode & 0o777, 0o640)

    def test_disagreeing_credentials_and_source_edits_are_preserved(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(setup.os, "chown"),
        ):
            root = Path(directory)
            setup.credentials(root, os.getgid())
            env = root / "test-db.env"
            env.write_text("MARIADB_ROOT_PASSWORD=different\n")
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            with self.assertRaises(ValueError):
                setup.credentials(root, os.getgid())
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            a, b = root / "a", root / "b"
            a.write_text('{"database":"one"}')
            b.write_text('{"database":"two"}')
            with self.assertRaises(ValueError):
                setup.source_config(a, b)
            self.assertEqual(json.loads(b.read_text())["database"], "two")

    def test_foreign_container_or_changed_binding_is_refused(self):
        item = dict(
            Config=dict(
                Labels={"org.froeling-bridge.role": "hardware-test"},
                Image="mariadb:10.11",
                Env=["MARIADB_ROOT_PASSWORD=secret"],
            ),
            HostConfig=dict(
                PortBindings={
                    "3306/tcp": [{"HostIp": "127.0.0.1", "HostPort": "33079"}]
                }
            ),
            Mounts=[
                dict(
                    Type="volume",
                    Name="froeling-bridge-test-data",
                    Destination="/var/lib/mysql",
                )
            ],
        )
        setup.container_owned([item], "secret")
        with self.assertRaises(ValueError):
            setup.container_owned([item], "changed")
        item["HostConfig"]["PortBindings"]["3306/tcp"][0]["HostIp"] = "0.0.0.0"
        with self.assertRaises(ValueError):
            setup.container_owned([item], "secret")


@unittest.skipUnless(
    os.environ.get("FROELING_TEST_DB_CONFIG"), "requires separate local MariaDB"
)
class InstallDatabaseRecoveryTests(unittest.TestCase):
    def test_partial_schema_resumes_and_repeated_setup_preserves_rows(self):
        from froeling_bridge.storage import DatabaseConfig

        base = DatabaseConfig.load(os.environ["FROELING_TEST_DB_CONFIG"])
        config = replace(
            base, database="froeling_bridge_test_install_" + uuid.uuid4().hex[:8]
        )
        setup.initialize_schema(config)
        connection = config.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO valuefacts (address,type,title) VALUES (42,'VA','keep me')"
                )
                cursor.execute("DROP TABLE peaks")  # simulate interrupted DDL
            connection.commit()
            setup.initialize_schema(config)
            setup.initialize_schema(config)
            with connection.cursor() as cursor:
                cursor.execute("SELECT title FROM valuefacts WHERE address=42")
                self.assertEqual(cursor.fetchone()["title"], "keep me")
                cursor.execute("SHOW TABLES LIKE 'peaks'")
                self.assertTrue(cursor.fetchone())
                cursor.execute("ALTER TABLE peaks ADD COLUMN unexpected INT")
            with self.assertRaises(ValueError):
                setup.initialize_schema(config)
            with connection.cursor() as cursor:
                cursor.execute("SELECT title FROM valuefacts WHERE address=42")
                self.assertEqual(cursor.fetchone()["title"], "keep me")
        finally:
            connection.close()
            cleanup = replace(config, database="").connect()
            with cleanup.cursor() as cursor:
                cursor.execute(f"DROP DATABASE `{config.database}`")
            cleanup.close()
