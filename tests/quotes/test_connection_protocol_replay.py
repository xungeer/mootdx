"""Replay captured protocol bytes through the real public Quotes API offline."""
import json
from pathlib import Path

import pandas as pd
import pytest

import mootdx._protocol.base_socket_client as protocol
from mootdx.quotes import Quotes


FIXTURE = Path(__file__).parents[1] / 'fixtures/connection/standard_session_20261111.json'


class CapturedSocket:
    def __init__(self, events):
        self.events = iter(events)
        self.requests = []
        self.pending = b''
        self._closed = False
        self.send_pkg_num = self.recv_pkg_num = 0
        self.send_pkg_bytes = self.recv_pkg_bytes = 0
        self.last_api_send_bytes = self.last_api_recv_bytes = 0
        self.first_pkg_send_time = None

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect(self, endpoint):
        self.endpoint = endpoint

    def send(self, payload):
        assert not self._closed and not self.pending
        event = next(self.events)
        assert bytes(payload).hex() == event['request_hex']
        self.requests.append(bytes(payload))
        self.pending = bytes.fromhex(event['wire_response_hex'])
        return len(payload)

    def recv(self, size):
        # Deliberately fragment both the recorded header and compressed body.
        result, self.pending = self.pending[:min(size, 7)], self.pending[min(size, 7):]
        return result

    def shutdown(self, how):
        pass

    def close(self):
        self._closed = True


def assert_frame_matches_capture(frame, event):
    expected = [dict(row) for row in event['decoded']]
    for row in expected:
        # The capture used 0.2.9. Its get_volume(0) bug was already fixed in
        # the 0.3.0 base of this change; retain original fixture values.
        for field in ('vol', 'amount'):
            if row.get(field) == 5.877471754111438e-39:
                row[field] = 0.0
        if 'vol' in row:
            row['volume'] = row['vol']
    assert json.loads(json.dumps(frame.to_dict('records'))) == expected
    if expected and 'datetime' in expected[0]:
        assert isinstance(frame.index, pd.DatetimeIndex)
        assert frame.index.tolist() == pd.to_datetime([row['datetime'] for row in expected]).tolist()


def test_real_standard_session_reuses_one_connection_and_preserves_dataframe_values(monkeypatch):
    fixture = json.loads(FIXTURE.read_text())
    events = fixture['events']
    transport = CapturedSocket(events)
    transports = []

    def socket_factory(*args):
        transports.append(transport)
        return transport

    monkeypatch.setattr(protocol, 'TrafficStatSocket', socket_factory)
    client = Quotes.factory(server=('127.0.0.1', 7709),
                            timeout=2, auto_retry=False, raise_exception=True)
    try:
        assert not client.closed
        assert client.client.handshake == 'minimal'
        assert len(client.client.handshake_results) == 2
        assert client.last_error is None
        assert transport.timeout == 2
        for event in events[2:]:
            if event['parser'] == 'GetSecurityQuotesCmd':
                frame = client.quotes(['000001', '600000', '510300', '920000'])
            else:
                request = bytes.fromhex(event['request_hex'])
                symbol = request[14:20].decode('ascii')
                method = client.index if event['parser'] == 'GetIndexBarsCmd' else client.bars
                frame = method(symbol=symbol, frequency=event['category'], offset=2)
            assert_frame_matches_capture(frame, event)
            assert client.last_error is None
        assert len(transports) == 1
        assert len(transport.requests) == len(events)
        assert transport.pending == b''
        assert next(transport.events, None) is None
    finally:
        client.close()
    assert client.closed
    assert transport._closed
