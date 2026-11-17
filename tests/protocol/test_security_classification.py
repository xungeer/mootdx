import pytest

from mootdx._protocol.helper import get_security_coefficient
from mootdx._protocol.helper import get_security_type
from mootdx._protocol.reader import TdxDailyBarReader
from mootdx.contrib.compat import MooTdxDailyBarReader
from mootdx.consts import MARKET_BJ
from mootdx.consts import MARKET_SH
from mootdx.consts import MARKET_SZ
from mootdx.utils import get_stock_market


@pytest.mark.parametrize('code', ['526070', '530880', '551900', '570001'])
def test_shanghai_fund_prefixes_use_three_decimal_price_scale(code):
    assert get_stock_market(code) == MARKET_SH
    assert get_security_type(MARKET_SH, code) == 'SH_FUND'
    assert get_security_coefficient(MARKET_SH, code) == 0.001


@pytest.mark.parametrize('code', ['159915', '160119', '180101'])
def test_shenzhen_fund_prefixes_use_three_decimal_price_scale(code):
    assert get_stock_market(code) == MARKET_SZ
    assert get_security_type(MARKET_SZ, code) == 'SZ_FUND'
    assert get_security_coefficient(MARKET_SZ, code) == 0.001


@pytest.mark.parametrize('code', ['430047', '830799', '870299', '920971'])
def test_beijing_legacy_and_current_stock_prefixes_route_to_bj(code):
    assert get_stock_market(code) == MARKET_BJ
    assert get_security_type(MARKET_BJ, code) == 'BJ_A_STOCK'


@pytest.mark.parametrize('code', ['526070', '530880', '551900', '570001'])
def test_local_daily_readers_share_shanghai_fund_prefixes(code):
    filename = f'/tmp/sh{code}.day'
    protocol_reader = object.__new__(TdxDailyBarReader)
    compat_reader = object.__new__(MooTdxDailyBarReader)

    assert protocol_reader.get_security_type(filename) == 'SH_FUND'
    assert compat_reader.get_security_type(filename) == 'SH_FUND'


def test_unknown_security_type_does_not_silently_assume_stock_scale():
    with pytest.raises(NotImplementedError):
        get_security_coefficient(MARKET_SH, '400001')


def test_security_coefficient_accepts_protocol_bytes_code():
    assert get_security_coefficient(MARKET_SH, b'526070') == 0.001
