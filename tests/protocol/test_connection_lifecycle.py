"""Deterministic socket lifecycle tests; public quote servers are never used."""
import itertools
import socket
import struct
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from mootdx._protocol.base_socket_client import BaseSocketClient, last_ack_time
from mootdx._protocol.exceptions import (
    TdxConnectionError, TdxFunctionCallError, TdxHandshakeError, TdxHandshakeRejected,
    TdxResponseError, TdxTransportError, ValidationException,
)
from mootdx._protocol.exhq import TdxExHq_API
from mootdx._protocol.heartbeat import HeartBeatThread
from mootdx._protocol.parser.std.get_security_count import GetSecurityCountCmd


class ScriptedSocket:
    """Small standard/extended response server at the socket API boundary."""
    def __init__(self, *, connect_error=None, send_error=None, shutdown_error=None,
                 body=None, gate=None):
        self.connect_error = connect_error
        self.send_error = send_error
        self.shutdown_error = shutdown_error
        self.body = body
        self.gate = gate
        self.sent = threading.Event()
        self.commands = []
        self.timeout = None
        self.address = None
        self.bound = None
        self.closed = False
        self.close_count = 0
        self.pending = b""
        self.active = 0
        self.max_active = 0
        self.send_pkg_num = self.recv_pkg_num = 0
        self.send_pkg_bytes = self.recv_pkg_bytes = 0
        self.last_api_send_bytes = self.last_api_recv_bytes = 0
        self.first_pkg_send_time = None

    def settimeout(self, value):
        self.timeout = value

    def bind(self, address):
        self.bound = address

    def connect(self, address):
        self.address = address
        if self.connect_error:
            raise self.connect_error

    def send(self, request):
        if self.send_error:
            raise self.send_error
        request = bytes(request)
        self.commands.append(request)
        body = self.body
        if body is None:
            body = struct.pack("<H", 393) if request[0] == 0x0c else bytes(19) + struct.pack("<I", 393)
        if request[0] == 0x0c:
            header = bytes.fromhex("b1cb7400") + b"\x00" + request[1:5] + b"\x00" + request[10:12]
        else:
            header = bytes(12)  # Distinct extension envelope: no standard-header assumptions.
        self.pending = header + struct.pack("<HH", len(body), len(body)) + body
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.sent.set()
        return len(request)

    def recv(self, size):
        if self.gate is not None:
            assert self.gate.wait(1), "test did not release response gate"
        result, self.pending = self.pending[:size], self.pending[size:]
        if not self.pending:
            self.active -= 1
        return result

    def shutdown(self, how):
        if self.shutdown_error:
            raise self.shutdown_error

    def close(self):
        self.closed = True
        self.close_count += 1


class CountAPI(BaseSocketClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.need_setup = False
        self.beat_done = threading.Event()

    @last_ack_time
    def count(self):
        parser = GetSecurityCountCmd(self.client, lock=self.lock)
        parser.setParams(2)
        return parser.call_api()

    def do_heartbeat(self):
        result = self.count()
        if result is not None:
            self.beat_done.set()
        return result


class ZeroDelay:
    @staticmethod
    def generate():
        yield from itertools.repeat(0)


def install_sockets(monkeypatch, *sockets):
    remaining = iter(sockets)
    used = []
    def factory(*args):
        sock = next(remaining)
        used.append(sock)
        return sock
    monkeypatch.setattr("mootdx._protocol.base_socket_client.TrafficStatSocket", factory)
    return used


@pytest.mark.parametrize("raise_exception", [False, True])
def test_connect_timeout_retains_cause_and_closes_even_if_shutdown_fails(monkeypatch, raise_exception):
    cause = socket.timeout("bounded timeout")
    sock = ScriptedSocket(connect_error=cause, shutdown_error=OSError("not connected"))
    install_sockets(monkeypatch, sock)
    api = CountAPI(raise_exception=raise_exception)
    if raise_exception:
        with pytest.raises(TdxConnectionError) as result:
            api.connect("example", time_out=0.25)
        assert result.value.__cause__ is cause
    else:
        assert api.connect("example", time_out=0.25) is False
    assert api.last_error.original_exception is cause
    assert api.closed and api.client is None and sock.closed
    assert sock.close_count == 1
    api.close()
    api.close()
    assert sock.close_count == 1


@pytest.mark.parametrize("raise_exception", [False, True])
def test_setup_failure_cannot_leave_a_live_socket(monkeypatch, raise_exception):
    sock = ScriptedSocket()
    install_sockets(monkeypatch, sock)
    failure = TdxResponseError("invalid initialization frame", command=13, response=b"x")
    class BrokenSetup(BaseSocketClient):
        def setup(self):
            raise failure
    api = BrokenSetup(raise_exception=raise_exception)
    if raise_exception:
        with pytest.raises(TdxConnectionError) as caught:
            api.connect("example")
        assert caught.value.original_exception is failure
    else:
        assert api.connect("example") is False
    assert isinstance(api.last_error, TdxHandshakeError)
    assert api.last_error.status == "malformed"
    assert api.last_error.original_exception is failure
    assert api.last_error.command == 13
    assert api.last_error.response_length == 1
    assert api.last_error.response_preview == "78"
    assert api.closed and sock.closed and api.client is None


def test_heartbeat_start_failure_does_not_mask_original_error(monkeypatch):
    sock = ScriptedSocket()
    install_sockets(monkeypatch, sock)
    failure = RuntimeError("cannot start new thread")
    def fail_start(self):
        raise failure
    monkeypatch.setattr(HeartBeatThread, "start", fail_start)
    api = CountAPI(heartbeat=True, raise_exception=True)
    with pytest.raises(TdxConnectionError) as caught:
        api.connect("example")
    assert caught.value.original_exception is failure
    assert api.client is None and api.closed and sock.closed
    api.close()


def test_reconnect_preserves_timeout_bind_and_options(monkeypatch):
    first, second = ScriptedSocket(), ScriptedSocket()
    install_sockets(monkeypatch, first, second)
    api = CountAPI(max_retries=2, heartbeat_interval=12, raise_exception=True)
    assert api.connect("example", 7710, time_out=0.75, bind_port=0, bind_ip="127.0.0.1") is api
    assert api.count() == 393
    assert api.reconnect() is api
    assert first.closed and not second.closed
    assert second.address == ("example", 7710)
    assert second.timeout == 0.75
    assert second.bound == ("127.0.0.1", 0)
    assert api.heartbeat_interval == 12 and api.max_retries == 2
    assert api.count() == 393
    api.close()
    assert second.closed and api.closed


def test_network_retry_replays_request_only_on_a_new_socket(monkeypatch):
    first = ScriptedSocket(send_error=ConnectionResetError("gone"))
    second = ScriptedSocket()
    used = install_sockets(monkeypatch, first, second)
    api = CountAPI(auto_retry=True, raise_exception=True, max_retries=1)
    api.retry_strategy = ZeroDelay()
    api.connect("example", 7710, time_out=0.75, bind_port=0)
    assert api.count() == 393
    assert used == [first, second] and first.closed
    assert second.timeout == 0.75 and second.bound == ("0.0.0.0", 0)
    assert api.last_error is None
    api.close()


@pytest.mark.parametrize("raise_exception", [False, True])
def test_even_an_infinite_retry_strategy_has_a_hard_attempt_limit(monkeypatch, raise_exception):
    socks = [ScriptedSocket(send_error=ConnectionResetError("gone")) for _ in range(3)]
    used = install_sockets(monkeypatch, *socks)
    api = CountAPI(auto_retry=True, raise_exception=raise_exception, max_retries=2)
    api.retry_strategy = ZeroDelay()
    api.connect("example")
    if raise_exception:
        with pytest.raises(TdxFunctionCallError) as caught:
            api.count()
        assert caught.value.original_exception is api.last_error
        assert caught.value.__cause__ is api.last_error
    else:
        assert api.count() is None
    assert len(used) == 3 and all(s.closed for s in socks)
    assert isinstance(api.last_error, TdxTransportError)
    assert isinstance(api.last_error.original_exception, ConnectionResetError)
    assert api.closed and api.client is None


@pytest.mark.parametrize("failure", [
    TdxResponseError("malformed response", command=0x052D, response=b"\x20\x03"),
    TdxHandshakeRejected("explicit rejection", command=0x0FDB, response=b"rejected", status="rejected"),
])
@pytest.mark.parametrize("raise_exception", [False, True])
def test_protocol_and_handshake_failures_are_not_retried(monkeypatch, failure, raise_exception):
    sock = ScriptedSocket()
    used = install_sockets(monkeypatch, sock)
    class ErrorAPI(CountAPI):
        @last_ack_time
        def fail(self):
            raise failure
    api = ErrorAPI(auto_retry=True, raise_exception=raise_exception)
    api.retry_strategy = ZeroDelay()
    api.connect("example")
    if raise_exception:
        with pytest.raises(TdxFunctionCallError) as caught:
            api.fail()
        assert caught.value.__cause__ is failure
    else:
        assert api.fail() is None
    assert api.last_error is failure
    assert used == [sock] and sock.closed


def test_success_updates_ack_failure_does_not_and_last_error_is_inspectable(monkeypatch):
    sock = ScriptedSocket()
    install_sockets(monkeypatch, sock)
    api = CountAPI()
    api.connect("example")
    api.last_ack_time = -1
    api._last_ack_monotonic = -2
    assert api.count() == 393
    assert api.last_ack_time > 0 and api._last_ack_monotonic > 0
    previous = api.last_ack_time, api._last_ack_monotonic
    sock.send_error = ConnectionResetError("gone")
    assert api.count() is None
    assert (api.last_ack_time, api._last_ack_monotonic) == previous
    assert api.last_error is not None


def test_legal_zero_count_is_success_and_not_a_reconnect_trigger(monkeypatch):
    sock = ScriptedSocket(body=b"\x00\x00")
    used = install_sockets(monkeypatch, sock)
    api = CountAPI(auto_retry=True)
    api.connect("example")
    assert api.count() == 0
    assert api.last_error is None and not api.closed and used == [sock]
    api.close()


@pytest.mark.parametrize("api_class, method", [(CountAPI, "count"), (TdxExHq_API, "get_instrument_count")])
def test_whole_requests_are_serialized_even_for_extension_parsers(monkeypatch, api_class, method):
    gate = threading.Event()
    sock = ScriptedSocket(gate=gate)
    install_sockets(monkeypatch, sock)
    api = api_class(raise_exception=True)
    api.need_setup = False
    api.connect("example")
    second_started = threading.Event()
    call = getattr(api, method)
    def second():
        second_started.set()
        return call()
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(call)
        assert sock.sent.wait(1)
        two = pool.submit(second)
        assert second_started.wait(1)
        gate.set()
        assert one.result(timeout=1) == two.result(timeout=1) == 393
    assert sock.max_active == 1
    assert len(sock.commands) == 2
    api.close()


def test_two_clients_have_independent_locks_sockets_and_diagnostics(monkeypatch):
    gate = threading.Event()
    first, second = ScriptedSocket(gate=gate), ScriptedSocket()
    install_sockets(monkeypatch, first, second)
    a, b = CountAPI(raise_exception=True), CountAPI(raise_exception=True)
    a.connect("first")
    b.connect("second")
    assert a.lock is not b.lock
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(a.count)
            assert first.sent.wait(1)
            complete = pool.submit(b.count)
            assert complete.result(timeout=1) == 393
            assert not pending.done()
            gate.set()
            assert pending.result(timeout=1) == 393
        first.send_error = ConnectionResetError("first failed")
        with pytest.raises(TdxFunctionCallError):
            a.count()
        assert a.closed and not b.closed
        assert a.last_error is not None and b.last_error is None
        assert b.count() == 393
    finally:
        gate.set()
        a.close()
        b.close()


def test_active_heartbeat_is_stopped_joined_and_replaced_on_reconnect(monkeypatch):
    first, second = ScriptedSocket(), ScriptedSocket()
    install_sockets(monkeypatch, first, second)
    api = CountAPI(heartbeat=True, heartbeat_interval=0.01, raise_exception=True)
    api.connect("example")
    first_thread = api.heartbeat_thread
    assert api.beat_done.wait(1)
    assert first_thread.is_alive() and first_thread.daemon
    api.beat_done.clear()
    api.reconnect()
    second_thread = api.heartbeat_thread
    assert second_thread is not first_thread
    assert not first_thread.is_alive() and first.closed
    assert api.beat_done.wait(1)
    api.close()
    assert not second_thread.is_alive()
    assert api.heartbeat_thread is None and api.stop_event is None
    assert api.client is None and second.closed


def test_heartbeat_can_reconnect_from_its_own_thread_without_joining_itself(monkeypatch):
    first = ScriptedSocket(send_error=ConnectionResetError("idle peer closed"))
    second = ScriptedSocket()
    install_sockets(monkeypatch, first, second)
    api = CountAPI(heartbeat=True, heartbeat_interval=0.01, auto_retry=True,
                   max_retries=1, raise_exception=True)
    api.retry_strategy = ZeroDelay()
    api.connect("example", time_out=0.5)
    original = api.heartbeat_thread
    assert api.beat_done.wait(1)
    assert api.client is second and first.closed
    original.join(timeout=1)
    assert not original.is_alive()
    replacement = api.heartbeat_thread
    assert replacement is not original and replacement.is_alive()
    api.close()
    assert not replacement.is_alive()


def test_heartbeat_uses_successful_monotonic_ack_and_ignores_wall_clock(monkeypatch):
    sock = ScriptedSocket()
    install_sockets(monkeypatch, sock)
    api = CountAPI()
    api.connect("example")
    api._last_ack_monotonic = 100
    api.last_ack_time = -10**10
    class OneTick:
        def __init__(self):
            self.calls = 0
        def wait(self, interval):
            self.calls += 1
            return self.calls > 1
        def is_set(self):
            return False
    monkeypatch.setattr("mootdx._protocol.heartbeat.time.monotonic", lambda: 100.1)
    HeartBeatThread(api, OneTick(), interval=10).run()
    assert not sock.commands
    monkeypatch.setattr("mootdx._protocol.heartbeat.time.monotonic", lambda: 111)
    HeartBeatThread(api, OneTick(), interval=10).run()
    assert len(sock.commands) == 1
    assert api._last_ack_monotonic == 111
    api.close()


def test_retired_heartbeat_cannot_send_on_a_new_connection(monkeypatch):
    first, second = ScriptedSocket(), ScriptedSocket()
    install_sockets(monkeypatch, first, second)
    api = CountAPI()
    api.connect("example")
    class OneTick:
        def wait(self, interval):
            return False
        def is_set(self):
            return False
    retired = HeartBeatThread(api, OneTick(), interval=0.01)
    api.reconnect()
    api._last_ack_monotonic = 0
    retired.run()
    assert first.closed and not second.commands
    api.close()


@pytest.mark.parametrize("kwargs", [
    {"heartbeat_interval": 0}, {"heartbeat_interval": -1},
    {"heartbeat_interval": float("inf")}, {"heartbeat_interval": float("nan")},
    {"heartbeat_interval": True}, {"max_retries": -1},
    {"max_retries": 1.5}, {"max_retries": True},
])
def test_connection_options_reject_invalid_values(kwargs):
    with pytest.raises(ValidationException):
        CountAPI(**kwargs)


def test_reconnect_before_connect_is_validation_error():
    with pytest.raises(ValidationException):
        CountAPI().reconnect()


@pytest.mark.parametrize("raise_exception", [False, True])
def test_explicit_close_disables_implicit_reopening(monkeypatch, raise_exception):
    sock = ScriptedSocket()
    used = install_sockets(monkeypatch, sock)
    api = CountAPI(auto_retry=True, raise_exception=raise_exception)
    api.retry_strategy = ZeroDelay()
    api.connect("example")
    api.close()
    if raise_exception:
        with pytest.raises(TdxFunctionCallError):
            api.count()
    else:
        assert api.count() is None
    assert used == [sock] and sock.closed and api.client is None


def test_explicit_reconnect_after_close_reenables_requests(monkeypatch):
    first, second = ScriptedSocket(), ScriptedSocket()
    install_sockets(monkeypatch, first, second)
    api = CountAPI(auto_retry=True, raise_exception=True)
    api.connect("example")
    api.close()
    assert api.reconnect() is api
    assert api.count() == 393
    api.close()


def test_raw_diagnostics_keep_their_always_raise_contract(monkeypatch):
    sock = ScriptedSocket(send_error=ConnectionResetError("raw failure"))
    used = install_sockets(monkeypatch, sock)
    api = CountAPI(auto_retry=True, raise_exception=False)
    api.connect("example")
    parser = GetSecurityCountCmd(None)
    parser.setParams(2)
    with pytest.raises(TdxTransportError) as caught:
        api.send_raw_pkg(parser.send_pkg)
    assert api.last_error is caught.value
    assert used == [sock] and sock.closed and api.closed


def test_context_manager_preserves_body_exception_and_cleans_socket(monkeypatch):
    sock = ScriptedSocket(shutdown_error=OSError("already disconnected"))
    install_sockets(monkeypatch, sock)
    api = CountAPI(raise_exception=True)
    original = RuntimeError("caller failure")
    with pytest.raises(RuntimeError) as caught:
        with api.connect("example"):
            raise original
    assert caught.value is original
    assert sock.closed and api.closed and api.client is None


@pytest.mark.parametrize("raise_exception", [False, True])
def test_retry_stops_when_new_connection_returns_malformed_handshake(monkeypatch, raise_exception):
    first = ScriptedSocket(send_error=ConnectionResetError("peer disappeared"))
    second = ScriptedSocket()
    used = install_sockets(monkeypatch, first, second)
    original = TdxResponseError("wrong command", command=0x000d, response=bytes(range(40)),
                                expected_length=189, kind="unexpected_response")
    class CorruptReconnect(CountAPI):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.need_setup = True
            self.setup_count = 0
        def setup(self):
            self.setup_count += 1
            if self.setup_count > 1:
                raise original
    api = CorruptReconnect(auto_retry=True, raise_exception=raise_exception, max_retries=4)
    api.retry_strategy = ZeroDelay()
    api.connect("example")
    if raise_exception:
        with pytest.raises(TdxFunctionCallError) as caught:
            api.count()
        assert caught.value.original_exception is api.last_error
    else:
        assert api.count() is None
    assert isinstance(api.last_error, TdxHandshakeError)
    assert api.last_error.status == "malformed"
    assert api.last_error.original_exception is original
    assert api.last_error.command == 0x000d
    assert api.last_error.response_length == 40
    assert api.last_error.response_preview == bytes(range(32)).hex()
    assert api.last_error.expected_length == 189
    assert used == [first, second]
    assert first.closed and second.closed and api.closed
    assert not second.commands


class BlockedReceiveSocket(ScriptedSocket):
    """An unbounded recv is released only by shutdown, like an idle socket."""
    def __init__(self):
        super().__init__()
        self.receiving = threading.Event()
        self.interrupted = threading.Event()

    def recv(self, size):
        self.receiving.set()
        assert self.interrupted.wait(2), "close did not interrupt recv"
        return b""

    def shutdown(self, how):
        self.interrupted.set()


@pytest.mark.parametrize("raise_exception", [False, True])
def test_close_interrupts_unbounded_receive_before_waiting_for_operation_lock(monkeypatch, raise_exception):
    sock = BlockedReceiveSocket()
    used = install_sockets(monkeypatch, sock)
    api = CountAPI(auto_retry=True, raise_exception=raise_exception)
    api.retry_strategy = ZeroDelay()
    api.connect("example", time_out=None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(api.count)
        try:
            assert sock.receiving.wait(1)
            closing = pool.submit(api.close)
            assert closing.result(timeout=1) is None
            if raise_exception:
                with pytest.raises(TdxFunctionCallError):
                    pending.result(timeout=1)
            else:
                assert pending.result(timeout=1) is None
        finally:
            sock.interrupted.set()
    assert sock.timeout is None
    assert used == [sock] and sock.closed and api.closed and api.client is None
    assert api.heartbeat_thread is None


def test_close_interrupts_long_retry_delay_without_opening_another_socket(monkeypatch):
    sock = ScriptedSocket(send_error=ConnectionResetError("disconnected"))
    used = install_sockets(monkeypatch, sock)
    class ObservedEvent:
        def __init__(self):
            self.event = threading.Event()
            self.waiting = threading.Event()
        def set(self):
            self.event.set()
        def clear(self):
            self.event.clear()
        def is_set(self):
            return self.event.is_set()
        def wait(self, timeout):
            self.waiting.set()
            return self.event.wait(timeout)
    class LongDelay:
        @staticmethod
        def generate():
            yield 3600
    api = CountAPI(auto_retry=True)
    cancellation = ObservedEvent()
    api._cancel_event = cancellation
    api.retry_strategy = LongDelay()
    api.connect("example")
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(api.count)
        try:
            assert cancellation.waiting.wait(1)
            closing = pool.submit(api.close)
            assert closing.result(timeout=1) is None
            assert pending.result(timeout=1) is None
        finally:
            cancellation.set()
    assert used == [sock]
    assert api.closed and api.client is None and sock.closed
    assert api.last_error is not None


@pytest.mark.parametrize("raise_exception", [False, True])
def test_cancelled_connect_never_publishes_live_state_or_starts_heartbeat(monkeypatch, raise_exception):
    class ConnectingSocket(ScriptedSocket):
        def __init__(self):
            super().__init__()
            self.connecting = threading.Event()
            self.interrupted = threading.Event()
        def connect(self, address):
            self.address = address
            self.connecting.set()
            assert self.interrupted.wait(2), "test did not interrupt connect"
        def shutdown(self, how):
            self.interrupted.set()
    sock = ConnectingSocket()
    used = install_sockets(monkeypatch, sock)
    class InitializingAPI(CountAPI):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.need_setup = True
            self.setup_calls = 0
        def setup(self):
            self.setup_calls += 1
    api = InitializingAPI(heartbeat=True, auto_retry=True, raise_exception=raise_exception)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(api.connect, "example", time_out=None)
        try:
            assert sock.connecting.wait(1)
            closing = pool.submit(api.close)
            assert closing.result(timeout=1) is None
            if raise_exception:
                with pytest.raises(TdxConnectionError, match="cancelled"):
                    pending.result(timeout=1)
            else:
                assert pending.result(timeout=1) is False
        finally:
            sock.interrupted.set()
    assert used == [sock] and sock.closed and api.closed and api.client is None
    assert api.heartbeat_thread is None and api.stop_event is None
    assert api.setup_calls == 0
    assert "cancelled" in str(api.last_error)


def test_cancellation_during_socket_creation_cleans_up_before_connect(monkeypatch):
    creating, release_factory = threading.Event(), threading.Event()
    sock = ScriptedSocket()
    def factory(*args):
        creating.set()
        assert release_factory.wait(2), "test did not release socket factory"
        return sock
    monkeypatch.setattr("mootdx._protocol.base_socket_client.TrafficStatSocket", factory)
    api = CountAPI()
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(api.connect, "example")
        try:
            assert creating.wait(1)
            closing = pool.submit(api.close)
            assert api._cancel_event.wait(1)
            release_factory.set()
            assert pending.result(timeout=1) is False
            assert closing.result(timeout=1) is None
        finally:
            release_factory.set()
    assert sock.address is None and sock.closed
    assert api.closed and api.client is None


def test_real_local_socketpair_receive_is_interrupted_by_close(monkeypatch):
    local, peer = socket.socketpair()
    class PairedSocket(ScriptedSocket):
        def __init__(self):
            super().__init__()
            self.receiving = threading.Event()
        def settimeout(self, value):
            super().settimeout(value)
            local.settimeout(value)
        def send(self, request):
            return local.send(request)
        def recv(self, size):
            self.receiving.set()
            return local.recv(size)
        def shutdown(self, how):
            local.shutdown(how)
        def close(self):
            super().close()
            local.close()
    sock = PairedSocket()
    used = install_sockets(monkeypatch, sock)
    api = CountAPI(auto_retry=True)
    api.connect("local socketpair", time_out=None)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(api.count)
            try:
                assert sock.receiving.wait(1)
                closing = pool.submit(api.close)
                assert closing.result(timeout=1) is None
                assert pending.result(timeout=1) is None
            finally:
                peer.close()  # Also releases recv if an implementation regression occurs.
        assert used == [sock] and sock.closed and local.fileno() == -1
        assert api.closed and api.client is None
    finally:
        peer.close()
        local.close()
        api.close()
