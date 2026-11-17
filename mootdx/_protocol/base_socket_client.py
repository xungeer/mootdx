# cython: language_level=3
import datetime
import functools
import math
from contextlib import contextmanager
from itertools import islice
import socket
import threading
import time

import pandas as pd

from mootdx._protocol.exceptions import TdxHandshakeError
from mootdx._protocol.exceptions import TdxProtocolError
from mootdx._protocol.exceptions import TdxConnectionError
from mootdx._protocol.exceptions import TdxFunctionCallError
from mootdx._protocol.exceptions import ValidationException
from mootdx._protocol.heartbeat import HeartBeatThread
from mootdx._protocol.logger import logger
from mootdx._protocol.parser.raw_parser import RawParser

DEFAULT_HEARTBEAT_INTERVAL = 10.0

CONNECT_TIMEOUT = 5.000
RECV_HEADER_LEN = 0x10


def last_ack_time(func):
    """Serialize a complete request/retry transaction and record successful ACKs.

    The historical name and return/error modes remain public. Failed requests
    are available as ``last_error`` even in the default silent mode.
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kw):
        with self._operation():
            return self._request(func, args, kw)
    return wrapper


class RetryStrategy:
    @classmethod
    def generate(cls):
        raise NotImplementedError("need to override")


class DefaultRetryStrategy(RetryStrategy):
    """
    默认的重试策略，您可以通过写自己的重试策略替代本策略, 改策略主要实现 generate 方法，该方法是一个生成器，
    返回下次重试的间隔时间, 单位为秒，我们会使用 time.sleep在这里同步等待之后进行重新connect,然后再重新发起
    源请求，直到 generate 结束。
    """

    @classmethod
    def generate(cls):
        yield from [0.1, 0.5, 1, 2]


class TrafficStatSocket(socket.socket):
    """
    实现支持流量统计的socket类
    """

    def __init__(self, sock, mode):
        super().__init__(sock, mode)

        # 流量统计相关
        self.send_pkg_num = 0  # 发送次数
        self.recv_pkg_num = 0  # 接收次数
        self.send_pkg_bytes = 0  # 发送字节
        self.recv_pkg_bytes = 0  # 接收字节数
        self.first_pkg_send_time = None  # 第一个数据包发送时间

        self.last_api_send_bytes = 0  # 最近的一次api调用的发送字节数
        self.last_api_recv_bytes = 0  # 最近一次api调用的接收字节数


class BaseSocketClient:
    def __init__(self, multithread=False, heartbeat=False, auto_retry=False,
                 raise_exception=False, *, heartbeat_interval=DEFAULT_HEARTBEAT_INTERVAL,
                 max_retries=4):
        if not isinstance(heartbeat_interval, (int, float)) or isinstance(heartbeat_interval, bool) or not math.isfinite(heartbeat_interval) or heartbeat_interval <= 0:
            raise ValidationException("heartbeat_interval must be finite and positive")
        if not isinstance(max_retries, int) or isinstance(max_retries, bool) or max_retries < 0:
            raise ValidationException("max_retries must be a nonnegative integer")
        self.need_setup = True
        self.closed = True
        self.client = None
        # Protect the whole operation, including socket selection and reconnect.
        # RLock also covers nested APIs and parsers that acquire the same lock.
        self.lock = threading.RLock()
        self._operation_depth = 0
        self._retired_heartbeats = []
        self._generation = 0
        self.heartbeat = heartbeat
        self.heartbeat_thread = None
        self.stop_event = None
        self.heartbeat_interval = float(heartbeat_interval)
        self.last_ack_time = time.time()
        self._last_ack_monotonic = time.monotonic()
        self.last_error = None
        self.last_cleanup_error = None
        self.ip, self.port = None, None
        self._connect_params = None
        self._reconnect_allowed = False
        self._cancel_event = threading.Event()
        self.auto_retry = auto_retry
        self.max_retries = max_retries
        self.retry_strategy = DefaultRetryStrategy()
        self.raise_exception = raise_exception

    @contextmanager
    def _operation(self):
        retired = []
        try:
            with self.lock:
                self._operation_depth += 1
                try:
                    yield
                finally:
                    self._operation_depth -= 1
                    if not self._operation_depth:
                        retired, self._retired_heartbeats = self._retired_heartbeats, []
        finally:
            # A heartbeat may be waiting for the operation lock. Never join it
            # while holding that lock, or join the current heartbeat itself.
            for thread in retired:
                if thread is not threading.current_thread() and thread.ident is not None:
                    thread.join()

    def _ack(self):
        self.last_ack_time = time.time()
        self._last_ack_monotonic = time.monotonic()
        self.last_error = None

    def _request(self, func, args, kw):
        try:
            result = func(self, *args, **kw)
            self._ack()
            return result
        except (TypeError, ValueError) as exc:
            self.last_error = exc
            raise ValidationException(*exc.args) from exc
        except Exception as exc:
            current = exc

        # Protocol corruption and explicit refusal cannot be repaired by blindly
        # replaying the same request. Network failures may use fresh connections.
        retryable = self._retryable(current)
        if isinstance(current, (OSError, TdxConnectionError, TdxProtocolError)):
            self._disconnect_locked()
        if self.auto_retry and retryable and self._reconnect_allowed and self._connect_params is not None:
            for delay in islice(self.retry_strategy.generate(), self.max_retries):
                if not isinstance(delay, (int, float)) or not math.isfinite(delay) or delay < 0:
                    current = ValidationException("retry delay must be finite and nonnegative")
                    break
                if self._cancel_event.wait(delay) or not self._reconnect_allowed:
                    break
                try:
                    if not self._connect_locked(**self._connect_params):
                        raise self.last_error
                    result = func(self, *args, **kw)
                    self._ack()
                    return result
                except Exception as exc:
                    current = exc
                    self._disconnect_locked()
                    if not self._retryable(exc):
                        break
        self.last_error = current
        if self.raise_exception:
            error = TdxFunctionCallError("calling function error")
            error.original_exception = current
            raise error from current
        return None

    @staticmethod
    def _retryable(exc):
        return isinstance(exc, (OSError, TdxConnectionError)) and not isinstance(exc, TdxHandshakeError)

    def connect(self, ip=None, port=7709, time_out=CONNECT_TIMEOUT,
                bind_port=None, bind_ip="0.0.0.0"):
        """Connect and initialize; return self or False in compatibility mode.

        Explicit handshake refusals and initialization failures always close the
        socket. The last failure remains available through ``last_error``.
        """
        if not ip:
            raise ValidationException("IP Address bad.")
        with self._operation():
            self._cancel_event.clear()
            self._reconnect_allowed = True
            return self._connect_locked(ip, port, time_out, bind_port, bind_ip)

    def _connect_locked(self, ip, port=7709, time_out=CONNECT_TIMEOUT,
                        bind_port=None, bind_ip="0.0.0.0"):
        self._disconnect_locked()
        self.ip, self.port = ip, port
        self._connect_params = dict(ip=ip, port=port, time_out=time_out,
                                    bind_port=bind_port, bind_ip=bind_ip)
        try:
            if self._cancel_event.is_set():
                raise TdxConnectionError("connection cancelled")
            self.client = TrafficStatSocket(socket.AF_INET, socket.SOCK_STREAM)
            self.client.settimeout(time_out)
            if bind_port is not None:
                self.client.bind((bind_ip, bind_port))
            if self._cancel_event.is_set():
                raise TdxConnectionError("connection cancelled")
            self.client.connect((ip, port))
            if self._cancel_event.is_set():
                raise TdxConnectionError("connection cancelled")
            if self.need_setup:
                self.setup()
            if self._cancel_event.is_set():
                raise TdxConnectionError("connection cancelled")
            self.closed = False
            self._ack()
            if self.heartbeat:
                self.stop_event = threading.Event()
                self.heartbeat_thread = HeartBeatThread(
                    client=self, stop_event=self.stop_event,
                    interval=self.heartbeat_interval)
                self.heartbeat_thread.start()
            return self
        except Exception as exc:
            self._disconnect_locked()
            if isinstance(exc, TdxProtocolError):
                error = TdxHandshakeError("malformed handshake response",
                                          command=exc.command, original_exception=exc,
                                          status="malformed", step=getattr(exc, "step", None),
                                          profile=getattr(exc, "profile", None))
                # Preserve the full length and bounded preview without retaining
                # an unbounded payload or discarding the parser's diagnosis.
                error.response_length = exc.response_length
                error.response_preview = exc.response_preview
                error.expected_length = exc.expected_length
                error.args = (error._detail("malformed handshake response"),)
            else:
                error = exc if isinstance(exc, TdxConnectionError) else TdxConnectionError("connection or initialization failed")
                if error is not exc:
                    error.original_exception = exc
            self.last_error = error
            if self.raise_exception:
                if error is exc:
                    raise
                raise error from exc
            return False

    def reconnect(self):
        """Open a new socket with the original timeout, bind and API options."""
        with self._operation():
            if self._connect_params is None:
                raise ValidationException("connect must be called before reconnect")
            self._cancel_event.clear()
            self._reconnect_allowed = True
            return self._connect_locked(**self._connect_params)

    def _disconnect_locked(self):
        self._generation += 1
        if self.stop_event is not None:
            self.stop_event.set()
        if self.heartbeat_thread is not None:
            self._retired_heartbeats.append(self.heartbeat_thread)
        self.heartbeat_thread = None
        self.stop_event = None
        sock, self.client = self.client, None
        self.closed = True
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                # A failed connect or an already disconnected peer is normal.
                pass
            except Exception as exc:
                self.last_cleanup_error = exc
            finally:
                try:
                    sock.close()
                except Exception as exc:
                    self.last_cleanup_error = exc

    def disconnect(self):
        """Cancel pending socket I/O/retry waits, close and join the heartbeat."""
        # Cancellation must precede the operation lock: recv may be blocking
        # indefinitely when the caller explicitly selected time_out=None.
        self._cancel_event.set()
        self._reconnect_allowed = False
        event, sock = self.stop_event, self.client
        if event is not None:
            event.set()
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            except Exception as exc:
                self.last_cleanup_error = exc
        with self._operation():
            self._disconnect_locked()

    def close(self):
        self.disconnect()

    def get_traffic_stats(self):
        """Return statistics for one socket generation; require a connection."""
        with self._operation():
            if self.client is None:
                raise TdxConnectionError("traffic statistics require an open connection")
            return self._get_traffic_stats_locked()

    def _get_traffic_stats_locked(self):
        if self.client.first_pkg_send_time is not None:
            total_seconds = (datetime.datetime.now() - self.client.first_pkg_send_time).total_seconds()

            if total_seconds != 0:
                send_bytes_per_second = self.client.send_pkg_bytes // total_seconds
                recv_bytes_per_second = self.client.recv_pkg_bytes // total_seconds
            else:
                send_bytes_per_second = None
                recv_bytes_per_second = None
        else:
            total_seconds = None
            send_bytes_per_second = None
            recv_bytes_per_second = None

        return {
            "send_pkg_num": self.client.send_pkg_num,
            "recv_pkg_num": self.client.recv_pkg_num,
            "send_pkg_bytes": self.client.send_pkg_bytes,
            "recv_pkg_bytes": self.client.recv_pkg_bytes,
            "first_pkg_send_time": self.client.first_pkg_send_time,
            "total_seconds": total_seconds,
            "send_bytes_per_second": send_bytes_per_second,
            "recv_bytes_per_second": recv_bytes_per_second,
            "last_api_send_bytes": self.client.last_api_send_bytes,
            "last_api_recv_bytes": self.client.last_api_recv_bytes,
        }

    def send_raw_pkg(self, pkg):
        """
        发送原始数据包
        # for debuging and testing protocol

        :param pkg:
        :return:
        """
        with self._operation():
            cmd = RawParser(self.client, lock=self.lock)
            cmd.setParams(pkg)
            try:
                result = cmd.call_api()
                self._ack()
                return result
            except Exception as exc:
                self.last_error = exc
                if isinstance(exc, (OSError, TdxConnectionError, TdxProtocolError)):
                    self._disconnect_locked()
                # Raw diagnostics have always raised, independent of the API
                # decorator's compatibility mode; preserve that contract.
                raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @staticmethod
    def to_df(v):
        """
        数据转换 df 格式
        :param v:
        :return:
        """

        v = v or ""

        if not v:
            return pd.DataFrame(data=None)

        if isinstance(v, list):
            return pd.DataFrame(data=v)

        if isinstance(v, dict):
            return pd.DataFrame(data=[v])

        return pd.DataFrame(data=[{"value": v}])

    def setup(self):
        """
        方法
        """
        pass
