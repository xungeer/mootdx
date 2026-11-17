"""Offline public connection contracts; no server discovery or network calls."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pandas as pd
import pytest

import mootdx.quotes as quotes_module
from mootdx.exceptions import MootdxDataException
from mootdx.quotes import BaseQuotes, Quotes, check_empty


class OldProtocolClient:
    """A minimal protocol double with only the historical constructor options."""

    def __init__(self, heartbeat=False, auto_retry=False, raise_exception=False, multithread=False):
        self.options = dict(heartbeat=heartbeat, auto_retry=auto_retry,
                            raise_exception=raise_exception, multithread=multithread)
        self.client = None
        self.connect_options = []

    def connect(self, ip, port, time_out=5):
        self.endpoint = (ip, port)
        self.connect_options.append(time_out)
        self.client = SimpleNamespace(_closed=False)
        return self

    def close(self):
        self.client = None


class ProtocolClient(OldProtocolClient):
    def __init__(self, handshake='minimal', heartbeat_interval=10.0, max_retries=None, **kwargs):
        super().__init__(**kwargs)
        self.options.update(handshake=handshake, heartbeat_interval=heartbeat_interval)
        if max_retries is not None:
            self.options['max_retries'] = max_retries
        self.last_error = None

    def reconnect(self):
        return self.connect(*self.endpoint, time_out=self.connect_options[-1])


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('explicit endpoints must not access or change global configuration')

    monkeypatch.setattr(quotes_module, 'TdxHq_API', ProtocolClient)
    monkeypatch.setattr(quotes_module, 'TdxExHq_API', ProtocolClient)
    monkeypatch.setattr(quotes_module.config, 'setup', forbidden)
    monkeypatch.setattr(quotes_module.config, 'get', forbidden)
    monkeypatch.setattr(quotes_module.config, 'set', forbidden)
    monkeypatch.setattr(quotes_module, 'check_server', forbidden)


def test_explicit_endpoints_and_options_are_isolated_between_concurrent_clients():
    def create(i):
        return Quotes.factory(server=('127.0.0.1', 7709 + i), timeout=i + 2,
                              handshake=['single', 'minimal'][i], heartbeat_interval=i + 3,
                              heartbeat=True, multithread=True, max_retries=i)

    with ThreadPoolExecutor(max_workers=2) as executor:
        clients = list(executor.map(create, range(2)))
    try:
        assert [q.client.endpoint for q in clients] == [('127.0.0.1', 7709), ('127.0.0.1', 7710)]
        assert [q.client.options['handshake'] for q in clients] == ['single', 'minimal']
        assert [q.client.options['heartbeat_interval'] for q in clients] == [3, 4]
        assert [q.client.options['max_retries'] for q in clients] == [0, 1]
        assert all(q.client.options['multithread'] for q in clients)
        clients[0].close()
        assert clients[0].closed and not clients[1].closed
        assert clients[0].reconnect() is clients[0].client
        assert not clients[0].closed
        assert clients[0].client.connect_options == [2, 2]
        assert clients[1].client.connect_options == [3]
    finally:
        for q in clients:
            q.close()


@pytest.mark.parametrize('market,key,port', [('std', 'HQ', 7709), ('ext', 'EX', 7720)])
@pytest.mark.parametrize('saved', [True, False])
def test_unspecified_endpoint_uses_saved_or_default_configuration(monkeypatch, market, key, port, saved):
    setup_calls = []
    settings = {'BESTIP': {key: ['127.0.0.2', port] if saved else ''},
                'SERVER': {key: [('fixture', '127.0.0.3', port)]}}
    monkeypatch.setattr(quotes_module.config, 'setup', lambda: setup_calls.append(True))
    monkeypatch.setattr(quotes_module.config, 'get', settings.get)
    q = Quotes.factory(market=market)
    try:
        assert q.server == ('127.0.0.2' if saved else '127.0.0.3', port)
        assert q.client.endpoint == q.server
        assert setup_calls == [True]
    finally:
        q.close()


def test_explicit_bestip_remains_opt_in_without_replacing_explicit_endpoint(monkeypatch):
    scans = []
    monkeypatch.setattr(quotes_module, 'check_server', lambda **kwargs: scans.append(kwargs))
    q = Quotes.factory(server=('127.0.0.1', 7709), bestip=True)
    try:
        assert scans == [{'sync': False}]
        assert q.client.endpoint == ('127.0.0.1', 7709)
    finally:
        q.close()


@pytest.mark.parametrize('market,attribute', [('std', 'TdxHq_API'), ('ext', 'TdxExHq_API')])
def test_historical_constructor_and_reconnect_work_with_old_protocol(monkeypatch, market, attribute):
    monkeypatch.setattr(quotes_module, attribute, OldProtocolClient)
    q = Quotes.factory(market=market, server=('127.0.0.1', 7709), timeout=2.5)
    try:
        assert q.client.options == dict(heartbeat=False, auto_retry=True,
                                        raise_exception=False, multithread=False)
        assert q.last_error is None
        assert q.reconnect() is q.client
        assert q.client.connect_options == [2.5]
        q.close()
        q.close()
        assert q.closed
        assert q.reconnect() is q.client
        assert q.client.connect_options == [2.5, 2.5]
    finally:
        q.close()


@pytest.mark.parametrize('option', [{'handshake': 'minimal'}, {'heartbeat_interval': 2}, {'max_retries': 1}])
def test_unsupported_new_options_fail_explicitly_on_old_protocol(monkeypatch, option):
    monkeypatch.setattr(quotes_module, 'TdxHq_API', OldProtocolClient)
    with pytest.raises(TypeError):
        Quotes.factory(server=('127.0.0.1', 7709), **option)


def test_extended_market_keeps_its_own_handshake_and_accepts_connection_options():
    q = Quotes.factory(market='ext', server=('127.0.0.1', 7720), timeout=1.25,
                       heartbeat=True, auto_retry=False, raise_exception=True,
                       multithread=True, heartbeat_interval=3, quiet=True)
    try:
        assert q.client.options == dict(heartbeat=True, auto_retry=False, raise_exception=True,
                                        multithread=True, heartbeat_interval=3, handshake='minimal')
        assert q.client.connect_options == [1.25]
    finally:
        q.close()


def test_extended_market_rejects_standard_handshake_configuration():
    with pytest.raises(TypeError, match='standard market'):
        Quotes.factory(market='ext', server=('127.0.0.1', 7720), handshake='minimal')


@pytest.mark.parametrize('market,attribute', [('std', 'TdxHq_API'), ('ext', 'TdxExHq_API')])
def test_connection_failures_preserve_standard_strict_and_extended_compatibility_policies(monkeypatch, market, attribute):
    error = OSError('fixture connection failure')

    class FailingClient(ProtocolClient):
        def connect(self, *args, **kwargs):
            self.last_error = error
            if self.options['raise_exception']:
                raise error
            return False

    monkeypatch.setattr(quotes_module, attribute, FailingClient)
    if market == 'std':
        with pytest.raises(MootdxDataException, match='标准行情服务器连接失败') as caught:
            Quotes.factory(market=market, server=('127.0.0.1', 7709))
        assert caught.value.__cause__ is error
    else:
        q = Quotes.factory(market=market, server=('127.0.0.1', 7709))
        assert q.closed
        assert q.last_error is error
        q.close()
    with pytest.raises(OSError, match='fixture connection failure'):
        Quotes.factory(market=market, server=('127.0.0.1', 7709), raise_exception=True)


def test_closed_and_cleanup_are_safe_before_initialization():
    q = BaseQuotes.__new__(BaseQuotes)
    assert q.closed
    assert q.last_error is None
    assert q.reconnect() is False
    q.close()


def test_old_extended_protocol_setup_failure_keeps_compatibility_and_closes_socket(monkeypatch):
    error = OSError('old protocol setup failed')
    clients = []

    class OldSetupFailure(OldProtocolClient):
        def connect(self, *args, **kwargs):
            super().connect(*args, **kwargs)
            clients.append(self)
            raise error

    monkeypatch.setattr(quotes_module, 'TdxExHq_API', OldSetupFailure)
    q = Quotes.factory(market='ext', server=('127.0.0.1', 7720))
    assert q.closed
    assert q.last_error is error
    assert clients[0].client is None
    with pytest.raises(OSError, match='old protocol setup failed'):
        Quotes.factory(market='ext', server=('127.0.0.1', 7720), raise_exception=True)
    assert clients[1].client is None


def test_empty_check_is_independent_of_the_last_constructed_client():
    assert check_empty(pd.DataFrame())
    assert check_empty([])
    assert check_empty(None)
    assert not check_empty(pd.DataFrame({'zero': [0], 'false': [False]}))
    assert not check_empty([0])


def test_standard_default_strategy_is_owned_by_bundled_protocol():
    q = Quotes.factory(server=('127.0.0.1', 7709))
    try:
        assert q.client.options['handshake'] == 'minimal'
    finally:
        q.close()


def test_online_verifier_defaults_to_no_import_or_network(monkeypatch, capsys):
    import importlib
    import runpy
    import socket
    import sys
    from pathlib import Path

    def forbidden(*args, **kwargs):
        raise AssertionError('default verification must not import runtime or use sockets')

    monkeypatch.setattr(importlib, 'import_module', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    script = Path(__file__).parents[2] / 'scripts/verify/verify_connection_lifecycle.py'
    monkeypatch.setattr(sys, 'argv', [str(script)])
    with pytest.raises(SystemExit) as caught:
        runpy.run_path(str(script), run_name='__main__')
    assert caught.value.code == 0
    assert 'Offline: no network requests made.' in capsys.readouterr().out


def test_extended_failed_connect_remains_diagnostic_without_protocol_last_error(monkeypatch):
    clients = []

    class FailedClient(OldProtocolClient):
        def connect(self, *args, **kwargs):
            super().connect(*args, **kwargs)
            clients.append(self)
            return False

    monkeypatch.setattr(quotes_module, 'TdxExHq_API', FailedClient)
    q = Quotes.factory(market='ext', server=('127.0.0.1', 7720))
    assert q.closed
    assert clients[0].client is None
    assert isinstance(q.last_error, MootdxDataException)
    assert '扩展行情服务器连接失败' in str(q.last_error)
