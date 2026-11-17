from datetime import datetime as real_datetime

import pytest

from mootdx._protocol.exceptions import ValidationException
from mootdx.exceptions import MootdxDataException
from mootdx.quotes import StdQuotes


def _bar(marker):
    return {
        'open': 10.0,
        'close': 10.0,
        'high': 10.0,
        'low': 10.0,
        'vol': 100.0,
        'amount': 1000.0,
        'datetime': '2024-06-03 15:00',
        'marker': marker,
    }


def _ordinary_client(responses):
    class Client:
        def __init__(self):
            self.responses = iter(responses)
            self.calls = []

        def get_security_bars(self, category, market, symbol, start, count):
            self.calls.append((category, market, symbol, start, count))
            return next(self.responses)

    quotes = object.__new__(StdQuotes)
    quotes.client = Client()
    quotes.server = ('116.205.183.150', 7709)
    quotes.timeout = 6
    return quotes


def test_std_quotes_rejects_initial_connection_failure(monkeypatch):
    class FailedClient:
        def __init__(self, **kwargs):
            self.client = None

        def connect(self, ip, port, time_out):
            return False

        def close(self):
            pass

    config = {
        'SERVER': {'HQ': [('测试主站', '127.0.0.1', 7709)]},
        'BESTIP': {'HQ': ('127.0.0.1', 7709)},
    }
    monkeypatch.setattr('mootdx.quotes.config.setup', lambda: None)
    monkeypatch.setattr('mootdx.quotes.config.set', lambda *args: None)
    monkeypatch.setattr('mootdx.quotes.config.get', lambda key: config[key])
    monkeypatch.setattr('mootdx.quotes.TdxHq_API', FailedClient)

    with pytest.raises(MootdxDataException, match='标准行情服务器连接失败'):
        StdQuotes(server=('127.0.0.1', 7709))


def test_quotes_rejects_protocol_validation_failure():
    class Client:
        def get_security_quotes(self, symbols):
            raise ValidationException('broken payload')

    client = object.__new__(StdQuotes)
    client.client = Client()

    with pytest.raises(MootdxDataException, match='实时行情请求或解析失败'):
        client.quotes('600036')


def test_bars_rejects_failed_single_response():
    client = _ordinary_client([None])

    with pytest.raises(MootdxDataException, match='K线 请求失败'):
        client.bars(symbol='600036', frequency='day', offset=1)


def test_bars_rejects_failed_later_page_without_returning_partial_data(monkeypatch):
    client = _ordinary_client([[_bar(index) for index in range(800)], None])
    monkeypatch.setattr('mootdx.quotes.time.sleep', lambda seconds: None)

    with pytest.raises(MootdxDataException, match='K线分页 请求失败'):
        client.bars(symbol='600036', frequency='day', offset=801)


def test_bars_keeps_legal_history_exhaustion_and_attaches_lineage(monkeypatch):
    client = _ordinary_client([[_bar(index) for index in range(800)], []])
    monkeypatch.setattr('mootdx.quotes.time.sleep', lambda seconds: None)

    result = client.bars(symbol='600036', frequency='day', offset=801)

    assert len(result) == 800
    metadata = result.attrs['mootdx']
    assert metadata['instrument_id'] == 'SH.600036'
    assert metadata['category'] == 9
    assert metadata['requested_count'] == 801
    assert metadata['returned_count'] == 800
    assert metadata['source_server'] == '116.205.183.150:7709'
    assert metadata['volume_semantics'] == 'tdx_protocol_native_unadjusted'
    assert metadata['timezone'] == 'Asia/Shanghai'


def test_bars_preserves_day_and_days_protocol_categories():
    day = _ordinary_client([[_bar('day')]]).bars(symbol='600036', frequency='day', offset=1)
    days = _ordinary_client([[_bar('days')]]).bars(symbol='600036', frequency='days', offset=1)

    assert day.attrs['mootdx']['category'] == 9
    assert days.attrs['mootdx']['category'] == 4
    assert day.attrs['mootdx']['fact_table_eligible'] is True
    assert days.attrs['mootdx']['fact_table_eligible'] is False
    assert day.iloc[0].volume == 100.0
    assert days.iloc[0].volume == 100.0


def test_minute_uses_asia_shanghai_calendar_date(monkeypatch):
    class FrozenDateTime:
        @classmethod
        def now(cls, tz=None):
            assert str(tz) == 'Asia/Shanghai'
            return real_datetime(2026, 7, 22, 0, 30, tzinfo=tz)

    client = object.__new__(StdQuotes)
    calls = []
    client.minutes = lambda symbol, date, **kwargs: calls.append((symbol, date)) or date
    monkeypatch.setattr('mootdx.quotes.datetime', FrozenDateTime)

    assert client.minute(symbol='600036') == '20260722'
    assert calls == [('600036', '20260722')]


def test_minutes_metadata_keeps_requested_date():
    class Client:
        def get_history_minute_time_data(self, market, code, date):
            return []

    client = object.__new__(StdQuotes)
    client.client = Client()
    client.server = ('116.205.183.150', 7709)

    result = client.minutes(symbol='600036', date='20260721')

    assert result.attrs['mootdx']['request_date'] == '20260721'
    assert result.attrs['mootdx']['fact_table_eligible'] is False


def test_transaction_metadata_keeps_history_date_without_inventing_current_date():
    class Client:
        def get_transaction_data(self, market, symbol, start, offset):
            return []

        def get_history_transaction_data(self, market, symbol, start, offset, date):
            return []

    client = object.__new__(StdQuotes)
    client.client = Client()
    client.server = ('116.205.183.150', 7709)

    current = client.transaction(symbol='600036', offset=1)
    history = client.transactions(symbol='600036', date='20260721', offset=1)

    assert current.attrs['mootdx']['request_date'] is None
    assert history.attrs['mootdx']['request_date'] == '20260721'
