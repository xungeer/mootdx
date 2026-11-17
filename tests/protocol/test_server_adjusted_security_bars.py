import struct
import unittest
from datetime import date
from datetime import datetime
from unittest import mock

from mootdx._protocol.hq import ServerAdjustedTdxHqAPI
from mootdx._protocol.hq import TdxHq_API
from mootdx._protocol.helper import get_volume
from mootdx._protocol.parser.std.get_security_bars import GetSecurityBarsCmd
from mootdx._protocol.parser.std.get_server_adjusted_security_bars import GetServerAdjustedSecurityBarsCmd
from mootdx._protocol.parser.std.get_server_adjusted_security_bars import SERVER_ADJUSTED_BAR_BATCH_SIZE
from mootdx._protocol.parser.std.get_server_adjusted_security_bars import normalize_adjust
from mootdx._protocol.parser.std.get_server_adjusted_security_bars import normalize_anchor_date


PARSER_MODULE = "mootdx._protocol.parser.std.get_server_adjusted_security_bars"


class TestGetServerAdjustedSecurityBarsCmd(unittest.TestCase):
    def test_builds_54_byte_qfq_frame(self):
        parser = GetServerAdjustedSecurityBarsCmd(client=None)

        parser.setParams(4, 1, "600036", 0, 5, adjust="qfq")

        self.assertEqual(len(parser.send_pkg), 54)
        self.assertEqual(
            parser.send_pkg.hex(),
            "0c01086401012c002c002d05"
            "0100"
            "363030303336"
            "0400"
            "0100"
            "0000"
            "0500"
            "0100"
            "00000000"
            "0000000000000000000000000000000000000000",
        )

    def test_encodes_fixed_anchor_date(self):
        parser = GetServerAdjustedSecurityBarsCmd(client=None)

        parser.setParams(
            4,
            0,
            "000001",
            0,
            420,
            adjust="fixed_qfq",
            anchor_date="2007-06-23",
        )

        self.assertEqual(parser.send_pkg[28:34].hex(), "0300df403201")

    def test_encodes_custom_period_parameter(self):
        parser = GetServerAdjustedSecurityBarsCmd(client=None)

        parser.setParams(8, 0, "000001", 0, 5, adjust="qfq", period_param=10)

        self.assertEqual(parser.send_pkg[20:24].hex(), "08000a00")

    def test_accepts_exact_server_batch_limit(self):
        parser = GetServerAdjustedSecurityBarsCmd(client=None)

        parser.setParams(9, 0, "000001", 0, SERVER_ADJUSTED_BAR_BATCH_SIZE, adjust="none")

        self.assertEqual(
            int.from_bytes(parser.send_pkg[26:28], "little"),
            SERVER_ADJUSTED_BAR_BATCH_SIZE,
        )

    def test_accepts_custom_period_parameter_for_supported_categories(self):
        for category in [8, 9, 13]:
            with self.subTest(category=category):
                parser = GetServerAdjustedSecurityBarsCmd(client=None)
                parser.setParams(category, 0, "000001", 0, 5, adjust="none", period_param=2)
                self.assertEqual(int.from_bytes(parser.send_pkg[22:24], "little"), 2)

    def test_normalizes_adjustment_and_anchor_date(self):
        self.assertEqual(normalize_adjust(None), 0)
        self.assertEqual(normalize_adjust("before"), 1)
        self.assertEqual(normalize_adjust("hfq"), 2)
        self.assertEqual(normalize_adjust("fixed_front"), 3)
        self.assertEqual(normalize_adjust(4), 4)
        self.assertEqual(normalize_anchor_date(date(2024, 6, 3)), 20240603)
        self.assertEqual(normalize_anchor_date("20240603"), 20240603)

        with self.assertRaisesRegex(ValueError, "复权参数错误"):
            normalize_adjust("invalid")
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            normalize_anchor_date("2024-13-03")
        with self.assertRaisesRegex(ValueError, "定点复权日期错误"):
            normalize_anchor_date(False)

    def test_rejects_protocol_parameter_boundaries(self):
        invalid_cases = [
            ({"market": 3}, "市场代码"),
            ({"category": -1}, "category"),
            ({"category": 12}, "category"),
            ({"category": 65536}, "category"),
            ({"start": -1}, "start"),
            ({"start": 65536}, "start"),
            ({"count": 0}, "count"),
            ({"count": 801}, "count"),
            ({"period_param": 0}, "period_param"),
            ({"period_param": 32768}, "period_param"),
            ({"category": 5, "period_param": 2}, "period_param"),
            ({"code": "00001"}, "股票代码"),
            ({"code": "股票01"}, "ASCII"),
            ({"code": b"\xff" * 6}, "ASCII"),
            ({"adjust": "fixed_hfq"}, "anchor_date"),
            ({"category": 13, "adjust": "qfq"}, "秒线"),
        ]

        for changes, message in invalid_cases:
            params = {
                "category": 9,
                "market": 0,
                "code": "000001",
                "start": 0,
                "count": 5,
                "adjust": "none",
                "anchor_date": None,
                "period_param": 1,
            }
            params.update(changes)
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                GetServerAdjustedSecurityBarsCmd(client=None).setParams(**params)

    def test_rejects_non_integer_fields(self):
        for field, value in [
            ("category", True),
            ("market", "1"),
            ("start", 1.9),
            ("count", 1.9),
            ("period_param", 1.9),
        ]:
            params = {
                "category": 9,
                "market": 0,
                "code": "000001",
                "start": 0,
                "count": 5,
                "adjust": "none",
                "period_param": 1,
            }
            params[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, f"{field} 必须是整数"):
                GetServerAdjustedSecurityBarsCmd(client=None).setParams(**params)

    def test_parses_second_bars(self):
        parser = GetServerAdjustedSecurityBarsCmd(client=None)
        parser.category = 13
        price_diffs = iter([10000, 200, 300, -100])
        timestamp = int((datetime(2026, 7, 21, 14, 57, 5) - datetime(2003, 12, 31)).total_seconds())
        body = struct.pack("<HI", 1, timestamp) + b"\x00" * 4 + struct.pack("<II", 123, 456)

        with mock.patch(
            f"{PARSER_MODULE}.get_price",
            side_effect=lambda payload, pos: (next(price_diffs), pos + 1),
        ), mock.patch(f"{PARSER_MODULE}.get_volume", side_effect=float):
            result = parser.parseResponse(body)

        self.assertEqual(result[0]["datetime"], "2026-07-21 14:57:05")
        self.assertEqual(result[0]["second"], 5)
        self.assertEqual(result[0]["open"], 10.0)
        self.assertEqual(result[0]["close"], 10.2)
        self.assertEqual(result[0]["high"], 10.3)
        self.assertEqual(result[0]["low"], 9.9)
        self.assertEqual(result[0]["vol"], 123.0)
        self.assertEqual(result[0]["amount"], 456.0)

    def test_parses_second_bar_zero_volume_as_zero(self):
        parser = GetServerAdjustedSecurityBarsCmd(client=None)
        parser.category = 13
        price_diffs = iter([10000, 0, 0, 0])
        timestamp = int((datetime(2026, 7, 21, 14, 57, 5) - datetime(2003, 12, 31)).total_seconds())
        body = struct.pack("<HI", 1, timestamp) + b"\x00" * 4 + struct.pack("<II", 0, 0)

        with mock.patch(
            f"{PARSER_MODULE}.get_price",
            side_effect=lambda payload, pos: (next(price_diffs), pos + 1),
        ):
            result = parser.parseResponse(body)

        self.assertEqual(result[0]["vol"], 0.0)
        self.assertEqual(result[0]["amount"], 0.0)


class TestServerAdjustedTdxHqAPI(unittest.TestCase):
    def test_setup_uses_only_first_handshake(self):
        api = ServerAdjustedTdxHqAPI(auto_retry=False, raise_exception=True)
        api.client = object()

        with mock.patch("mootdx._protocol.hq.SetupCmd1") as setup1, mock.patch("mootdx._protocol.hq.SetupCmd2") as setup2, mock.patch(
            "mootdx._protocol.hq.SetupCmd3"
        ) as setup3:
            import json
            from pathlib import Path
            fixtures = json.loads((Path(__file__).parent / "fixtures" / "handshake_20261111.json").read_text())["fixtures"]
            payload = next(item for item in fixtures if item["parser"] == "SetupCmd1")
            setup1.return_value.call_api.return_value = bytes.fromhex(payload["response_hex"])
            setup1.return_value.send_pkg = bytes.fromhex(payload["request_hex"])
            api.setup()

        setup1.assert_called_once_with(api.client, lock=api.lock)
        setup1.return_value.call_api.assert_called_once_with()
        setup2.assert_not_called()
        setup3.assert_not_called()

    @mock.patch("mootdx._protocol.hq.GetServerAdjustedSecurityBarsCmd")
    def test_api_forwards_server_adjusted_parameters(self, parser_cls):
        api = ServerAdjustedTdxHqAPI(auto_retry=False, raise_exception=True)
        api.client = object()
        parser_cls.return_value.call_api.return_value = [{"close": 10.2}]

        result = api.get_server_adjusted_bars(
            9,
            1,
            "600036",
            20,
            30,
            adjust="fixed_hfq",
            anchor_date="2024-06-03",
            period_param=2,
        )

        parser_cls.assert_called_once_with(api.client, lock=api.lock)
        parser_cls.return_value.setParams.assert_called_once_with(
            9,
            1,
            "600036",
            20,
            30,
            "fixed_hfq",
            "2024-06-03",
            2,
        )
        self.assertEqual(result, [{"close": 10.2}])


class TestLegacySecurityBarsCompatibility(unittest.TestCase):
    def test_zero_volume_decodes_as_zero(self):
        self.assertEqual(get_volume(0), 0.0)

    def test_legacy_frame_remains_unchanged(self):
        parser = GetSecurityBarsCmd(client=None)

        parser.setParams(9, 1, "600036", 0, 5)

        self.assertEqual(len(parser.send_pkg), 38)
        self.assertEqual(
            parser.send_pkg.hex(),
            "0c01086401011c001c002d050100363030303336090001000000050000000000000000000000",
        )

    def test_explicit_legacy_api_keeps_three_handshakes(self):
        api = TdxHq_API(auto_retry=False, raise_exception=True, handshake="legacy")
        api.client = object()

        with mock.patch("mootdx._protocol.hq.SetupCmd1") as setup1, mock.patch("mootdx._protocol.hq.SetupCmd2") as setup2, mock.patch(
            "mootdx._protocol.hq.SetupCmd3"
        ) as setup3:
            import json
            from pathlib import Path
            fixtures = json.loads((Path(__file__).parent / "fixtures" / "handshake_20261111.json").read_text())["fixtures"]
            for number, command in enumerate((setup1, setup2, setup3), 1):
                payload = next(item for item in fixtures
                               if item["parser"] == f"SetupCmd{number}"
                               and "客户端与行情主站不匹配,不能使用!".encode("gbk").hex() not in item["response_hex"])
                command.return_value.call_api.return_value = bytes.fromhex(payload["response_hex"])
                command.return_value.send_pkg = bytes.fromhex(payload["request_hex"])
            api.setup()

        setup1.assert_called_once_with(api.client, lock=api.lock)
        setup1.return_value.call_api.assert_called_once_with()
        setup2.assert_called_once_with(api.client, lock=api.lock)
        setup2.return_value.call_api.assert_called_once_with()
        setup3.assert_called_once_with(api.client, lock=api.lock)
        setup3.return_value.call_api.assert_called_once_with()

    @mock.patch("mootdx._protocol.hq.GetSecurityBarsCmd")
    def test_legacy_api_still_forwards_original_arguments(self, parser_cls):
        api = TdxHq_API(auto_retry=False, raise_exception=True)
        api.client = object()
        parser_cls.return_value.call_api.return_value = [{"close": 10.0}]

        result = api.get_security_bars(9, 1, "600036", 0, 5)

        parser_cls.assert_called_once_with(api.client, lock=api.lock)
        parser_cls.return_value.setParams.assert_called_once_with(9, 1, "600036", 0, 5)
        self.assertEqual(result, [{"close": 10.0}])


if __name__ == "__main__":
    unittest.main()
