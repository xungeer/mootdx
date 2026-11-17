# cython: language_level=3
import struct
from collections import OrderedDict

from mootdx._protocol.constants import TDXParams
from mootdx._protocol.parser.base import BaseParser


FINANCE_INFO_FORMAT = "<fHHII30f"
FINANCE_INFO_SIZE = struct.calcsize(FINANCE_INFO_FORMAT)
FINANCE_RECORD_SIZE = 7 + FINANCE_INFO_SIZE


def _encode_stock(market, code):
    if type(market) is not int or market not in (
        TDXParams.MARKET_SZ,
        TDXParams.MARKET_SH,
        TDXParams.MARKET_BJ,
    ):
        raise ValueError("market must be 0 (SZ), 1 (SH), or 2 (BJ)")

    if isinstance(code, str):
        try:
            code = code.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("code must be a 6-digit ASCII string") from exc
    elif not isinstance(code, bytes):
        raise ValueError("code must be str or bytes")

    if len(code) != 6 or not code.isdigit():
        raise ValueError("code must be a 6-digit ASCII string")
    return market, code


def _build_finance_request(all_stock):
    if all_stock is None or isinstance(all_stock, (str, bytes)):
        raise ValueError("all_stock must be a non-empty iterable of (market, code)")

    try:
        stocks = list(all_stock)
    except TypeError as exc:
        raise ValueError("all_stock must be a non-empty iterable of (market, code)") from exc

    stock_len = len(stocks)
    if stock_len == 0:
        raise ValueError("all_stock must not be empty")
    if stock_len > TDXParams.MAX_FINANCE_BATCH_SIZE:
        raise ValueError(
            f"finance batch supports at most {TDXParams.MAX_FINANCE_BATCH_SIZE} stocks"
        )

    body = bytearray(struct.pack("<H", stock_len))
    for stock in stocks:
        if not isinstance(stock, (list, tuple)) or len(stock) != 2:
            raise ValueError("each stock must be a (market, code) pair")
        market, code = _encode_stock(*stock)
        body.extend(struct.pack("<B6s", market, code))

    frame_body_length = len(body) + 2
    header = bytearray.fromhex("0c 1f 18 76 00 01")
    header.extend(
        struct.pack(
            "<HHH",
            frame_body_length,
            frame_body_length,
            0x0010,
        )
    )
    return header + body


def _parse_finance_record(record):
    if len(record) != FINANCE_RECORD_SIZE:
        raise ValueError(
            f"invalid finance record length: expected={FINANCE_RECORD_SIZE}, actual={len(record)}"
        )

    market, code = struct.unpack("<B6s", record[:7])
    if market not in (TDXParams.MARKET_SZ, TDXParams.MARKET_SH, TDXParams.MARKET_BJ):
        raise ValueError(f"invalid finance record market: {market}")
    try:
        code = code.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("invalid finance record code") from exc

    (
        liutongguben,
        province,
        industry,
        updated_date,
        ipo_date,
        zongguben,
        guojiagu,
        faqirenfarengu,
        farengu,
        bgu,
        hgu,
        zhigonggu,
        zongzichan,
        liudongzichan,
        gudingzichan,
        wuxingzichan,
        gudongrenshu,
        liudongfuzhai,
        changqifuzhai,
        zibengongjijin,
        jingzichan,
        zhuyingshouru,
        zhuyinglirun,
        yingshouzhangkuan,
        yingyelirun,
        touzishouyu,
        jingyingxianjinliu,
        zongxianjinliu,
        cunhuo,
        lirunzonghe,
        shuihoulirun,
        jinglirun,
        weifenlirun,
        baoliu1,
        baoliu2,
    ) = struct.unpack(FINANCE_INFO_FORMAT, record[7:])

    def _get_v(value):
        return value

    return OrderedDict(
        [
            ("market", market),
            ("code", code),
            ("liutongguben", _get_v(liutongguben) * 10000),
            ("province", province),
            ("industry", industry),
            ("updated_date", updated_date),
            ("ipo_date", ipo_date),
            ("zongguben", _get_v(zongguben) * 10000),
            ("guojiagu", _get_v(guojiagu) * 10000),
            ("faqirenfarengu", _get_v(faqirenfarengu) * 10000),
            ("farengu", _get_v(farengu) * 10000),
            ("bgu", _get_v(bgu) * 10000),
            ("hgu", _get_v(hgu) * 10000),
            ("zhigonggu", _get_v(zhigonggu) * 10000),
            ("zongzichan", _get_v(zongzichan) * 10000),
            ("liudongzichan", _get_v(liudongzichan) * 10000),
            ("gudingzichan", _get_v(gudingzichan) * 10000),
            ("wuxingzichan", _get_v(wuxingzichan) * 10000),
            ("gudongrenshu", _get_v(gudongrenshu)),
            ("liudongfuzhai", _get_v(liudongfuzhai) * 10000),
            ("changqifuzhai", _get_v(changqifuzhai) * 10000),
            ("zibengongjijin", _get_v(zibengongjijin) * 10000),
            ("jingzichan", _get_v(jingzichan) * 10000),
            ("zhuyingshouru", _get_v(zhuyingshouru) * 10000),
            ("zhuyinglirun", _get_v(zhuyinglirun) * 10000),
            ("yingshouzhangkuan", _get_v(yingshouzhangkuan) * 10000),
            ("yingyelirun", _get_v(yingyelirun) * 10000),
            ("touzishouyu", _get_v(touzishouyu) * 10000),
            ("jingyingxianjinliu", _get_v(jingyingxianjinliu) * 10000),
            ("zongxianjinliu", _get_v(zongxianjinliu) * 10000),
            ("cunhuo", _get_v(cunhuo) * 10000),
            ("lirunzonghe", _get_v(lirunzonghe) * 10000),
            ("shuihoulirun", _get_v(shuihoulirun) * 10000),
            ("jinglirun", _get_v(jinglirun) * 10000),
            ("weifenpeilirun", _get_v(weifenlirun) * 10000),
            ("meigujingzichan", _get_v(baoliu1)),
            ("baoliu2", _get_v(baoliu2)),
        ]
    )


def _parse_finance_response(body_buf):
    if len(body_buf) < 2:
        raise ValueError("finance response is missing the record count")

    (record_count,) = struct.unpack("<H", body_buf[:2])
    expected_size = 2 + record_count * FINANCE_RECORD_SIZE
    if len(body_buf) != expected_size:
        raise ValueError(
            f"invalid finance response length: expected={expected_size}, actual={len(body_buf)}"
        )

    records = []
    pos = 2
    for _ in range(record_count):
        record = body_buf[pos : pos + FINANCE_RECORD_SIZE]
        records.append(_parse_finance_record(record))
        pos += FINANCE_RECORD_SIZE
    return records


class GetFinanceInfoBatch(BaseParser):
    def setParams(self, all_stock):
        """构建最多 80 只证券的批量财务信息请求。"""
        self.send_pkg = _build_finance_request(all_stock)

    def parseResponse(self, body_buf):
        return _parse_finance_response(body_buf)


class GetFinanceInfo(GetFinanceInfoBatch):
    def setParams(self, market, code):
        """保留单证券接口，并复用批量协议构建。"""
        super().setParams([(market, code)])

    def parseResponse(self, body_buf):
        records = super().parseResponse(body_buf)
        if len(records) != 1:
            raise ValueError(f"single finance response must contain exactly one record, got {len(records)}")
        return records[0]
