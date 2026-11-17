"""Offline replay of real parser inputs; no public server is needed."""
import json
import struct
from pathlib import Path

import pytest

from mootdx._protocol.exceptions import TdxResponseError
from mootdx._protocol.parser.std.get_index_bars import GetIndexBarsCmd
from mootdx._protocol.parser.std.get_security_quotes import GetSecurityQuotesCmd
from mootdx._protocol.parser.std.get_security_bars import GetSecurityBarsCmd
from mootdx._protocol.parser.std.get_xdxr_info import GetXdXrInfo


EVIDENCE = json.loads(
    (Path(__file__).parent / 'fixtures' / 'handshake_20261111.json').read_text(encoding='utf-8')
)
BAR_FIXTURES = [row for row in EVIDENCE['fixtures'] if row['parser'] == 'GetIndexBarsCmd']
QUOTE_FIXTURES = [row for row in EVIDENCE['fixtures'] if row['parser'] == 'GetSecurityQuotesCmd']
HEALTHY_BARS = [row for row in BAR_FIXTURES if 'decoded' in row]
HEALTHY_QUOTES = [row for row in QUOTE_FIXTURES if row['decoded']]


def configured_parser(fixture):
    cls = GetIndexBarsCmd if fixture['parser'] == 'GetIndexBarsCmd' else GetSecurityQuotesCmd
    parser = cls(None)
    parser.category = fixture['category']
    parser.send_pkg = bytes.fromhex(fixture['request_hex'])
    return parser


def expected_rows(fixture):
    rows = json_normalize(fixture['decoded'])
    # v0.3.0 already fixed helper.get_volume(0); retain historical fixture bytes
    # and original v0.2.9 output, but expect that existing correction explicitly.
    if fixture['parser'] in ('GetIndexBarsCmd', 'GetSecurityBarsCmd'):
        payload = bytes.fromhex(fixture.get('response_hex', fixture.get('parser_input_hex', '')))
        pos = 2
        for row in rows:
            pos += 4  # date/time
            for _ in range(4):  # four signed variable-length price deltas
                while payload[pos] & 0x80:
                    pos += 1
                pos += 1
            for field in ('vol', 'amount'):
                raw = struct.unpack_from('<I', payload, pos)[0]
                pos += 4
                if raw == 0:
                    assert row[field] in (0.0, 5.877471754111438e-39)
                    row[field] = 0.0
                else:
                    assert row[field] != 5.877471754111438e-39
            if fixture['parser'] == 'GetIndexBarsCmd':
                pos += 4  # advancing/declining counts
    return rows


def json_normalize(value):
    # JSON captured the legacy tuple-valued reversed_bytes4 as a list.
    return json.loads(json.dumps(value))


@pytest.mark.parametrize('fixture', HEALTHY_BARS, ids=['index-daily', 'index-minute'])
def test_real_index_rows_preserve_every_value_and_order(fixture):
    rows = configured_parser(fixture).parseResponse(bytes.fromhex(fixture['response_hex']))
    assert json_normalize(rows) == expected_rows(fixture)
    assert len(rows) == 2
    assert rows[0]['datetime'] < rows[1]['datetime']
    assert list(rows[0]) == list(fixture['decoded'][0])


def test_real_daily_index_units_are_unchanged():
    fixture = next(row for row in HEALTHY_BARS if row['category'] == 9)
    last = configured_parser(fixture).parseResponse(bytes.fromhex(fixture['response_hex']))[-1]
    assert {key: last[key] for key in ('open', 'close', 'high', 'low', 'vol', 'amount', 'datetime')} == {
        'open': 6084.97,
        'close': 6067.18,
        'high': 6092.21,
        'low': 6051.4,
        'vol': 9125333.0,
        'amount': 1473908441088.0,
        'datetime': '2026-11-10 15:00',
    }


@pytest.mark.parametrize('fixture', QUOTE_FIXTURES)
def test_real_quotes_preserve_all_fields_and_legal_empty_result(fixture):
    result = configured_parser(fixture).parseResponse(bytes.fromhex(fixture['response_hex']))
    assert json_normalize(result) == fixture['decoded']
    if result:
        assert [(row['market'], row['code']) for row in result] == [
            (1, '600000'), (1, '510300'), (2, '920000')
        ]
        assert result[1]['price'] == 4.135
        assert result[1]['vol'] == 12031066
        assert result[1]['amount'] == 4983241216.0


@pytest.mark.parametrize('fixture', [row for row in BAR_FIXTURES if 'parse_error' in row])
def test_real_two_byte_response_is_structured_truncation_not_error_code_2003(fixture):
    payload = bytes.fromhex(fixture['response_hex'])
    assert payload == b'\x20\x03'
    assert struct.unpack('<H', payload)[0] == 800
    with pytest.raises(TdxResponseError) as caught:
        configured_parser(fixture).parseResponse(payload)
    error = caught.value
    assert error.command == 0x052D
    assert error.response_length == 2
    assert error.response_preview == '2003'
    assert fixture['parse_error']['type'] == 'error'  # historical struct.error


def test_identical_index_request_bytes_across_handshake_strategies():
    for category in (9, 7):
        fixtures = [row for row in BAR_FIXTURES if row['category'] == category]
        assert len({row['request_hex'] for row in fixtures}) == 1
        variants = {item['variant'] for row in fixtures for item in row['occurrences']}
        assert {'1', '12', '123', '12+3'} <= variants
    assert sum(len(row['occurrences']) for row in BAR_FIXTURES) == 39


@pytest.mark.parametrize('fixture', HEALTHY_BARS + HEALTHY_QUOTES)
def test_real_responses_reject_every_truncated_prefix(fixture):
    parser = configured_parser(fixture)
    payload = bytes.fromhex(fixture['response_hex'])
    for length in range(len(payload)):
        with pytest.raises(TdxResponseError):
            parser.parseResponse(payload[:length])


@pytest.mark.parametrize('fixture', HEALTHY_BARS + HEALTHY_QUOTES)
def test_synthetic_count_mismatch_and_trailing_data_are_not_silent(fixture):
    payload = bytearray.fromhex(fixture['response_hex'])
    count_offset = 0 if fixture['parser'] == 'GetIndexBarsCmd' else 2
    declared = struct.unpack_from('<H', payload, count_offset)[0]
    struct.pack_into('<H', payload, count_offset, declared + 1)
    with pytest.raises(TdxResponseError):
        configured_parser(fixture).parseResponse(payload)
    with pytest.raises(TdxResponseError):
        configured_parser(fixture).parseResponse(bytes.fromhex(fixture['response_hex']) + b'\x00')


@pytest.mark.parametrize('category', [9, 7])
def test_zero_record_index_response_remains_legal(category):
    parser = GetIndexBarsCmd(None)
    parser.setParams(category, 0, '399317', 0, 2)
    assert parser.parseResponse(b'\x00\x00') == []


def test_different_third_step_replies_remain_distinct_evidence():
    replies = [row for row in EVIDENCE['fixtures'] if row['parser'] == 'SetupCmd3']
    assert len(replies) == 3
    assert sorted(row['response_bytes'] for row in replies) == [179, 179, 596]
    mismatch = '客户端与行情主站不匹配,不能使用!'.encode('gbk')
    explicit = [row for row in replies if mismatch in bytes.fromhex(row['response_hex'])]
    assert len(explicit) == 1
    assert {item['host'] for item in explicit[0]['occurrences']} == {'110.41.147.114'}


# Additional real frames from the independent macOS verification.

WIRE = json.loads(
    (Path(__file__).parent / 'fixtures' / 'wire_capture_20261111.json').read_text(encoding='utf-8')
)
SUPPLEMENT = json.loads(
    (Path(__file__).parent / 'fixtures' / 'wire_supplement_20261111.json').read_text(encoding='utf-8')
)
WIRE_PARSERS = {
    'GetIndexBarsCmd': GetIndexBarsCmd,
    'GetSecurityBarsCmd': GetSecurityBarsCmd,
    'GetSecurityQuotesCmd': GetSecurityQuotesCmd,
    'GetXdXrInfo': GetXdXrInfo,
}
WIRE_EVENTS = [
    event
    for report in (WIRE, SUPPLEMENT)
    for case in report['cases']
    for event in case['events']
    if event['parser'] in WIRE_PARSERS
]


def wire_parser(event):
    parser = WIRE_PARSERS[event['parser']](None)
    parser.category = event['category']
    parser.send_pkg = bytes.fromhex(event['request_hex'])
    return parser


@pytest.mark.parametrize('event', WIRE_EVENTS)
def test_independent_three_market_and_etf_values_match_baseline(event):
    result = wire_parser(event).parseResponse(bytes.fromhex(event['parser_input_hex']))
    assert json_normalize(result) == expected_rows(event)


def test_real_empty_corporate_actions_require_the_record_count_header():
    event = next(
        item for item in WIRE_EVENTS
        if item['parser'] == 'GetXdXrInfo' and item['decoded'] == []
    )
    payload = bytes.fromhex(event['parser_input_hex'])
    assert payload.hex() == '0100003339393331370000'
    assert wire_parser(event).parseResponse(payload) == []
    for length in range(len(payload)):
        with pytest.raises(TdxResponseError):
            wire_parser(event).parseResponse(payload[:length])


def test_real_corporate_actions_and_stock_bars_reject_truncation_and_trailing_data():
    events = [
        event for event in WIRE['cases'][0]['events']
        if event['parser'] in ('GetSecurityBarsCmd', 'GetXdXrInfo')
    ]
    for event in events:
        payload = bytes.fromhex(event['parser_input_hex'])
        for length in range(len(payload)):
            with pytest.raises(TdxResponseError):
                wire_parser(event).parseResponse(payload[:length])
        with pytest.raises(TdxResponseError):
            wire_parser(event).parseResponse(payload + b'\x00')


def test_real_separate_pages_preserve_start_offset_and_chronological_order():
    events = [
        item for item in SUPPLEMENT['cases'][0]['events']
        if item['parser'] == 'GetIndexBarsCmd'
    ]
    pages = {}
    for event in events:
        request = bytes.fromhex(event['request_hex'])
        start, count = struct.unpack_from('<HH', request, 24)
        pages[start] = wire_parser(event).parseResponse(bytes.fromhex(event['parser_input_hex']))
        assert count in (1, 2)
    healthy_daily = next(item for item in HEALTHY_BARS if item['category'] == 9)
    expected = expected_rows(healthy_daily)
    assert pages[0] == [expected[1]]
    assert pages[1] == [expected[0]]
    assert pages[60000] == []
    assert pages[1] + pages[0] == expected
