"""Keep menu write eligibility tied to p4d's actual backend allowlist."""
from pathlib import Path
import re
import unittest
from unittest.mock import Mock

from froeling_bridge.errors import ValidationError
from froeling_bridge.messages import ParameterType
from froeling_bridge.service import BridgeService

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'reference/linux-p4d'


@unittest.skipUnless((REFERENCE / 'specific.c').is_file(), 'checkout the pinned p4d submodule')
class OriginalWriteContractTests(unittest.TestCase):
    def original_types(self):
        source = (REFERENCE / 'specific.c').read_text()
        start = source.index('if (type == mstPar ||')
        end = source.index('json_object_set_new(oData, "editable"', start)
        names = re.findall(r'type == (mst\w+)', source[start:end])
        self.assertEqual(len(names), 6)
        definitions = dict((name, int(value, 16)) for name, value in re.findall(
            r'\b(mst\w+)\s*=\s*(0x[0-9a-fA-F]+)', (REFERENCE / 'service.h').read_text()))
        return {definitions[name] for name in names}

    def test_python_and_browser_type_sets_equal_original_backend(self):
        original = self.original_types()
        self.assertEqual({int(kind) for kind in ParameterType}, original)
        browser = (ROOT / 'src/froeling_bridge/static/app.js').read_text()
        match = re.search(r'const editableTypes = new Set\(\[([^]]+)\]\)', browser)
        self.assertIsNotNone(match)
        self.assertEqual({int(value.strip(), 0) for value in match[1].split(',')}, original)

    def test_api_accepts_only_original_parameter_types_without_executing_writes(self):
        original = self.original_types()
        repository = Mock()
        service = BridgeService(repository, client=Mock(), autostart=False)
        self.addCleanup(service.close)
        for kind in range(256):
            with self.subTest(menu_type=kind):
                repository.menu_item.return_value = dict(id=1, type=kind, address=0x1234)
                value = True if kind == 8 else '06:30' if kind == 10 else '1'
                request = dict(operation='write_parameter', menu_id=1, value=value)
                if kind in original:
                    self.assertTrue(callable(service._job_action(request)))
                else:
                    with self.assertRaises(ValidationError):
                        service._job_action(request)
        service.client.set_parameter.assert_not_called()

    def test_api_resolves_address_from_catalogue_and_rejects_supplied_address(self):
        repository = Mock()
        repository.menu_item.return_value = dict(id=1, type=7, address=0x1234)
        client = Mock()
        service = BridgeService(repository, client=client, autostart=False)
        self.addCleanup(service.close)
        request = dict(operation='write_parameter', menu_id=1, value='1')
        action = service._job_action(request)
        with self.assertRaises(ValidationError):
            service._job_action(dict(request, address=0x5678))
        action()  # Mock client only; assert the catalogue address reaches the protocol client.
        client.set_parameter.assert_called_once_with(0x1234, '1', ParameterType.NUMBER)


if __name__ == '__main__':
    unittest.main()
