import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile
from froeling_bridge.local_store import LocalRepository
from froeling_bridge.state_backup import backup, restore
from froeling_bridge.errors import ValidationError


class BackupTests(unittest.TestCase):
    def test_consistent_roundtrip_preserves_preferences_and_removes_write_authorization(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / "old"
            repo = LocalRepository(state / "catalogue.sqlite3")
            repo.set_meta("test", "retained")
            config = root / "settings.json"
            config.write_text(
                json.dumps(
                    dict(device="/dev/ttyUSB0", write_validation="/private/proof.json")
                )
            )
            archive = root / "backup.zip"
            backup(state, config, archive)
            self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
            restore(archive, root / "restored", root / "restored-settings.json")
            self.assertEqual(
                LocalRepository(root / "restored/catalogue.sqlite3").get_meta("test"),
                "retained",
            )
            self.assertNotIn(
                "write_validation",
                json.loads((root / "restored-settings.json").read_text()),
            )
            with self.assertRaises(ValidationError):
                restore(archive, root / "restored", root / "restored-settings.json")

    def test_archive_traversal_and_foreign_entries_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "bad.zip"
            with ZipFile(archive, "w") as z:
                z.writestr("../escape", "bad")
            with self.assertRaises(ValidationError):
                restore(archive, root / "state", root / "settings.json")
            self.assertFalse((root / "state").exists())
