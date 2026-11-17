# cython: language_level=3
import struct
from collections import OrderedDict

from mootdx._protocol.parser.base import BaseParser


class GetSecurityList(BaseParser):
    def setParams(self, market, start, limit=1000):
        """
        设置参数
        :param market: 市场
        :param start: 开始位置
        :param limit: 返回数量
        """
        pkg = bytearray.fromhex("0c 01 18 64 01 01 10 00 10 00 4d 04")
        pkg.extend(struct.pack("<HIII", market, start, limit, 0))

        self.send_pkg = pkg

    def parseResponse(self, body_buf):
        if len(body_buf) < 2:
            raise ValueError("证券列表响应缺少记录数")
        (num,) = struct.unpack("<H", body_buf[:2])
        expected_size = 2 + num * 37
        if len(body_buf) < expected_size:
            raise ValueError(
                f"证券列表响应不完整: expected>={expected_size}, actual={len(body_buf)}"
            )

        pos = 2
        symbols = []

        for _ in range(num):
            one_bytes = body_buf[pos : pos + 37]

            code, volunit, name_bytes, _reversed_bytes1, decimal_point, pre_close, _reversed_bytes2 = struct.unpack(
                "<6sH16s4sBf4s", one_bytes
            )

            code = code.decode("utf-8", errors="ignore")
            name = name_bytes.decode("gbk", errors="ignore").rstrip("\x00")

            pos += 37

            rows = OrderedDict(
                [
                    ("code", code),
                    ("volunit", volunit),
                    ("decimal_point", decimal_point),
                    ("name", name),
                    ("pre_close", pre_close),
                ]
            )

            symbols.append(rows)

        return symbols
