# cython: language_level=3
import struct
from collections import OrderedDict
from datetime import date
from datetime import datetime
from datetime import timedelta

from mootdx._protocol.helper import get_price
from mootdx._protocol.helper import get_volume
from mootdx._protocol.parser.std.get_security_bars import GetSecurityBarsCmd


SERVER_ADJUSTED_BAR_BATCH_SIZE = 800

ADJUST_MODES = {
    None: 0,
    "": 0,
    "none": 0,
    "bfq": 0,
    "qfq": 1,
    "front": 1,
    "before": 1,
    "hfq": 2,
    "back": 2,
    "after": 2,
    "fixed_qfq": 3,
    "fixed_front": 3,
    "fixed_hfq": 4,
    "fixed_back": 4,
}


def normalize_adjust(adjust):
    if isinstance(adjust, bool):
        raise ValueError(f"复权参数错误: {adjust!r}")

    if isinstance(adjust, int):
        if adjust in range(5):
            return adjust
        raise ValueError(f"复权参数错误: {adjust!r}")

    key = None if adjust is None else str(adjust).strip().lower()

    try:
        return ADJUST_MODES[key]
    except KeyError as ex:
        raise ValueError(
            "复权参数错误, adjust 仅支持 none/bfq、qfq/front、hfq/back、"
            "fixed_qfq/fixed_front、fixed_hfq/fixed_back"
        ) from ex


def normalize_anchor_date(anchor_date):
    if isinstance(anchor_date, bool):
        raise ValueError(f"定点复权日期错误: {anchor_date!r}")

    if anchor_date in [None, "", 0]:
        return 0

    if isinstance(anchor_date, (date, datetime)):
        return int(anchor_date.strftime("%Y%m%d"))

    value = str(anchor_date).strip()
    date_format = "%Y-%m-%d" if "-" in value else "%Y%m%d"

    try:
        return int(datetime.strptime(value, date_format).strftime("%Y%m%d"))
    except ValueError as ex:
        raise ValueError("定点复权日期必须是 YYYY-MM-DD 或 YYYYMMDD") from ex


class GetServerAdjustedSecurityBarsCmd(GetSecurityBarsCmd):
    """通达信新版 0x052d K 线请求，支持服务端复权参数。"""

    def setParams(
        self,
        category,
        market,
        code,
        start,
        count,
        adjust="qfq",
        anchor_date=None,
        period_param=1,
    ):
        integer_fields = {
            "category": category,
            "market": market,
            "start": start,
            "count": count,
            "period_param": period_param,
        }
        for field, value in integer_fields.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field} 必须是整数")

        category = int(category)
        market = int(market)
        start = int(start)
        count = int(count)
        period_param = int(period_param)
        adjust_mode = normalize_adjust(adjust)
        anchor_date_raw = normalize_anchor_date(anchor_date)

        if market not in [0, 1, 2]:
            raise ValueError(f"市场代码错误: {market!r}")
        if category not in range(12) and category != 13:
            raise ValueError("category 仅支持 0 到 11 或 13")
        if period_param <= 0 or period_param > 0x7FFF:
            raise ValueError("period_param 必须在 1 到 32767 之间")
        if category not in [8, 9, 13] and period_param != 1:
            raise ValueError(f"category {category} 的 period_param 必须为 1")
        if start < 0 or start > 0xFFFF:
            raise ValueError("start 必须在 0 到 65535 之间")
        if count <= 0 or count > SERVER_ADJUSTED_BAR_BATCH_SIZE:
            raise ValueError(f"count 必须在 1 到 {SERVER_ADJUSTED_BAR_BATCH_SIZE} 之间")
        if adjust_mode in [3, 4] and not anchor_date_raw:
            raise ValueError("定点复权必须提供 anchor_date")
        if category == 13 and adjust_mode != 0:
            raise ValueError("通达信秒线不支持服务端复权, adjust 必须为 none")

        if isinstance(code, str):
            try:
                code = code.encode("ascii")
            except UnicodeEncodeError as ex:
                raise ValueError("股票代码必须是 6 位 ASCII 字符") from ex

        if not isinstance(code, bytes) or len(code) != 6 or not code.isascii():
            raise ValueError("股票代码必须是 6 位 ASCII 字符")

        self.category = category
        data = struct.pack(
            "<H6sHHHHHI20s",
            market,
            code,
            category,
            period_param,
            start,
            count,
            adjust_mode,
            anchor_date_raw,
            b"\x00" * 20,
        )
        length = len(data) + 2
        self.send_pkg = struct.pack(
            "<HIHHH",
            0x010C,
            0x01016408,
            length,
            length,
            0x052D,
        ) + data

    def parseResponse(self, body_buf):
        if self.category != 13:
            return super().parseResponse(body_buf)

        pos = 0
        (ret_count,) = struct.unpack("<H", body_buf[0:2])
        pos += 2
        klines = []
        pre_diff_base = 0
        epoch = datetime(2003, 12, 31)

        for _ in range(ret_count):
            (seconds_since_epoch,) = struct.unpack("<I", body_buf[pos : pos + 4])
            item_time = epoch + timedelta(seconds=seconds_since_epoch)
            pos += 4

            price_open_diff, pos = get_price(body_buf, pos)
            price_close_diff, pos = get_price(body_buf, pos)
            price_high_diff, pos = get_price(body_buf, pos)
            price_low_diff, pos = get_price(body_buf, pos)

            (vol_raw,) = struct.unpack("<I", body_buf[pos : pos + 4])
            vol = get_volume(vol_raw)
            pos += 4
            (amount_raw,) = struct.unpack("<I", body_buf[pos : pos + 4])
            amount = get_volume(amount_raw)
            pos += 4

            open_ = self._cal_price1000(price_open_diff, pre_diff_base)
            price_open_diff += pre_diff_base
            close = self._cal_price1000(price_open_diff, price_close_diff)
            high = self._cal_price1000(price_open_diff, price_high_diff)
            low = self._cal_price1000(price_open_diff, price_low_diff)
            pre_diff_base = price_open_diff + price_close_diff

            klines.append(
                OrderedDict(
                    [
                        ("open", open_),
                        ("close", close),
                        ("high", high),
                        ("low", low),
                        ("vol", vol),
                        ("amount", amount),
                        ("year", item_time.year),
                        ("month", item_time.month),
                        ("day", item_time.day),
                        ("hour", item_time.hour),
                        ("minute", item_time.minute),
                        ("second", item_time.second),
                        ("datetime", item_time.strftime("%Y-%m-%d %H:%M:%S")),
                    ]
                )
            )

        return klines


__all__ = [
    "ADJUST_MODES",
    "GetServerAdjustedSecurityBarsCmd",
    "SERVER_ADJUSTED_BAR_BATCH_SIZE",
    "normalize_adjust",
    "normalize_anchor_date",
]
