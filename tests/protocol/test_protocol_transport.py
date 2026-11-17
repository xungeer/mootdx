"""Transport tests are deterministic; captured bytes are replayed through sockets."""
import json
import socket
import struct
import zlib
from pathlib import Path

import pytest

from mootdx._protocol.exceptions import TdxResponseError, TdxTransportError
from mootdx._protocol.parser.base import (
    ResponseHeaderRecvFails, ResponseRecvFails, SendRequestPkgFails,
    SocketClientNotReady,
)
from mootdx._protocol.parser.raw_parser import RawParser


REQUEST = bytes.fromhex("0c01086401011c001c002d050000333939333137090001000000020000000000000000000000")
FIXTURES = Path(__file__).parent / "fixtures"


class FragmentSocket:
    """A byte stream with bounded reads/writes, including adjacent frames."""
    def __init__(self, data=b"", read_size=65535, write_size=65535):
        self.data = bytearray(data)
        self.read_size = read_size
        self.write_size = write_size
        self.sent = bytearray()
        self.read_requests = []
        self.send_pkg_num = self.recv_pkg_num = 0
        self.send_pkg_bytes = self.recv_pkg_bytes = 0
        self.last_api_send_bytes = self.last_api_recv_bytes = 0
        self.first_pkg_send_time = None

    def send(self, data):
        size = min(len(data), self.write_size)
        self.sent.extend(data[:size])
        return size

    def recv(self, size):
        self.read_requests.append(size)
        take = min(size, self.read_size, len(self.data))
        data = bytes(self.data[:take])
        del self.data[:take]
        return data


def frame(body, request=REQUEST, compressed=False, declared_length=None):
    wire = zlib.compress(body) if compressed else body
    header = (bytes.fromhex("b1cb7400") + b"\x0c" + request[1:5] + b"\x00"
              + request[10:12] + struct.pack("<HH", len(wire),
                                            len(body) if declared_length is None else declared_length))
    return header + wire


def parser(sock, request=REQUEST):
    result = RawParser(sock)
    result.setParams(request)
    return result


@pytest.mark.parametrize("read_size", [1, 3, 16, 65535])
@pytest.mark.parametrize("compressed", [False, True])
def test_complete_fragmented_send_and_receive_without_overreading(read_size, compressed):
    body = b"payload" * 50
    wire = frame(body, compressed=compressed)
    second = frame(b"next frame")
    sock = FragmentSocket(wire + second, read_size=read_size, write_size=3)
    cmd = parser(sock)
    assert cmd.call_api() == body
    assert bytes(sock.sent) == REQUEST
    assert bytes(sock.data) == second
    assert sock.send_pkg_bytes == len(REQUEST)
    assert sock.recv_pkg_bytes == len(wire)
    assert sock.last_api_send_bytes == len(REQUEST)
    assert sock.last_api_recv_bytes == len(wire)
    assert cmd.rsp_header == wire[:16]
    assert cmd.rsp_body == body
    assert cmd.call_api() == b"next frame"
    assert sock.last_api_recv_bytes == len(second)


def test_real_captured_compressed_setup_and_uncompressed_bars():
    captured = json.loads((FIXTURES / "wire_capture_20261111.json").read_text())
    events = captured["cases"][0]["events"]
    for event in events:
        wire = bytes.fromhex(event["wire_response_hex"])
        sock = FragmentSocket(wire, read_size=2, write_size=5)
        cmd = parser(sock, bytes.fromhex(event["request_hex"]))
        assert cmd.call_api() == bytes.fromhex(event["parser_input_hex"])
        assert not sock.data


@pytest.mark.parametrize("length", range(16))
def test_truncated_header_is_network_error_with_bounded_diagnostics(length):
    wire = frame(b"x")
    with pytest.raises(ResponseHeaderRecvFails) as raised:
        parser(FragmentSocket(wire[:length], read_size=2)).call_api()
    error = raised.value
    assert isinstance(error, TdxTransportError)
    assert error.command == 0x052d
    assert error.response_length == length
    assert error.expected_length == 16
    assert error.kind == "network_error"


def test_partial_body_disconnection_reports_received_length():
    with pytest.raises(ResponseRecvFails) as raised:
        parser(FragmentSocket(frame(b"abcdef")[:-2], read_size=3)).call_api()
    assert raised.value.response_length == 4
    assert raised.value.expected_length == 6


@pytest.mark.parametrize("stage", ["send", "header", "body"])
def test_network_exception_cause_is_preserved(stage):
    cause = socket.timeout("bounded test timeout")
    sock = FragmentSocket(frame(b"body"))
    if stage == "send":
        sock.send = lambda data: (_ for _ in ()).throw(cause)
        error_type = SendRequestPkgFails
    elif stage == "header":
        sock.recv = lambda size: (_ for _ in ()).throw(cause)
        error_type = ResponseHeaderRecvFails
    else:
        recv = sock.recv
        sock.recv = lambda size: recv(size) if len(sock.data) > 4 else (_ for _ in ()).throw(cause)
        error_type = ResponseRecvFails
    with pytest.raises(error_type) as raised:
        parser(sock).call_api()
    assert raised.value.original_exception is cause
    assert raised.value.__cause__ is cause


def test_zero_send_and_disconnected_client():
    with pytest.raises(SendRequestPkgFails):
        parser(FragmentSocket(write_size=0)).call_api()
    with pytest.raises(SocketClientNotReady):
        parser(None).call_api()


@pytest.mark.parametrize("offset", [0, 5, 10])
def test_wrong_standard_prefix_identifier_or_command_is_rejected(offset):
    wire = bytearray(frame(b"body"))
    wire[offset] ^= 1
    sock = FragmentSocket(wire)
    with pytest.raises(TdxResponseError) as raised:
        parser(sock).call_api()
    assert raised.value.kind == "unexpected_response"
    assert raised.value.response_length == 16
    assert raised.value.command == 0x052d
    # A mismatched frame body is not parsed or consumed as a valid response.
    assert sock.data == b"body"


@pytest.mark.parametrize("declared_length", [1, 499, 501, 65535])
def test_compressed_output_length_must_match_header(declared_length):
    with pytest.raises(TdxResponseError) as raised:
        parser(FragmentSocket(frame(b"a" * 500, compressed=True,
                                    declared_length=declared_length))).call_api()
    assert raised.value.kind == "invalid_compression"
    assert raised.value.original_exception is not None
    assert len(raised.value.response_preview) <= 64


@pytest.mark.parametrize("alteration", ["truncated", "trailing", "second_stream", "corrupt"])
def test_requires_complete_single_valid_zlib_stream(alteration):
    body = b"a" * 500
    wire = bytearray(frame(body, compressed=True))
    if alteration == "truncated":
        wire = wire[:-1]
    elif alteration == "trailing":
        wire += b"trailing"
    elif alteration == "second_stream":
        wire += zlib.compress(b"other")
    else:
        wire[-1] ^= 1
    wire[12:14] = struct.pack("<H", len(wire) - 16)
    with pytest.raises(TdxResponseError) as raised:
        parser(FragmentSocket(wire)).call_api()
    assert raised.value.kind == "invalid_compression"


def test_transport_permits_zero_length_payload_for_parser_to_classify():
    assert parser(FragmentSocket(frame(b""))).call_api() == b""


def test_extension_market_does_not_use_standard_header_match_assumptions():
    request = bytes.fromhex("010148650001520052005424")
    # This synthetic extension envelope tests isolation, not its protocol schema.
    wire = struct.pack("<IIIHH", 0, 0, 0, 2, 2) + b"ok"
    assert parser(FragmentSocket(wire), request).call_api() == b"ok"


@pytest.mark.parametrize("cause", [struct.error("short record"), IndexError("short varint"),
                                   ValueError("invalid record length"),
                                   UnicodeDecodeError("ascii", b"\xff", 0, 1, "invalid")])
def test_legacy_decoders_are_not_misclassified_as_bad_user_parameters(cause):
    cmd = parser(FragmentSocket(frame(b"wire data")))
    cmd.parseResponse = lambda body: (_ for _ in ()).throw(cause)
    with pytest.raises(TdxResponseError) as raised:
        cmd.call_api()
    assert raised.value.original_exception is cause
    assert raised.value.__cause__ is cause
    assert raised.value.response_length == len(b"wire data")
