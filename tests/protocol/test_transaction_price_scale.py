from unittest import mock

import pytest

from mootdx._protocol.parser.std.get_history_minute_time_data import GetHistoryMinuteTimeData
from mootdx._protocol.parser.std.get_history_transaction_data import GetHistoryTransactionData
from mootdx._protocol.parser.std.get_minute_time_data import GetMinuteTimeData
from mootdx._protocol.parser.std.get_transaction_data import GetTransactionData


@pytest.mark.parametrize(
    ('code', 'price_raw', 'expected'),
    [
        ('510300', 4787, 4.787),
        ('526070', 982, 0.982),
        ('530880', 1051, 1.051),
        ('551900', 101580, 101.58),
        ('600036', 3799, 37.99),
    ],
)
def test_current_transaction_uses_security_price_scale(code, price_raw, expected):
    parser = GetTransactionData(client=None)
    parser.setParams(market=1, code=code, start=0, count=1)

    with mock.patch(
        'mootdx._protocol.parser.std.get_transaction_data.get_time',
        return_value=(9, 31, 2),
    ), mock.patch(
        'mootdx._protocol.parser.std.get_transaction_data.get_price',
        side_effect=[(price_raw, 3), (100, 4), (1, 5), (0, 6), (0, 7)],
    ):
        result = parser.parseResponse(b'\x01\x00')

    assert result[0]['price'] == pytest.approx(expected)


@pytest.mark.parametrize(
    ('code', 'price_raw', 'expected'),
    [
        ('510300', 4787, 4.787),
        ('526070', 982, 0.982),
        ('530880', 1051, 1.051),
        ('551900', 101580, 101.58),
        ('600036', 3799, 37.99),
    ],
)
def test_history_transaction_uses_security_price_scale(code, price_raw, expected):
    parser = GetHistoryTransactionData(client=None)
    parser.setParams(market=1, code=code, start=0, count=1, date=20260721)

    with mock.patch(
        'mootdx._protocol.parser.std.get_history_transaction_data.get_time',
        return_value=(9, 31, 6),
    ), mock.patch(
        'mootdx._protocol.parser.std.get_history_transaction_data.get_price',
        side_effect=[(price_raw, 7), (100, 8), (0, 9), (0, 10)],
    ):
        result = parser.parseResponse(b'\x01\x00\x00\x00\x00\x00')

    assert result[0]['price'] == pytest.approx(expected)


@pytest.mark.parametrize(
    ('parser_class', 'module_name', 'history'),
    [
        (GetMinuteTimeData, 'get_minute_time_data', False),
        (GetHistoryMinuteTimeData, 'get_history_minute_time_data', True),
    ],
)
@pytest.mark.parametrize(
    ('code', 'price_raw', 'expected'),
    [
        ('510300', 4787, 4.787),
        ('526070', 982, 0.982),
        ('530880', 1051, 1.051),
        ('551900', 101580, 101.58),
        ('600036', 3799, 37.99),
    ],
)
def test_minute_data_uses_security_price_scale(parser_class, module_name, history, code, price_raw, expected):
    parser = parser_class(client=None)
    if history:
        parser.setParams(market=1, code=code, date=20260721)
        payload = b'\x01\x00\x00\x00\x00\x00'
    else:
        parser.setParams(market=1, code=code)
        payload = b'\x01\x00\x00\x00'

    with mock.patch(
        f'mootdx._protocol.parser.std.{module_name}.get_price',
        side_effect=[(price_raw, 7), (0, 8), (100, 9)],
    ):
        result = parser.parseResponse(payload)

    assert result[0]['price'] == pytest.approx(expected)
