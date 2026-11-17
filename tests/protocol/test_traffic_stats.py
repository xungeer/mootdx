"""Traffic counters belong to one connection generation, including during close."""
import datetime
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from mootdx._protocol.base_socket_client import BaseSocketClient
from mootdx._protocol.exceptions import TdxConnectionError


START = datetime.datetime(2026, 1, 1)


class CounterSocket:
    def __init__(self, multiplier=1):
        self.send_pkg_num = 3 * multiplier
        self.recv_pkg_num = 5 * multiplier
        self.send_pkg_bytes = 1000 * multiplier
        self.recv_pkg_bytes = 2000 * multiplier
        self.last_api_send_bytes = 10 * multiplier
        self.last_api_recv_bytes = 20 * multiplier
        self.entered = threading.Event()
        self.release = threading.Event()
        self.pause_next_read = False
        self.closed = False

    @property
    def first_pkg_send_time(self):
        if self.pause_next_read:
            self.pause_next_read = False
            self.entered.set()
            assert self.release.wait(2), "test did not release counter read"
        return START

    def settimeout(self, value):
        pass

    def connect(self, address):
        pass

    def shutdown(self, how):
        pass

    def close(self):
        self.closed = True


@pytest.fixture
def fixed_clock(monkeypatch):
    class Clock(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return START + datetime.timedelta(seconds=2)
    monkeypatch.setattr("mootdx._protocol.base_socket_client.datetime.datetime", Clock)


def make_api(monkeypatch, *sockets):
    queue = iter(sockets)
    monkeypatch.setattr("mootdx._protocol.base_socket_client.TrafficStatSocket", lambda *_: next(queue))
    api = BaseSocketClient()
    api.need_setup = False
    api.connect("test.invalid")
    return api


def expected(multiplier=1):
    return {
        "send_pkg_num": 3 * multiplier,
        "recv_pkg_num": 5 * multiplier,
        "send_pkg_bytes": 1000 * multiplier,
        "recv_pkg_bytes": 2000 * multiplier,
        "first_pkg_send_time": START,
        "total_seconds": 2.0,
        "send_bytes_per_second": 500 * multiplier,
        "recv_bytes_per_second": 1000 * multiplier,
        "last_api_send_bytes": 10 * multiplier,
        "last_api_recv_bytes": 20 * multiplier,
    }


def test_counter_shape_values_and_ack_diagnostics_remain_unchanged(monkeypatch, fixed_clock):
    api = make_api(monkeypatch, CounterSocket())
    sentinel = RuntimeError("previous request error")
    api.last_error = sentinel
    api.last_ack_time = -4
    api._last_ack_monotonic = -5
    try:
        assert api.get_traffic_stats() == expected()
        assert api.last_error is sentinel
        assert api.last_ack_time == -4
        assert api._last_ack_monotonic == -5
    finally:
        api.close()


@pytest.mark.parametrize("action", ["close", "reconnect"])
def test_concurrent_lifecycle_cannot_replace_socket_mid_snapshot(monkeypatch, fixed_clock, action):
    old, new = CounterSocket(), CounterSocket(10)
    api = make_api(monkeypatch, old, new)
    old.pause_next_read = True
    lifecycle_started = threading.Event()
    lifecycle_finished = threading.Event()

    def change_connection():
        lifecycle_started.set()
        getattr(api, action)()
        lifecycle_finished.set()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            snapshot = pool.submit(api.get_traffic_stats)
            assert old.entered.wait(1)
            lifecycle = pool.submit(change_connection)
            assert lifecycle_started.wait(1)
            # The counter reader is held at a known point under the operation
            # lock; neither close nor reconnect may change its socket yet.
            assert not lifecycle_finished.wait(0.02)
            old.release.set()
            assert snapshot.result(timeout=1) == expected()
            lifecycle.result(timeout=1)
        assert old.closed
        if action == "close":
            assert api.client is None
            with pytest.raises(TdxConnectionError):
                api.get_traffic_stats()
        else:
            assert api.client is new
            assert api.get_traffic_stats() == expected(10)
    finally:
        old.release.set()
        api.close()


@pytest.mark.parametrize("raise_exception", [False, True])
def test_disconnected_stats_raise_domain_error_without_mutating_last_error(raise_exception):
    api = BaseSocketClient(raise_exception=raise_exception)
    sentinel = RuntimeError("previous failure")
    api.last_error = sentinel
    with pytest.raises(TdxConnectionError):
        api.get_traffic_stats()
    assert api.last_error is sentinel
    assert api.last_ack_time > 0
    api.close()
    with pytest.raises(TdxConnectionError):
        api.get_traffic_stats()
    assert api.last_error is sentinel
