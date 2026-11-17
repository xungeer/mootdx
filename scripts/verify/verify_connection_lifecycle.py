#!/usr/bin/env python3
"""Bounded, opt-in downstream connection verification; no network by default.

Select the Mootdx source with PYTHONPATH. This script imports the public Mootdx
API only after --online is supplied, never scans servers or writes BESTIP.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import ipaddress
import json
import math
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


STD_HOSTS = ['110.41.147.114', '60.12.136.250', '120.195.71.156']
EXT_HOSTS = ['47.112.95.207']
STD_SYMBOLS = ['000001', '600000', '510300', '920000']
HEARTBEAT_INTERVAL = 2.0
IDLE_SECONDS = 5.0
BAR_COUNT = 2


def now():
    return datetime.now(timezone.utc).isoformat()


def json_default(value):
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    if hasattr(value, 'item'):
        return value.item()
    return str(value)


def error_info(error):
    if error is None:
        return None
    result = {'type': type(error).__name__, 'message': str(error)[:512]}
    for name in ('command', 'response_length', 'expected_length', 'kind', 'status', 'response_preview'):
        value = getattr(error, name, None)
        if value is not None:
            result[name] = value[:128] if isinstance(value, str) else value
    cause = getattr(error, 'original_exception', None) or error.__cause__
    if cause is not None and cause is not error:
        result['cause'] = {'type': type(cause).__name__, 'message': str(cause)[:512]}
    return result


def environment():
    modules = [
        'mootdx', 'mootdx.quotes', 'mootdx._protocol', 'mootdx._protocol.hq', 'mootdx._protocol.exhq',
        'mootdx._protocol.base_socket_client', 'mootdx._protocol.heartbeat', 'mootdx._protocol.helper',
        'mootdx._protocol.parser.base', 'mootdx._protocol.parser.setup_commands',
        'mootdx._protocol.parser.std.get_security_bars', 'mootdx._protocol.parser.std.get_index_bars',
        'mootdx._protocol.parser.std.get_security_quotes', 'mootdx._protocol.parser.std.get_xdxr_info',
        'mootdx._protocol.parser.ext.ex_get_instrument_bars',
    ]
    result = {'python': sys.version, 'executable': sys.executable,
              'platform': platform.platform(), 'modules': {}, 'installed_metadata': {}}
    for name in modules:
        module = importlib.import_module(name)
        path = Path(module.__file__).resolve()
        result['modules'][name] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                    'module_version': getattr(module, '__version__', None)}
    for name in ('mootdx', 'pandas', 'tenacity'):
        try:
            result['installed_metadata'][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result['installed_metadata'][name] = None
    result['metadata_note'] = 'Installed metadata may differ from PYTHONPATH-selected source; module paths/hashes identify runtime.'
    return result


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def validate_frame(frame, kind, market):
    import pandas as pd

    require(isinstance(frame, pd.DataFrame), 'public API did not return a DataFrame')
    if kind == 'empty_xdxr':
        require(frame.empty, 'index xdxr was expected to be legally empty')
        return {'legal_empty': True, 'units': 'not applicable'}
    require(not frame.empty, 'unexpected empty market data')
    checks = {'nonempty': True, 'units': 'unchanged protocol-native values; no cross-source unit certification'}
    fields = ('open', 'high', 'low', 'close') if kind == 'bars' else ('price', 'open', 'high', 'low', 'last_close')
    for field in fields:
        require(field in frame, f'missing {field}')
        require(all(math.isfinite(float(v)) and float(v) >= 0 for v in frame[field]), f'invalid {field}')
    for _, row in frame.iterrows():
        lower, upper = float(row['low']), float(row['high'])
        epsilon = max(1.0, abs(upper)) * 1e-6
        require(lower <= upper + epsilon, 'low exceeds high')
        for field in ('open', 'close') if kind == 'bars' else ('open', 'price'):
            require(lower - epsilon <= float(row[field]) <= upper + epsilon, f'{field} outside low/high')
    checks['finite_nonnegative_prices'] = checks['ohlc_bounds'] = True
    if kind == 'bars':
        require(0 < len(frame) <= BAR_COUNT, 'unexpected bar count')
        require(isinstance(frame.index, pd.DatetimeIndex), 'missing DatetimeIndex')
        require(frame.index.is_monotonic_increasing and frame.index.is_unique, 'bar dates unordered or duplicated')
        require(not frame.index.hasnans, 'invalid dates')
        checks['ordered_unique_datetime_index'] = True
    if market == 'std':
        for field in ('vol', 'volume', 'amount'):
            require(field in frame, f'missing {field}')
            require(all(math.isfinite(float(v)) and float(v) >= 0 for v in frame[field]), f'invalid {field}')
        require(frame['vol'].equals(frame['volume']), 'volume alias changed values')
        checks['volume_alias_exact'] = checks['finite_nonnegative_volume_amount'] = True
    else:
        for field in ('position', 'trade'):
            require(field in frame, f'missing extended field {field}')
            require(all(int(v) >= 0 for v in frame[field]), f'invalid {field}')
        checks['extended_unit_note'] = 'position/trade/price/amount are recorded as returned; index/futures units and amount overlay are not inferred.'
    return checks


def frame_record(frame):
    return {'rows': len(frame), 'columns': frame.columns.tolist(),
            'index': [str(value) for value in frame.index],
            'records': frame.to_dict('records')}


def run_node(args, host, checkpoint):
    from mootdx.quotes import Quotes

    record = {'host': host, 'port': args.port, 'market': args.market,
              'started_at': now(), 'status': 'running', 'calls': []}
    q = None
    heartbeat_threads = []

    def save():
        checkpoint(record)

    def invoke(label, function, kind='bars', parameters=None):
        event = {'label': label, 'parameters': parameters or {}, 'started_at': now()}
        record['calls'].append(event)
        start = time.perf_counter()
        try:
            frame = function()
            event['last_error'] = error_info(q.last_error)
            require(q.last_error is None, 'protocol last_error is set')
            event['frame'] = frame_record(frame) if hasattr(frame, 'columns') else {'result': repr(frame)[:512]}
            event['checks'] = validate_frame(frame, kind, args.market)
            event['status'] = 'pass'
            return frame
        except Exception as exc:
            event['status'] = 'failed'
            event['error'] = error_info(exc)
            event['last_error'] = error_info(q.last_error)
            raise
        finally:
            event['elapsed_seconds'] = time.perf_counter() - start
            event['finished_at'] = now()
            save()

    try:
        options = dict(market=args.market, server=(host, args.port), bestip=False,
                       timeout=args.timeout, heartbeat=True, heartbeat_interval=HEARTBEAT_INTERVAL,
                       auto_retry=False, max_retries=0, raise_exception=True, multithread=True)
        record['options'] = options
        connect_start = time.perf_counter()
        q = Quotes.factory(**options)
        record['connect_seconds'] = time.perf_counter() - connect_start
        record['selected_server'] = q.server
        require(tuple(q.server) == (host, args.port), 'selected server differs from explicit endpoint')
        require(not q.closed, 'constructor returned a closed client')
        record['handshake_results'] = getattr(q.client, 'handshake_results', None)
        record['selected_handshake'] = getattr(q.client, 'handshake', None)
        if args.market == 'std':
            require(record['selected_handshake'] == 'minimal', 'default standard handshake is not minimal')
            require(len(record['handshake_results']) == 2, 'default standard handshake did not use two steps')
        first_socket = q.client.client
        first_thread = q.client.heartbeat_thread
        heartbeat_threads.append(first_thread)
        record['initial_socket_id'] = id(first_socket)
        record['stats_after_connect'] = q.client.get_traffic_stats()
        save()

        if args.market == 'std':
            for symbol in STD_SYMBOLS:
                for frequency in (9, 8):
                    parameters = dict(symbol=symbol, frequency=frequency, start=0, offset=BAR_COUNT)
                    invoke(f'bars:{symbol}:{frequency}', lambda p=parameters: q.bars(**p), parameters=parameters)
            for frequency in (9, 8):
                parameters = dict(symbol='399317', frequency=frequency, start=0, offset=BAR_COUNT)
                invoke(f'index:399317:{frequency}', lambda p=parameters: q.index(**p), parameters=parameters)
            frame = invoke('quotes', lambda: q.quotes(STD_SYMBOLS), 'quotes', {'symbols': STD_SYMBOLS})
            require(frame['code'].tolist() == STD_SYMBOLS, 'snapshot symbols/order differ')
            require(frame['market'].tolist() == [0, 1, 1, 2], 'snapshot markets differ')
            invoke('legal_empty_index_xdxr', lambda: q.xdxr(symbol='399317'), 'empty_xdxr', {'symbol': '399317'})
        else:
            for market, symbol in ((62, '932000'), (47, 'IFL0')):
                for frequency in (8, 9):
                    parameters = dict(market=market, symbol=symbol, frequency=frequency, start=0, offset=BAR_COUNT)
                    invoke(f'ext_bars:{market}:{symbol}:{frequency}', lambda p=parameters: q.bars(**p), parameters=parameters)

        record['stats_before_idle'] = q.client.get_traffic_stats()
        record['idle_started_at'] = now()
        save()
        time.sleep(IDLE_SECONDS)
        record['stats_after_idle'] = q.client.get_traffic_stats()
        record['idle_finished_at'] = now()
        record['idle_send_call_delta'] = (record['stats_after_idle']['send_pkg_num']
                                          - record['stats_before_idle']['send_pkg_num'])
        record['heartbeat_check'] = {
            'interval_seconds': HEARTBEAT_INTERVAL, 'idle_seconds': IDLE_SECONDS,
            'same_socket': q.client.client is first_socket,
            'thread_alive': first_thread.is_alive() if first_thread else False,
            'last_error': error_info(q.last_error),
            'delta_note': 'socket send calls during foreground-idle window, not certified quote-capability messages',
        }
        require(record['idle_send_call_delta'] > 0, 'no heartbeat traffic observed during idle')
        require(q.last_error is None and q.client.client is first_socket, 'idle heartbeat failed or changed socket')
        require(first_thread is not None and first_thread.is_alive(), 'heartbeat thread stopped unexpectedly')

        q.close()
        record['closed_before_reconnect'] = q.closed
        record['first_heartbeat_stopped'] = not first_thread.is_alive()
        require(q.closed and not first_thread.is_alive(), 'close did not stop initial socket/heartbeat')
        require(q.reconnect(), 'explicit reconnect failed')
        heartbeat_threads.append(q.client.heartbeat_thread)
        record['reconnected_server'] = q.server
        record['reconnected_socket_id'] = id(q.client.client)
        record['new_socket_after_reconnect'] = q.client.client is not first_socket
        record['reconnected_timeout'] = q.client.client.gettimeout()
        record['reconnected_handshake'] = getattr(q.client, 'handshake', None)
        record['reconnected_heartbeat_interval'] = q.client.heartbeat_interval
        require(not q.closed and q.client.client is not first_socket, 'reconnect did not create a new open socket')
        require(record['reconnected_timeout'] == args.timeout, 'reconnect lost timeout')
        require(q.client.heartbeat_interval == HEARTBEAT_INTERVAL, 'reconnect lost heartbeat interval')
        if args.market == 'std':
            require(q.client.handshake == 'minimal', 'reconnect lost standard handshake strategy')
            invoke('quotes_after_reconnect', lambda: q.quotes(STD_SYMBOLS), 'quotes', {'symbols': STD_SYMBOLS})
        else:
            parameters = dict(market=62, symbol='932000', frequency=8, start=0, offset=BAR_COUNT)
            invoke('ext_bars_after_reconnect', lambda: q.bars(**parameters), parameters=parameters)
        record['stats_before_final_close'] = q.client.get_traffic_stats()
        record['status'] = 'pass'
    except Exception as exc:
        record['status'] = 'failed'
        record['error'] = error_info(exc)
        if q is not None:
            record['last_error'] = error_info(q.last_error)
    finally:
        if q is not None:
            try:
                q.close()
                record['final_closed'] = q.closed
            except Exception as exc:
                record['cleanup_error'] = error_info(exc)
                record['status'] = 'failed'
            record['heartbeat_threads_stopped'] = [thread is None or not thread.is_alive() for thread in heartbeat_threads]
            if not record.get('final_closed') or not all(record['heartbeat_threads_stopped']):
                record['status'] = 'failed'
        record['finished_at'] = now()
        save()
    return record


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--online', action='store_true', help='explicitly enable public-server requests')
    parser.add_argument('--output', type=Path, help='new JSON diagnostic file; existing files are rejected')
    parser.add_argument('--market', choices=('std', 'ext'), default='std')
    parser.add_argument('--hosts', nargs='+', help='one to three IPv4 nodes; no scanning')
    parser.add_argument('--port', type=int)
    parser.add_argument('--timeout', type=float, default=3.0, help='per socket timeout, >0 and <=5 seconds')
    args = parser.parse_args()
    args.hosts = args.hosts or (STD_HOSTS if args.market == 'std' else EXT_HOSTS)
    if args.port is None:
        args.port = 7709 if args.market == 'std' else 7720
    if not 1 <= len(args.hosts) <= 3 or len(set(args.hosts)) != len(args.hosts):
        parser.error('--hosts must contain one to three distinct nodes')
    try:
        for host in args.hosts:
            ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        parser.error('--hosts must be explicit IPv4 addresses')
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 5:
        parser.error('--timeout must be finite, >0 and <=5 seconds')
    if args.online and args.output is None:
        parser.error('--online requires --output pointing to a new JSON file')
    return args


def main():
    args = parse_args()
    if not args.online:
        print('Offline: no network requests made. Add --online --output NEW.json to run the bounded verification.')
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve a new file before importing source modules or connecting.
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write('{}\n')
    report = {'started_at': now(), 'online_explicit': True, 'nodes': [],
              'bounds': {'max_hosts': 3, 'timeout_seconds': args.timeout, 'bar_count': BAR_COUNT,
                         'heartbeat_interval_seconds': HEARTBEAT_INTERVAL, 'idle_seconds': IDLE_SECONDS,
                         'protocol_auto_retry': False, 'protocol_max_retries': 0,
                         'std_foreground_calls_per_node_max': 13, 'ext_foreground_calls_per_node_max': 5,
                         'ext_existing_outer_retry': 'up to 3 calls each, random 1–10 second waits; unchanged public API'},
              'limitations': ['single network and time window; not long-term stability evidence',
                              'native numerical values and invariants; external unit truth is not established',
                              'heartbeat counts are connectivity evidence, not quote/bar capability checks']}

    def checkpoint(node=None):
        if node is not None and not any(existing is node for existing in report['nodes']):
            report['nodes'].append(node)
        with args.output.open('w', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, default=json_default)
            stream.write('\n')

    try:
        report['environment'] = environment()
        checkpoint()
        for host in args.hosts:
            node = run_node(args, host, checkpoint)
            print(f"{host}:{args.port} {node['status']}", flush=True)
        report['status'] = 'pass' if all(node['status'] == 'pass' for node in report['nodes']) else 'failed'
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = error_info(exc)
    except KeyboardInterrupt:
        report['status'] = 'interrupted'
    finally:
        report['finished_at'] = now()
        checkpoint()
    print(f"diagnostics: {args.output}", flush=True)
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
