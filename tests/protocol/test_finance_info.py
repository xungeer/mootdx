import struct
import unittest
from collections import OrderedDict
from unittest import mock

from mootdx._protocol.hq import TdxHq_API
from mootdx._protocol.parser.std.get_finance_info import FINANCE_RECORD_SIZE
from mootdx._protocol.parser.std.get_finance_info import GetFinanceInfo
from mootdx._protocol.parser.std.get_finance_info import GetFinanceInfoBatch


def _finance_record(market, code, seed=1.0):
    finance_values = [seed + index for index in range(30)]
    return struct.pack(
        "<B6sfHHII30f",
        market,
        code.encode("ascii"),
        seed,
        int(seed) + 10,
        int(seed) + 20,
        20260711,
        19910403,
        *finance_values,
    )


class TestGetFinanceInfoBatch(unittest.TestCase):
    def test_builds_finance_batch_frame(self):
        parser = GetFinanceInfoBatch(client=None)

        parser.setParams([(0, "000001"), (1, b"600000"), (2, "920971")])

        body = struct.pack("<H", 3)
        body += struct.pack("<B6s", 0, b"000001")
        body += struct.pack("<B6s", 1, b"600000")
        body += struct.pack("<B6s", 2, b"920971")
        expected_header = bytearray.fromhex("0c 1f 18 76 00 01")
        expected_header.extend(struct.pack("<HHH", len(body) + 2, len(body) + 2, 0x0010))
        self.assertEqual(parser.send_pkg, expected_header + body)

    def test_parses_finance_records_for_all_three_markets(self):
        parser = GetFinanceInfoBatch(client=None)
        records = [
            _finance_record(0, "000001", 1.0),
            _finance_record(1, "600000", 2.0),
            _finance_record(2, "920971", 3.0),
        ]

        result = parser.parseResponse(struct.pack("<H", len(records)) + b"".join(records))

        self.assertEqual(len(result), 3)
        self.assertTrue(all(isinstance(row, OrderedDict) for row in result))
        self.assertEqual([(row["market"], row["code"]) for row in result], [
            (0, "000001"),
            (1, "600000"),
            (2, "920971"),
        ])
        self.assertEqual(result[0]["liutongguben"], 10000.0)
        self.assertEqual(result[2]["industry"], 23)
        self.assertEqual(result[2]["zongguben"], 30000.0)
        self.assertEqual(len(records[0]), FINANCE_RECORD_SIZE)

    def test_rejects_truncated_or_trailing_response_bytes(self):
        parser = GetFinanceInfoBatch(client=None)
        payload = struct.pack("<H", 1) + _finance_record(0, "000001")

        with self.assertRaisesRegex(ValueError, "expected=145, actual=144"):
            parser.parseResponse(payload[:-1])
        with self.assertRaisesRegex(ValueError, "expected=145, actual=146"):
            parser.parseResponse(payload + b"x")

    def test_rejects_empty_oversized_and_invalid_batch_parameters(self):
        parser = GetFinanceInfoBatch(client=None)
        invalid_parameters = [
            None,
            [],
            "000001",
            [(0, "000001")] * 81,
            [(3, "000001")],
            [(True, "000001")],
            [(0, "00001")],
            [(0, "ABCDEF")],
            [(0, object())],
            [(0, "000001", "extra")],
        ]

        for all_stock in invalid_parameters:
            with self.subTest(all_stock=all_stock), self.assertRaises(ValueError):
                parser.setParams(all_stock)

    @mock.patch("mootdx._protocol.hq.GetFinanceInfoBatch")
    def test_api_forwards_batch_parameters(self, parser_cls):
        api = TdxHq_API(auto_retry=False, raise_exception=True)
        api.client = object()
        stocks = [(0, "000001"), (2, "920971")]
        parser_cls.return_value.call_api.return_value = [{"code": "000001"}]

        result = api.get_finance_info_batch(stocks)

        parser_cls.assert_called_once_with(api.client, lock=api.lock)
        parser_cls.return_value.setParams.assert_called_once_with(stocks)
        self.assertEqual(result, [{"code": "000001"}])


class TestGetFinanceInfoCompatibility(unittest.TestCase):
    def test_single_request_frame_and_result_shape_remain_compatible(self):
        parser = GetFinanceInfo(client=None)

        parser.setParams(1, "600000")

        expected = bytearray.fromhex("0c 1f 18 76 00 01 0b 00 0b 00 10 00 01 00")
        expected.extend(struct.pack("<B6s", 1, b"600000"))
        self.assertEqual(parser.send_pkg, expected)

        result = parser.parseResponse(struct.pack("<H", 1) + _finance_record(1, "600000"))
        self.assertIsInstance(result, OrderedDict)
        self.assertEqual(result["market"], 1)
        self.assertEqual(result["code"], "600000")
        self.assertEqual(result["zongguben"], 10000.0)

    @mock.patch("mootdx._protocol.hq.GetFinanceInfo")
    def test_single_api_still_forwards_market_and_code(self, parser_cls):
        api = TdxHq_API(auto_retry=False, raise_exception=True)
        api.client = object()
        parser_cls.return_value.call_api.return_value = {"code": "600000"}

        result = api.get_finance_info(1, "600000")

        parser_cls.assert_called_once_with(api.client, lock=api.lock)
        parser_cls.return_value.setParams.assert_called_once_with(1, "600000")
        self.assertEqual(result, {"code": "600000"})


if __name__ == "__main__":
    unittest.main()
