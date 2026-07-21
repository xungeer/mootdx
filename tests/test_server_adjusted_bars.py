from datetime import datetime
from datetime import timedelta

import pytest

from mootdx.adjusted import normalize_period
from mootdx.consts import FREQUENCY as PUBLIC_FREQUENCY
from mootdx.quotes import StdQuotes
from mootdx.utils import FREQUENCY as RUNTIME_FREQUENCY


@pytest.mark.parametrize(
    ('frequency', 'expected'),
    [
        ('5m', (0, 1)),
        ('60m', (3, 1)),
        ('days', (4, 1)),
        ('ex_1m', (7, 1)),
        ('1m', (8, 1)),
        ('day', (9, 1)),
        ('10m', (8, 10)),
        ('2d', (9, 2)),
        ('5s', (13, 5)),
        ('32767m', (8, 32767)),
        ((8, 20), (8, 20)),
        (11, (11, 1)),
    ],
)
def test_period_normalization(frequency, expected):
    assert normalize_period(frequency) == expected


@pytest.mark.parametrize('frequency', ['invalid', '0m', '32768d', True, 12, (8, 0), (5, 2), 1.5])
def test_period_normalization_rejects_unsupported_values(frequency):
    with pytest.raises(ValueError, match='周期'):
        normalize_period(frequency)


def test_public_frequency_table_matches_runtime_and_protocol_categories():
    assert PUBLIC_FREQUENCY == RUNTIME_FREQUENCY
    assert [normalize_period(frequency)[0] for frequency in PUBLIC_FREQUENCY] == list(range(12))


def test_adjusted_bars_routes_adjustment_to_tdx_server(monkeypatch):
    class LegacyClient:
        auto_retry = True
        raise_exception = False

        def get_security_bars(self, *args, **kwargs):
            raise AssertionError('复权请求不应走旧版 K 线接口')

        def close(self):
            pass

    class ServerClient:
        instances = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.calls = []
            self.closed = False
            self.instances.append(self)

        def connect(self, ip, port, time_out):
            self.connection = (ip, port, time_out)
            return self

        def get_server_adjusted_bars(self, *args):
            self.calls.append(args)
            return [
                {
                    'open': 10.0,
                    'close': 10.2,
                    'high': 10.3,
                    'low': 9.9,
                    'vol': 100.0,
                    'amount': 1000.0,
                    'year': 2024,
                    'month': 6,
                    'day': 3,
                    'hour': 15,
                    'minute': 0,
                    'datetime': '2024-06-03 15:00',
                }
            ]

        def close(self):
            self.closed = True

    def fail_external_adjust(*args, **kwargs):
        raise AssertionError('复权请求不应访问外部复权因子')

    monkeypatch.setattr('mootdx.quotes.ServerAdjustedTdxHqAPI', ServerClient)
    monkeypatch.setattr('mootdx.utils.adjust.to_adjust', fail_external_adjust)

    client = object.__new__(StdQuotes)
    client.client = LegacyClient()
    client.server = ('116.205.183.150', 7709)
    client.timeout = 6

    result = client.adjusted_bars(symbol='600036', frequency=9, offset=1, adjust='qfq')

    server_client = ServerClient.instances[0]
    assert server_client.connection == ('116.205.183.150', 7709, 6)
    assert server_client.calls == [(9, 1, '600036', 0, 1, 1, 0, 1)]
    assert server_client.closed is True
    assert result.iloc[0].close == 10.2
    assert result.iloc[0].volume == 100.0
    assert 'factor' not in result.columns


@pytest.mark.parametrize(
    ('adjust', 'expected_mode'),
    [('fixed_qfq', 3), ('fixed_hfq', 4)],
)
def test_adjusted_bars_normalizes_and_forwards_fixed_anchor_date(monkeypatch, adjust, expected_mode):
    class LegacyClient:
        auto_retry = False
        raise_exception = True

    class ServerClient:
        calls = []

        def __init__(self, **kwargs):
            pass

        def connect(self, ip, port, time_out):
            return self

        def get_server_adjusted_bars(self, *args):
            self.calls.append(args)
            return []

        def close(self):
            pass

    monkeypatch.setattr('mootdx.quotes.ServerAdjustedTdxHqAPI', ServerClient)

    client = object.__new__(StdQuotes)
    client.client = LegacyClient()
    client.server = ('116.205.183.150', 7709)
    client.timeout = 6

    client.adjusted_bars(
        symbol='600036',
        frequency='15m',
        offset=1,
        adjust=adjust,
        anchor_date=datetime(2024, 6, 3, 12, 30),
    )

    assert ServerClient.calls == [(1, 1, '600036', 0, 1, expected_mode, 20240603, 1)]


def test_adjusted_bars_keeps_paged_history_in_time_order(monkeypatch):
    class LegacyClient:
        auto_retry = False
        raise_exception = True

        def close(self):
            pass

    class ServerClient:
        instances = []

        def __init__(self, **kwargs):
            self.calls = []
            self.instances.append(self)

        def connect(self, ip, port, time_out):
            return self

        def get_server_adjusted_bars(
            self,
            category,
            market,
            code,
            start,
            count,
            adjust,
            anchor_date,
            period_param,
        ):
            self.calls.append((start, count, adjust, anchor_date, period_param))
            if start == 0:
                return [_bar(f'new-{index}') for index in range(800)]
            return [_bar('old')]

        def close(self):
            pass

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

    monkeypatch.setattr('mootdx.quotes.ServerAdjustedTdxHqAPI', ServerClient)
    monkeypatch.setattr('mootdx.quotes.time.sleep', lambda seconds: None)

    client = object.__new__(StdQuotes)
    client.client = LegacyClient()
    client.server = ('116.205.183.150', 7709)
    client.timeout = 6

    result = client.adjusted_bars(symbol='600036', offset=801, adjust='hfq')

    server_client = ServerClient.instances[0]
    assert server_client.calls == [(0, 800, 2, 0, 1), (800, 1, 2, 0, 1)]
    assert result.iloc[0].marker == 'old'
    assert result.iloc[-1].marker == 'new-799'


def test_adjusted_second_bars_skip_inclusive_page_boundary(monkeypatch):
    class LegacyClient:
        auto_retry = False
        raise_exception = True

    class ServerClient:
        instances = []

        def __init__(self, **kwargs):
            self.calls = []
            self.instances.append(self)

        def connect(self, ip, port, time_out):
            return self

        def get_server_adjusted_bars(
            self,
            category,
            market,
            code,
            start,
            count,
            adjust,
            anchor_date,
            period_param,
        ):
            self.calls.append((start, count, period_param))
            newest_position = 0 if start == 0 else start - 1
            return [
                {
                    'open': 10.0,
                    'close': 10.0,
                    'high': 10.0,
                    'low': 10.0,
                    'vol': 100.0,
                    'amount': 1000.0,
                    'datetime': (datetime(2024, 6, 3, 15) - timedelta(seconds=position * 5)).isoformat(' '),
                    'position': position,
                }
                for position in range(newest_position + count - 1, newest_position - 1, -1)
            ]

        def close(self):
            pass

    monkeypatch.setattr('mootdx.quotes.ServerAdjustedTdxHqAPI', ServerClient)
    monkeypatch.setattr('mootdx.quotes.time.sleep', lambda seconds: None)

    client = object.__new__(StdQuotes)
    client.client = LegacyClient()
    client.server = ('116.205.183.150', 7709)
    client.timeout = 6

    result = client.adjusted_bars(symbol='600036', frequency='5s', offset=1601, adjust='none')

    assert len(result) == 1601
    assert result.position.tolist() == list(range(1600, -1, -1))
    assert result.index.is_monotonic_increasing
    assert result.index.is_unique
    assert ServerClient.instances[0].calls == [(0, 800, 5), (801, 800, 5), (1601, 1, 5)]


@pytest.mark.parametrize(
    ('kwargs', 'message'),
    [
        ({'frequency': 'not-a-period'}, '周期'),
        ({'start': -1}, 'start'),
        ({'start': True}, 'start'),
        ({'offset': 0}, 'offset'),
        ({'offset': 1.5}, 'offset'),
        ({'offset': 65601}, '最多可分页'),
        ({'start': 65535, 'offset': 801}, '最多可分页'),
        ({'symbol': 'sh600036'}, '股票代码'),
        ({'frequency': '5s', 'adjust': 'qfq'}, '秒线'),
    ],
)
def test_adjusted_bars_validates_request_before_connecting(kwargs, message):
    client = object.__new__(StdQuotes)

    with pytest.raises(ValueError, match=message):
        client.adjusted_bars(**kwargs)
