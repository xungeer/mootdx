# Handshake regression fixtures

`handshake_20261111.json` is an exact extraction from the user-supplied
`tdxpy-handshake-20261111/probe.json`, SHA-256
`414a9b61464379242cb3ae8980653dd0ef6745d38652b4066b97f361d19266f0`.
The archive supplied for this investigation has SHA-256
`0909cce6956537dec96417b7892f15f4b75b6a59bdf2390de7dbcc82d7d15145`.
All 14 entries of its `SHA256SUMS.json` were checked before extraction.

Capture window: 2026-11-11 00:43:22.413279–00:43:25.902814 Asia/Shanghai.
The capture was made on Windows/Anaconda Python 3.11.14 with the **xungeer
forks**, mootdx 0.11.9 at `7d482a84d4b42b16c0f81c38d6f613452dd010c3`
and tdxpy 0.2.9 at `53111f8df4dc3a27555e609f675b5d815cfb5a59`,
pytdx 1.72 and pandas 2.1.4. These version numbers do not identify unrelated
same-named distributions.

The JSON preserves 36 unique parser/category/request/response combinations
and all 97 source occurrences (case and event indices, node, handshake
strategy, repeat and timestamps). It includes healthy daily and minute
index bars, the original three-security quotes, all distinct handshake
responses, the two-byte `20 03` bar response and zero-record quote responses.
The original decoded records and exception descriptions are evidence, not
rewritten expected outcomes. Current tests intentionally expect a structured
response error where the historical decoder raised `struct.error`.

**Capture layer:** `response_hex` is the input to `parseResponse`, after the
original transport decompressed the body. It excludes the TCP header and
compressed wire bytes; this is neither a pcap nor proof of frame-header
semantics. `request_hex` is the original outgoing application request.

Healthy values are retained at full recorded precision. Regressions compare
all fields, including OHLC, datetime, volume and amount, with the original
old-command decoder output. Quote coverage includes Shanghai stock 600000,
Shanghai ETF 510300 (three-decimal quote prices) and Beijing stock 920000.
Bars here cover Shenzhen index 399317. This fixture does not prove stock/ETF
bar units, all markets, current server data, or the correctness of a new
protocol. No new wire command or unit conversion is introduced by these tests.

`20 03` consists of two hexadecimal bytes; interpreted as a little-endian
record count it is 800, but the body contains no records. Its official status
meaning is unknown. A zero-count quote body is structurally legal and is
therefore kept as an empty result; it cannot on its own distinguish no data
from a server limiting a particular session's market-data capabilities.
The explicit mismatch text occurs only in one node's third-step response;
other nodes' different replies must not be given the same interpretation.

All hosts in this fixture are public market-data servers. Tests only replay
bytes locally and never connect to them. The capture covers one machine and
one short time window, not cross-network, cross-platform or long-term
reliability. Synthetic malformed variants in the tests are explicitly derived
from these fixtures; they are not represented as captured responses.

## Independent macOS captures

`wire_capture_20261111.json` and `wire_supplement_20261111.json` are verbatim
copies of the independent, bounded rerun's capture files. Their SHA-256 values
are respectively:

- `wire_capture_20261111.json`: `78854e4dceb046699d7e6b89854d9f0c5523303e0fedac2d1b0faa9a8643c13d`
- `wire_supplement_20261111.json`: `1ecb6c906d469d4513e96908bae79311902599085e6a4037601df0bef9224ac0`.

Their own top-level timestamps delimit the actual capture windows. Capture
occurs at Python `socket.send`/`socket.recv` before header parsing and zlib
decompression, with a separate copy of the decompressed parser input. These
are complete application response frames, not packet-level pcap files.
They use the same installed 0.2.9/0.11.9 fork commits described above, on
macOS arm64 with Python 3.12.13 and pandas 3.0.3. The first capture includes
48 responses from the same three public nodes, adding Shenzhen stock 000001,
Shanghai stock 600000, ETF 510300, Beijing stock 920000 day/minute bars and
ETF corporate actions. The supplement contains independent one-record pages,
a zero-record index page and genuine 11-byte empty index corporate actions.

The target library revision `c8390ab` (tdxpy 0.3.0) already changed
`get_volume(0)` from the old decoder's `5.877471754111438e-39` to `0.0`.
Tests preserve the historical decoded JSON and explicitly account for this
pre-existing zero-value correction. All other captured values are compared
exactly; this is not a unit conversion introduced by the handshake repair.


## Extended-market application frames

`extended_baseline_wire_20261111.json` is a verbatim copy of the independent
capture from the unmodified installed tdxpy 0.2.9 fork, commit
`53111f8df4dc3a27555e609f675b5d815cfb5a59` (mootdx 0.11.9 at the matching
historical fork commit). SHA-256:
`2cbcce4f00847fff937983b95b58c4a1fc5f2a8bf625031bc0333eec7ffb723d`.

It was captured at the application socket send/receive boundary on macOS arm64,
Python 3.12.13 / pandas 3.0.3, from `120.195.71.160:7721`, during
2026-11-11 01:27:17.829912–01:27:18.429077 Asia/Shanghai. Original JSON timestamps
are UTC. It contains the compressed extension setup response and four bar
responses: market 62/index 932000 and market 47/futures IFL0, categories 8 and 9.
Each request has two records. Complete application headers, compressed bodies
and decompressed parser inputs are retained; this is not a TCP pcap.

`test_protocol_extended_fixture.py` replays the real frames through partial
writes and fragmented header/body reads, then checks every original decoded
field plus explicit OHLC, date/time, position, trade and amount values. A
separately labelled synthetic header mutation checks that extension setup does
not inherit the standard-market frame schema. No runtime extension decoder or
handshake policy is changed by these tests.

For futures, the existing `amount` value is the same four bytes used for
`position`, reinterpreted as float32; it is consequently extremely small.
The test deliberately preserves this original API output. It does **not**
certify that field as economically meaningful turnover, establish an official
unit, or validate all extension markets/interfaces. The root investigation
separately compared these four responses through the patched mootdx wrapper;
all fields matched the original decoder output.
