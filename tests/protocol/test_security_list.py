import struct
import unittest
from collections import OrderedDict
from unittest import mock

from mootdx._protocol.hq import TdxHq_API
from mootdx._protocol.parser.std.get_security_list import GetSecurityList


class TestGetSecurityList(unittest.TestCase):
    def test_builds_current_security_list_frame(self):
        parser = GetSecurityList(client=None)

        parser.setParams(market=2, start=1600, limit=800)

        expected_header = bytearray.fromhex("0c 01 18 64 01 01 10 00 10 00 4d 04")
        expected_body = struct.pack("<HIII", 2, 1600, 800, 0)
        self.assertEqual(parser.send_pkg, expected_header + expected_body)
        self.assertEqual(len(expected_body), 14)

    def test_default_limit_preserves_legacy_page_size(self):
        parser = GetSecurityList(client=None)

        parser.setParams(market=1, start=0)

        self.assertEqual(parser.send_pkg[-8:-4], (1000).to_bytes(4, "little"))

    @mock.patch("mootdx._protocol.hq.GetSecurityList")
    def test_api_forwards_optional_limit(self, parser_cls):
        api = TdxHq_API(auto_retry=False, raise_exception=True)
        api.client = object()
        parser_cls.return_value.call_api.return_value = []

        result = api.get_security_list(market=2, start=25, limit=50)

        parser_cls.assert_called_once_with(api.client, lock=api.lock)
        parser_cls.return_value.setParams.assert_called_once_with(2, 25, 50)
        self.assertEqual(result, [])

    def test_parses_37_byte_security_records_with_compatible_fields(self):
        parser = GetSecurityList(client=None)
        name = "天马新材".encode("gbk").ljust(16, b"\x00")
        record = struct.pack(
            "<6sH16s4sBf4s",
            b"920971",
            100,
            name,
            bytes.fromhex("067a6043"),
            2,
            32.96,
            bytes.fromhex("dc31c625"),
        )

        result = parser.parseResponse(struct.pack("<H", 1) + record)

        row = result[0]
        self.assertIsInstance(row, OrderedDict)
        self.assertEqual(list(row), ["code", "volunit", "decimal_point", "name", "pre_close"])
        self.assertEqual(row["code"], "920971")
        self.assertEqual(row["volunit"], 100)
        self.assertEqual(row["decimal_point"], 2)
        self.assertEqual(row["name"], "天马新材")
        self.assertAlmostEqual(row["pre_close"], 32.96, places=4)
        self.assertEqual(len(record), 37)

    def test_rejects_truncated_security_list_payload(self):
        parser = GetSecurityList(client=None)
        payload = struct.pack("<H", 1) + b"truncated"

        with self.assertRaisesRegex(ValueError, "响应不完整"):
            parser.parseResponse(payload)


if __name__ == "__main__":
    unittest.main()
