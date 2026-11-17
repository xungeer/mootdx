"""Offline public-API handshake regression using captured parser inputs.

Except for the verbatim wire replay, envelopes around the historical bodies
are synthetic, using the standard frame correspondence independently captured
in wire_capture_20261111.json. No public endpoint is contacted by these tests.
"""
import hashlib
import json
import struct
from pathlib import Path

import pytest

from mootdx._protocol.exceptions import TdxHandshakeError, TdxHandshakeRejected, ValidationException
from mootdx._protocol.exhq import TdxExHq_API
from mootdx._protocol.hq import TdxHq_API
from mootdx._protocol.parser.base import ResponseRecvFails
from mootdx._protocol.parser.setup_commands import ExSetupCmd1


_FIXTURE_DIR = Path(__file__).parent / "fixtures"
_BODIES = json.loads((_FIXTURE_DIR / "handshake_20261111.json").read_text())["fixtures"]
_WIRE = json.loads((_FIXTURE_DIR / "wire_capture_20261111.json").read_text())


def captured(parser, host="110.41.147.114", category=None):
    return next(item for item in _BODIES
                if item["parser"] == parser and item["category"] == category
                and any(source["host"] == host for source in item["occurrences"]))


def envelope(request, body):
    # Synthetic uncompressed envelope, with command/request-id association
    # verified separately by the verbatim wire replay below.
    head = bytearray(16)
    head[:4] = bytes.fromhex("b1cb7400")
    head[4] = 0x1c
    head[5:9] = request[1:5]
    head[10:12] = request[10:12]
    head[12:16] = struct.pack("<HH", len(body), len(body))
    return bytes(head) + body


class ReplaySocket:
    def __init__(self, exchanges):
        self.exchanges = list(exchanges)
        self.pending = bytearray()
        self.sent = []
        self.timeout = None
        self.bound = None
        self.address = None
        self.close_count = 0
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

    def send(self, request):
        expected, reply = self.exchanges.pop(0)
        assert bytes(request) == expected
        assert not self.pending, "previous response was not fully consumed"
        self.sent.append(bytes(request))
        self.pending.extend(reply)
        return len(request)

    def recv(self, size):
        # Deliberately fragment both headers and bodies.
        out = bytes(self.pending[:min(size, 7)])
        del self.pending[:len(out)]
        return out

    def shutdown(self, _):
        pass

    def close(self):
        self.close_count += 1


def exchange(item, body=None):
    request = bytes.fromhex(item["request_hex"])
    payload = bytes.fromhex(item["response_hex"]) if body is None else body
    return request, envelope(request, payload)


def socket_factory(monkeypatch, *sockets):
    queue = iter(sockets)
    monkeypatch.setattr("mootdx._protocol.base_socket_client.TrafficStatSocket", lambda *_: next(queue))


def test_default_uses_two_captured_steps_and_keeps_their_identity(monkeypatch):
    # This node's third reply explicitly refused the old setup. The default
    # must send only the two required steps, without retrying the old profile.
    items = [captured(name) for name in ("SetupCmd1", "SetupCmd2")]
    sock = ReplaySocket([exchange(item) for item in items])
    socket_factory(monkeypatch, sock)
    api = TdxHq_API(raise_exception=True)
    try:
        assert api.connect("test.invalid") is api
        assert api.handshake == "minimal"
        assert sock.sent == [bytes.fromhex(item["request_hex"]) for item in items]
        assert [(row["step"], row["profile"], row["command"])
                for row in api.handshake_results] == [
                    (1, "minimal", 0x000d), (2, "minimal", 0x000d)]
        assert all(row["status"] == "unknown" for row in api.handshake_results)
    finally:
        api.close()
    assert sock.close_count == 1


@pytest.mark.parametrize("step", [1, 2])
@pytest.mark.parametrize("failure", ["rejected", "empty", "malformed", "transport_error"])
def test_required_step_failure_keeps_identity_and_never_falls_back(monkeypatch, step, failure):
    # All failure variants below are synthetic at the selected step. Only the
    # refusal body's original third-step provenance comes from the capture.
    exchanges = [exchange(captured(f"SetupCmd{number}")) for number in range(1, step + 1)]
    item = captured(f"SetupCmd{step}")
    if failure == "rejected":
        exchanges[-1] = exchange(item, bytes.fromhex(captured("SetupCmd3")["response_hex"]))
    elif failure == "empty":
        exchanges[-1] = exchange(item, b"")
    elif failure == "malformed":
        request, reply = exchanges[-1]
        exchanges[-1] = request, reply[:10] + b"\xff\xff" + reply[12:]
    else:
        request, reply = exchanges[-1]
        exchanges[-1] = request, reply[:-1]
    sock = ReplaySocket(exchanges)
    socket_factory(monkeypatch, sock)
    api = TdxHq_API(raise_exception=True, auto_retry=True, heartbeat=True)
    error_class = ResponseRecvFails if failure == "transport_error" else TdxHandshakeError
    with pytest.raises(error_class) as caught:
        api.connect("test.invalid")
    error = caught.value
    assert (error.step, error.profile, error.command) == (step, "minimal", 0x000d)
    assert error is api.last_error
    assert len(api.handshake_results) == step
    assert api.handshake_results[-1]["step"] == step
    assert api.handshake_results[-1]["profile"] == "minimal"
    assert api.handshake_results[-1]["status"] == failure
    assert len(sock.sent) == step
    assert api.client is None and api.closed
    assert api.heartbeat_thread is None
    assert sock.close_count == 1
    api.close()
    assert sock.close_count == 1


@pytest.mark.parametrize("strategy,names", [
    ("single", ["SetupCmd1"]),
    ("minimal", ["SetupCmd1", "SetupCmd2"]),
    ("legacy", ["SetupCmd1", "SetupCmd2", "SetupCmd3"]),
])
def test_explicit_sequences_replay_captured_requests_and_opaque_replies(monkeypatch, strategy, names):
    items = [captured(name, "60.12.136.250") for name in names]
    sock = ReplaySocket([exchange(item) for item in items])
    socket_factory(monkeypatch, sock)
    api = TdxHq_API(handshake=strategy, raise_exception=True)
    try:
        assert api.connect("test.invalid", 7709) is api
        assert sock.sent == [bytes.fromhex(item["request_hex"]) for item in items]
        assert not sock.exchanges
        assert [r["response_length"] for r in api.handshake_results] == [item["response_bytes"] for item in items]
        assert all(r["status"] == "unknown" for r in api.handshake_results)
        for result, item in zip(api.handshake_results, items):
            body = bytes.fromhex(item["response_hex"])
            assert result["response_preview"] == body[:32].hex()
            assert result["response_prefix_hex"] == body[:256].hex()
            assert result["response_sha256"] == hashlib.sha256(body).hexdigest()
            assert result["response_prefix_truncated"] is (len(body) > 256)
        assert not api.closed
    finally:
        api.close()
    assert sock.close_count == 1


@pytest.mark.parametrize("raise_exception", [False, True])
def test_explicit_legacy_detects_only_captured_explicit_refusal_and_cleans_up(monkeypatch, raise_exception):
    items = [captured(name) for name in ("SetupCmd1", "SetupCmd2", "SetupCmd3")]
    sock = ReplaySocket([exchange(item) for item in items])
    socket_factory(monkeypatch, sock)
    api = TdxHq_API(handshake="legacy", raise_exception=raise_exception)
    if raise_exception:
        with pytest.raises(TdxHandshakeRejected) as caught:
            api.connect("test.invalid")
        assert caught.value is api.last_error
    else:
        assert api.connect("test.invalid") is False
    assert isinstance(api.last_error, TdxHandshakeRejected)
    assert api.last_error.command == 0x0fdb
    assert api.last_error.status == "rejected"
    assert api.last_error.response_length == 179
    assert len(api.last_error.response_preview) <= 64
    assert api.handshake_results[-1]["status"] == "rejected"
    refusal = bytes.fromhex(items[-1]["response_hex"])
    assert api.handshake_results[-1]["response_prefix_hex"] == refusal[:256].hex()
    assert api.handshake_results[-1]["response_sha256"] == hashlib.sha256(refusal).hexdigest()
    assert api.closed and api.client is None
    assert sock.close_count == 1
    api.close()
    assert sock.close_count == 1


@pytest.mark.parametrize("host,expected_length", [("60.12.136.250", 596), ("120.195.71.156", 179)])
def test_other_third_replies_are_not_misclassified_as_rejection_or_success(monkeypatch, host, expected_length):
    items = [captured(name, host) for name in ("SetupCmd1", "SetupCmd2", "SetupCmd3")]
    sock = ReplaySocket([exchange(item) for item in items])
    socket_factory(monkeypatch, sock)
    api = TdxHq_API(handshake="legacy", raise_exception=True)
    try:
        api.connect("test.invalid")
        assert api.handshake_results[-1]["status"] == "unknown"
        assert api.handshake_results[-1]["response_length"] == expected_length
        assert api.last_error is None
    finally:
        api.close()


@pytest.mark.parametrize("body", [b"\x01", bytes(188), bytes(190)])
def test_no_unproven_189_byte_success_threshold(monkeypatch, body):
    sock = ReplaySocket([exchange(captured("SetupCmd1"), body)])
    socket_factory(monkeypatch, sock)
    api = TdxHq_API(handshake="single", raise_exception=True)
    try:
        assert api.connect("test.invalid") is api
        assert api.handshake_results == [{
            "step": 1, "profile": "single",
            "command": 0x000d, "status": "unknown", "response_length": len(body),
            "response_preview": body[:32].hex(),
            "response_prefix_hex": body[:256].hex(),
            "response_sha256": hashlib.sha256(body).hexdigest(),
            "response_prefix_truncated": len(body) > 256,
        }]
    finally:
        api.close()


def test_complete_but_empty_handshake_body_is_not_accepted(monkeypatch):
    sock = ReplaySocket([exchange(captured("SetupCmd1"), b"")])
    socket_factory(monkeypatch, sock)
    api = TdxHq_API(handshake="single", raise_exception=True)
    with pytest.raises(TdxHandshakeError) as caught:
        api.connect("test.invalid")
    assert caught.value.status == "empty"
    assert caught.value.response_length == 0
    assert api.client is None and api.closed
    assert sock.close_count == 1


def test_truncated_handshake_frame_preserves_transport_error_and_releases_socket(monkeypatch):
    request, reply = exchange(captured("SetupCmd1"))
    sock = ReplaySocket([(request, reply[:-1])])
    socket_factory(monkeypatch, sock)
    api = TdxHq_API(handshake="single", raise_exception=True)
    with pytest.raises(ResponseRecvFails) as caught:
        api.connect("test.invalid")
    assert caught.value.expected_length == 189
    assert caught.value.response_length == 188
    assert api.last_error is caught.value
    assert api.closed and api.client is None
    assert sock.close_count == 1


def test_minimal_reconnect_preserves_policy_timeout_binding_and_captured_data(monkeypatch):
    handshake = [captured(name) for name in ("SetupCmd1", "SetupCmd2")]
    bars = captured("GetIndexBarsCmd", category=9)
    first = ReplaySocket([exchange(item) for item in handshake] + [exchange(bars)])
    second = ReplaySocket([exchange(item) for item in handshake] + [exchange(bars)])
    socket_factory(monkeypatch, first, second)
    api = TdxHq_API(handshake="minimal", raise_exception=True)
    api.connect("test.invalid", 7710, time_out=1.25, bind_port=0, bind_ip="127.0.0.1")
    before = api.get_index_bars(9, 0, "399317", 0, 2)
    assert before == bars["decoded"]
    assert api.reconnect() is api
    after = api.get_index_bars(9, 0, "399317", 0, 2)
    assert after == before
    assert first.close_count == 1
    assert second.address == ("test.invalid", 7710)
    assert second.timeout == 1.25
    assert second.bound == ("127.0.0.1", 0)
    assert second.sent == first.sent
    assert len(api.handshake_results) == 2
    api.close()
    assert second.close_count == 1


def test_independent_clients_do_not_share_handshake_results_or_policy(monkeypatch):
    one = ReplaySocket([exchange(captured("SetupCmd1"))])
    two = ReplaySocket([exchange(captured(name)) for name in ("SetupCmd1", "SetupCmd2")])
    socket_factory(monkeypatch, one, two)
    single = TdxHq_API(handshake="single", raise_exception=True)
    minimal = TdxHq_API(handshake="minimal", raise_exception=True)
    try:
        single.connect("one.invalid")
        minimal.connect("two.invalid")
        assert len(single.handshake_results) == 1
        assert len(minimal.handshake_results) == 2
        assert single.handshake_results is not minimal.handshake_results
        assert single.lock is not minimal.lock
        single.close()
        assert not minimal.closed
        assert two.close_count == 0
    finally:
        single.close()
        minimal.close()


def test_verbatim_compressed_wire_handshakes_replay_under_public_minimal_policy(monkeypatch):
    events = _WIRE["cases"][0]["events"][:2]
    exchanges = [(b"".join(bytes.fromhex(c["hex"]) for c in event["send_chunks"]),
                  b"".join(bytes.fromhex(c["hex"]) for c in event["recv_chunks"]))
                 for event in events]
    sock = ReplaySocket(exchanges)
    socket_factory(monkeypatch, sock)
    api = TdxHq_API(handshake="minimal", raise_exception=True)
    try:
        assert api.connect("test.invalid") is api
        assert [result["response_length"] for result in api.handshake_results] == [189, 189]
        assert not sock.pending and not sock.exchanges
    finally:
        api.close()


def test_extended_market_uses_its_own_setup_and_rejects_standard_strategy_option(monkeypatch):
    parser = ExSetupCmd1(None)
    parser.setup()
    request = bytes(parser.send_pkg)
    # Extension transport length envelope is synthetic: there is deliberately
    # no claim here about undocumented extension handshake response semantics.
    sock = ReplaySocket([(request, envelope(request, b"extension transport reply"))])
    socket_factory(monkeypatch, sock)
    api = TdxExHq_API(raise_exception=True)
    try:
        assert api.connect("ext.invalid", 7727) is api
        assert len(sock.sent) == 1 and sock.sent[0][0] == 0x01
        assert not hasattr(api, "handshake_results")
    finally:
        api.close()
    with pytest.raises(TypeError, match="handshake"):
        TdxExHq_API(handshake="minimal")


@pytest.mark.parametrize("value", [None, "auto", "12", 1, []])
def test_invalid_handshake_strategy_is_not_silently_ignored(value):
    with pytest.raises(ValidationException, match="handshake"):
        TdxHq_API(handshake=value)


@pytest.mark.parametrize("options", [{}, {"handshake": "single"}])
def test_server_adjusted_api_preserves_single_step_wire_and_diagnostics(monkeypatch, options):
    from mootdx._protocol.hq import ServerAdjustedTdxHqAPI

    item = captured("SetupCmd1")
    sock = ReplaySocket([exchange(item)])
    socket_factory(monkeypatch, sock)
    api = ServerAdjustedTdxHqAPI(raise_exception=True, **options)
    try:
        assert api.connect("adjusted.invalid") is api
        assert api.handshake == "single"
        assert sock.sent == [bytes.fromhex(item["request_hex"])]
        assert api.handshake_results == [{
            "step": 1, "profile": "single",
            "command": 0x000d,
            "status": "unknown",
            "response_length": item["response_bytes"],
            "response_preview": item["response_hex"][:64],
            "response_prefix_hex": item["response_hex"][:512],
            "response_sha256": hashlib.sha256(bytes.fromhex(item["response_hex"])).hexdigest(),
            "response_prefix_truncated": item["response_bytes"] > 256,
        }]
    finally:
        api.close()
    assert sock.close_count == 1


@pytest.mark.parametrize("strategy", ["minimal", "legacy"])
def test_server_adjusted_api_rejects_unsupported_handshake_policies(strategy):
    from mootdx._protocol.hq import ServerAdjustedTdxHqAPI

    with pytest.raises(ValidationException, match="requires handshake='single'"):
        ServerAdjustedTdxHqAPI(handshake=strategy)


def test_server_adjusted_api_uses_shared_explicit_refusal_handling(monkeypatch):
    from mootdx._protocol.hq import ServerAdjustedTdxHqAPI

    # Synthetic first-step refusal: the refusal BODY was captured at step 3,
    # and is deliberately re-enveloped for step 1 to test shared semantics.
    # This is not evidence that any captured node rejected its first step.
    refusal = bytes.fromhex(captured("SetupCmd3")["response_hex"])
    sock = ReplaySocket([exchange(captured("SetupCmd1"), refusal)])
    socket_factory(monkeypatch, sock)
    api = ServerAdjustedTdxHqAPI(raise_exception=True)
    with pytest.raises(TdxHandshakeRejected) as caught:
        api.connect("adjusted.invalid")
    assert caught.value.command == 0x000d
    assert api.last_error is caught.value
    assert api.handshake_results[-1]["status"] == "rejected"
    assert api.closed and api.client is None
    assert sock.close_count == 1


def test_large_captured_handshake_retains_bounded_prefix_and_complete_digest(monkeypatch):
    # The 596-byte third reply was captured from 60.12.136.250. Retaining a
    # prefix cannot accidentally certify this opaque reply as successful.
    items = [captured(name, "60.12.136.250") for name in ("SetupCmd1", "SetupCmd2", "SetupCmd3")]
    sock = ReplaySocket([exchange(item) for item in items])
    socket_factory(monkeypatch, sock)
    api = TdxHq_API(handshake="legacy", raise_exception=True)
    try:
        api.connect("test.invalid")
        body = bytes.fromhex(items[-1]["response_hex"])
        result = api.handshake_results[-1]
        assert len(body) == 596
        assert len(bytes.fromhex(result["response_prefix_hex"])) == 256
        assert result["response_prefix_hex"] == body[:256].hex()
        assert result["response_sha256"] == hashlib.sha256(body).hexdigest()
        assert result["response_prefix_truncated"] is True
        assert result["response_preview"] == body[:32].hex()
        assert result["status"] == "unknown"
        assert len(sock.sent) == 3
    finally:
        api.close()


def test_captured_standard_setup_bytes_after_preview_remain_available(monkeypatch):
    item = captured("SetupCmd1", "60.12.136.250")
    body = bytes.fromhex(item["response_hex"])
    sock = ReplaySocket([exchange(item)])
    socket_factory(monkeypatch, sock)
    api = TdxHq_API(handshake="single", raise_exception=True)
    try:
        api.connect("test.invalid")
        result = api.handshake_results[0]
        assert len(body) == 189
        assert bytes.fromhex(result["response_prefix_hex"]) == body
        assert bytes.fromhex(result["response_prefix_hex"])[68:152] == body[68:152]
        assert result["response_prefix_truncated"] is False
        assert len(sock.sent) == 1
    finally:
        api.close()
