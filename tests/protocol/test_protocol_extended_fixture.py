"""Real extension-market application frames; no network or standard setup policy."""
import json
import struct
from pathlib import Path

import pytest

from mootdx._protocol.parser.ext.ex_get_instrument_bars import GetInstrumentBars
from mootdx._protocol.parser.setup_commands import ExSetupCmd1


FIXTURE = json.loads((Path(__file__).parent / "fixtures" /
                     "extended_baseline_wire_20261111.json").read_text(encoding="utf-8"))
SETUP = FIXTURE["events"][0]
BARS = [event for event in FIXTURE["events"] if event["parser"] == "GetInstrumentBars"]


class FragmentStream:
    def __init__(self, wire, fragment):
        self.pending = bytearray(wire)
        self.fragment = fragment
        self.sent = bytearray()
        self.send_pkg_num = self.recv_pkg_num = 0
        self.send_pkg_bytes = self.recv_pkg_bytes = 0
        self.last_api_send_bytes = self.last_api_recv_bytes = 0
        self.first_pkg_send_time = None

    def send(self, request):
        size = min(3, len(request))
        self.sent.extend(request[:size])
        return size

    def recv(self, size):
        take = min(size, self.fragment, len(self.pending))
        result = bytes(self.pending[:take])
        del self.pending[:take]
        return result


def parameters(event):
    request = bytes.fromhex(event["request_hex"])
    market, code, category, period, start, count = struct.unpack("<B9sHHIH", request[12:])
    assert period == 1
    return category, market, code.rstrip(b"\x00").decode("ascii"), start, count


def configured(event, stream):
    command = GetInstrumentBars(stream)
    command.setParams(*parameters(event))
    assert bytes(command.send_pkg) == bytes.fromhex(event["request_hex"])
    return command


@pytest.mark.parametrize("fragment", [1, 7, 65535])
def test_real_compressed_extended_setup_survives_partial_write_and_fragmented_read(fragment):
    wire = bytes.fromhex(SETUP["wire_response_hex"])
    stream = FragmentStream(wire, fragment)
    command = ExSetupCmd1(stream)
    # ExSetup's existing public parser result is None; transport exposes the
    # retained decompressed input separately without inventing status semantics.
    assert command.call_api() is None
    assert bytes(stream.sent) == bytes.fromhex(SETUP["request_hex"])
    assert stream.sent[0] == 0x01
    assert command.rsp_header == bytes.fromhex(SETUP["header_hex"])
    assert command.rsp_body == bytes.fromhex(SETUP["response_hex"])
    assert len(command.rsp_body) == 299
    assert stream.recv_pkg_bytes == len(wire)
    assert not stream.pending


def test_extension_setup_does_not_apply_the_standard_frame_schema():
    # This is explicitly a synthetic header variant of a real extension frame.
    # Its body/lengths are unchanged. It checks schema isolation, not whether
    # an actual extension server would emit or accept this altered header.
    wire = bytearray.fromhex(SETUP["wire_response_hex"])
    wire[0] ^= 1
    wire[5] ^= 1
    wire[10] ^= 1
    command = ExSetupCmd1(FragmentStream(wire, 2))
    assert command.call_api() is None
    assert command.rsp_body == bytes.fromhex(SETUP["response_hex"])


@pytest.mark.parametrize("fragment", [1, 7, 65535])
@pytest.mark.parametrize("event", BARS)
def test_real_extended_bars_replay_every_value_through_fragmented_transport(event, fragment):
    wire = bytes.fromhex(event["wire_response_hex"])
    stream = FragmentStream(wire, fragment)
    command = configured(event, stream)
    rows = command.call_api()
    assert rows == event["decoded"]
    assert command.rsp_body == bytes.fromhex(event["response_hex"])
    assert bytes(stream.sent) == bytes.fromhex(event["request_hex"])
    assert stream.recv_pkg_bytes == len(wire)
    assert not stream.pending
    assert rows[0]["datetime"] < rows[1]["datetime"]


@pytest.mark.parametrize("identity,expected", [
    ((8, 62, "932000"), (2804.5048828125, 2804.554931640625, 2804.5048828125,
                         2804.554931640625, 1166002432, 354, 4092.5625)),
    ((9, 62, "932000"), (2778.611083984375, 2806.856689453125, 2777.90966796875,
                         2804.5546875, 1218602258, 274, 332584.5625)),
    ((8, 47, "IFL0"), (4052.199951171875, 4053.60009765625, 4049.39990234375,
                       4049.39990234375, 44337, 153, 6.212937001276941e-41)),
    ((9, 47, "IFL0"), (4088.0, 4091.199951171875, 4047.199951171875,
                       4049.39990234375, 44337, 204, 6.212937001276941e-41)),
])
def test_concrete_index_and_futures_values_remain_the_original_decoder_contract(identity, expected):
    event = next(item for item in BARS if parameters(item)[:3] == identity)
    row = configured(event, None).parseResponse(bytes.fromhex(event["response_hex"]))[-1]
    assert tuple(row[key] for key in ("open", "high", "low", "close",
                                    "position", "trade", "amount")) == expected
    assert row["datetime"] == "2026-11-10 15:00"
    assert (row["year"], row["month"], row["day"], row["hour"], row["minute"]) == (2026, 11, 10, 15, 0)


def test_futures_amount_is_preserved_bit_reinterpretation_not_certified_turnover():
    for event in BARS:
        if parameters(event)[1] != 47:
            continue
        payload = bytes.fromhex(event["response_hex"])
        rows = configured(event, None).parseResponse(payload)
        for index, row in enumerate(rows):
            # 20-byte envelope, then 4-byte date + OHLC float32[4]. The legacy
            # decoder exposes this same 4-byte word as uint32 position and as
            # float32 amount. Preservation does NOT validate monetary meaning.
            word = payload[20 + index * 32 + 20:20 + index * 32 + 24]
            assert struct.unpack("<I", word)[0] == row["position"]
            assert struct.unpack("<f", word)[0] == row["amount"]
            assert 0 < row["amount"] < 1e-30
