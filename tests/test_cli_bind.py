import contextlib
import io
import unittest
from unittest.mock import patch

from froeling_bridge.__main__ import main


class ListenAddressTests(unittest.TestCase):
    def test_default_service_listens_on_lan(self):
        with patch('waitress.serve') as serve, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['serve']), 0)
        self.assertEqual(serve.call_args.kwargs['host'], '0.0.0.0')

    def test_explicit_listen_address_is_forwarded(self):
        with patch('waitress.serve') as serve, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['serve', '--host', '127.0.0.1', '--port', '8002']), 0)
        self.assertEqual(serve.call_args.kwargs['host'], '127.0.0.1')
        self.assertEqual(serve.call_args.kwargs['port'], 8002)
