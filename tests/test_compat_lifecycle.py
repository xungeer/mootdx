"""Legacy MooBaseSocketClient aliases share the bundled socket lifecycle."""
import socket
import threading

import pytest

from mootdx.contrib import compat
from mootdx._protocol import base_socket_client
from mootdx._protocol.exceptions import TdxConnectionError, TdxHandshakeError


class ScriptedSocket:
    def __init__(self, *, connect_error=None, shutdown_error=None):
        self.connect_error = connect_error
        self.shutdown_error = shutdown_error
        self.closed = False
        self.close_count = 0

    def settimeout(self, value):
        self.timeout = value

    def bind(self, endpoint):
        self.bound = endpoint

    def connect(self, endpoint):
        self.endpoint = endpoint
        if self.connect_error is not None:
            raise self.connect_error

    def shutdown(self, how):
        if self.shutdown_error is not None:
            raise self.shutdown_error

    def close(self):
        self.closed = True
        self.close_count += 1


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Compatibility tests must not access the network')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)


def install_sockets(monkeypatch, *sockets):
    remaining = iter(sockets)
    factory = lambda *args: next(remaining)
    # The legacy implementation owns a local alias; the corrected wrapper uses
    # the shared factory. Cover either while reproducing the old behavior.
    monkeypatch.setattr(compat, 'TrafficStatSocket', factory, raising=False)
    monkeypatch.setattr(base_socket_client, 'TrafficStatSocket', factory)


def test_legacy_connect_aliases_record_state_and_reconnect_parameters(monkeypatch):
    first, second = ScriptedSocket(), ScriptedSocket()
    install_sockets(monkeypatch, first, second)
    api = compat.MooBaseSocketClient()
    try:
        assert api.connect('192.0.2.1', 7710, 1.25, 0, '127.0.0.1') is api
        assert not api.closed
        assert first.bound == ('127.0.0.1', 0)
        assert first.timeout == 1.25
        assert api._connect_params == dict(ip='192.0.2.1', port=7710, time_out=1.25,
                                          bind_port=0, bind_ip='127.0.0.1')
        api.close()
        assert api.closed and first.close_count == 1
        assert api.reconnect() is api
        assert not api.closed
        assert second.endpoint == first.endpoint
        assert second.timeout == first.timeout
        assert second.bound == first.bound
    finally:
        api.close()
    assert first.close_count == second.close_count == 1


def test_explicit_reconnect_after_legacy_connect_uses_shared_lifecycle(monkeypatch):
    first, second = ScriptedSocket(), ScriptedSocket()
    install_sockets(monkeypatch, first, second)
    api = compat.MooBaseSocketClient()
    try:
        api.connect()
        assert api.reconnect() is api
        assert second.endpoint == ('101.227.73.20', 7709)
        assert first.close_count == 1
    finally:
        api.close()


def test_legacy_heartbeat_runs_and_close_joins_thread(monkeypatch):
    sock = ScriptedSocket()
    install_sockets(monkeypatch, sock)
    beat = threading.Event()

    class HeartbeatClient(compat.MooBaseSocketClient):
        def do_heartbeat(self):
            beat.set()

    api = HeartbeatClient()
    api.heartbeat = True
    api.heartbeat_interval = 0.005
    thread = None
    try:
        api.connect('192.0.2.1')
        thread = api.heartbeat_thread
        assert beat.wait(0.5), 'legacy client heartbeat exited without sending'
    finally:
        api.close()
        if thread is not None:
            thread.join(timeout=0.5)
    assert thread is not None and not thread.is_alive()
    assert api.closed and api.client is None
    assert sock.close_count == 1


@pytest.mark.parametrize('raise_exception', [False, True])
def test_connect_failure_retains_error_and_closes_unconnected_socket(monkeypatch, raise_exception):
    cause = socket.timeout('offline scripted timeout')
    sock = ScriptedSocket(connect_error=cause, shutdown_error=OSError('not connected'))
    install_sockets(monkeypatch, sock)
    api = compat.MooBaseSocketClient()
    api.raise_exception = raise_exception
    if raise_exception:
        with pytest.raises(TdxConnectionError):
            api.connect('192.0.2.1')
    else:
        assert api.connect('192.0.2.1') is False
    assert api.last_error.original_exception is cause
    assert api.closed and api.client is None
    assert sock.close_count == 1
    api.close()
    assert sock.close_count == 1


def test_failed_custom_setup_closes_and_retains_handshake_diagnosis(monkeypatch):
    sock = ScriptedSocket()
    install_sockets(monkeypatch, sock)
    error = TdxHandshakeError('scripted setup failure', step=1, profile='custom')

    class FailedSetup(compat.MooBaseSocketClient):
        def setup(self):
            raise error

    api = FailedSetup()
    assert api.connect('192.0.2.1') is False
    assert api.last_error is error
    assert api.closed and api.client is None
    assert sock.close_count == 1
