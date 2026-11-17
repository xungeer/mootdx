# cython: language_level=3
import abc
import datetime
import functools
import struct
import zlib

from mootdx._protocol.logger import logger
from mootdx._protocol.exceptions import TdxResponseError, TdxTransportError

try:
    import cython  # noqa

    if cython.compiled:

        def buffer(x):
            return x

except ImportError:
    pass


class SocketClientNotReady(TdxTransportError):
    pass


class SendPkgNotReady(Exception):
    pass


class SendRequestPkgFails(TdxTransportError):
    pass


class ResponseHeaderRecvFails(TdxTransportError):
    pass


class ResponseRecvFails(TdxTransportError):
    pass


RSP_HEADER_LEN = 0x10


def guard_response(func):
    """Normalize decoder boundary failures, including direct offline replay calls."""
    @functools.wraps(func)
    def wrapped(self, body_buf):
        try:
            return func(self, body_buf)
        except (struct.error, IndexError, UnicodeError, ValueError, OverflowError) as exc:
            raise TdxResponseError(
                "response record cannot be decoded", command=self.command,
                response=body_buf, original_exception=exc,
                kind="malformed_response",
            ) from exc
    return wrapped


class BaseParser:
    def __init__(self, client, lock=None):
        """

        :rtype: object
        """

        self.send_pkg = None
        self.data = None

        self.rsp_header_len = RSP_HEADER_LEN
        self.rsp_header = None
        self.rsp_body = None

        self.client = client
        self.lock = lock or None

        self.category = None

    def setParams(self, *args, **xargs):  # noqa
        """
        构建请求
        :return:
        """
        pass

    @abc.abstractmethod
    def parseResponse(self, body_buf):  # noqa
        """
        解析结果
        :param body_buf:
        """
        pass

    @staticmethod
    def _parse_date(num):
        """

        :param num:
        :return:
        """
        month = (num % 2048) // 100
        year = num // 2048 + 2004
        day = (num % 2048) % 100

        return year, month, day

    @staticmethod
    def _parse_time(num):
        """

        :param num:
        :return:
        """
        return (num // 60), (num % 60)

    @staticmethod
    def _cal_price1000(base_p, diff):
        return float(base_p + diff) / 1000

    def setup(self):
        pass

    def call_api(self):
        """

        :return:
        """
        if self.lock:
            with self.lock:
                logger.debug("sending thread lock api call")
                result = self._call_api()
        else:
            result = self._call_api()

        return result

    @property
    def command(self):
        if self.send_pkg is not None and len(self.send_pkg) >= 12:
            return int.from_bytes(self.send_pkg[10:12], "little")
        return getattr(self, "response_command", None)

    def require_length(self, body, minimum):
        if len(body) < minimum:
            raise TdxResponseError(
                "response shorter than its declared records", command=self.command,
                response=body, expected_length=minimum, kind="truncated_response",
            )

    def require_consumed(self, body, consumed):
        if consumed != len(body):
            raise TdxResponseError(
                "unexpected bytes after declared records", command=self.command,
                response=body, expected_length=consumed, kind="unexpected_response",
            )

    def _recv_exact(self, length, error_class):
        data = bytearray()
        while len(data) < length:
            try:
                chunk = self.client.recv(length - len(data))
            except OSError as exc:
                raise error_class(
                    "response receive failed", command=self.command, response=data,
                    expected_length=length, original_exception=exc,
                ) from exc
            self.client.recv_pkg_num += 1
            self.client.recv_pkg_bytes += len(chunk)
            self.client.last_api_recv_bytes += len(chunk)
            if not chunk:
                raise error_class(
                    "peer closed before complete response", command=self.command,
                    response=data, expected_length=length,
                )
            data.extend(chunk)
        return bytes(data)

    def _validate_header(self, header):
        # The standard 0x0c framing below is confirmed by captured requests and
        # responses from three nodes (tests/fixtures). Extension-market packets
        # use a distinct envelope and are deliberately not assigned this schema.
        if len(self.send_pkg) < 12 or self.send_pkg[0] != 0x0c:
            return
        if header[:4] != bytes.fromhex("b1cb7400"):
            raise TdxResponseError(
                "unexpected standard response prefix", command=self.command,
                response=header, kind="unexpected_response",
            )
        if header[10:12] != self.send_pkg[10:12] or header[5:9] != self.send_pkg[1:5]:
            raise TdxResponseError(
                "response command or request identifier does not match request",
                command=self.command, response=header, kind="unexpected_response",
            )

    def _call_api(self):
        self.setup()
        if not self.client:
            raise SocketClientNotReady("socket client not ready", command=self.command)
        if not self.send_pkg:
            raise SendPkgNotReady("send pkg not ready")

        self.rsp_header = None
        self.rsp_body = None
        self.client.last_api_send_bytes = 0
        self.client.last_api_recv_bytes = 0
        sent = 0
        if not self.client.first_pkg_send_time:
            self.client.first_pkg_send_time = datetime.datetime.now()
        while sent < len(self.send_pkg):
            try:
                size = self.client.send(self.send_pkg[sent:])
            except OSError as exc:
                raise SendRequestPkgFails(
                    "request send failed", command=self.command,
                    expected_length=len(self.send_pkg), original_exception=exc,
                ) from exc
            self.client.send_pkg_num += 1
            self.client.send_pkg_bytes += size
            self.client.last_api_send_bytes += size
            if size <= 0:
                raise SendRequestPkgFails(
                    "socket closed while sending request", command=self.command,
                    expected_length=len(self.send_pkg),
                )
            sent += size

        head_buf = self._recv_exact(self.rsp_header_len, ResponseHeaderRecvFails)
        self.rsp_header = head_buf
        self._validate_header(head_buf)
        _, _, _, zip_size, unzip_size = struct.unpack("<IIIHH", head_buf)
        wire_body = self._recv_exact(zip_size, ResponseRecvFails)
        if zip_size == unzip_size:
            body_buf = wire_body
        else:
            try:
                decompressor = zlib.decompressobj()
                # Header lengths are uint16. Bound inflation even for corrupt
                # streams, and require a complete, single zlib stream.
                body_buf = decompressor.decompress(wire_body, unzip_size + 1)
                if (len(body_buf) != unzip_size or not decompressor.eof
                        or decompressor.unused_data or decompressor.unconsumed_tail):
                    raise ValueError("compressed response length or stream boundary mismatch")
            except (zlib.error, ValueError) as exc:
                raise TdxResponseError(
                    "invalid compressed response", command=self.command,
                    response=wire_body, expected_length=unzip_size,
                    original_exception=exc, kind="invalid_compression",
                ) from exc
        self.rsp_body = body_buf
        try:
            return self.parseResponse(body_buf)
        except (struct.error, IndexError, UnicodeError, ValueError, OverflowError) as exc:
            # Parameter validation happens before call_api. Decoder failures
            # here concern server data and must not become ValidationException.
            raise TdxResponseError(
                "response record cannot be decoded", command=self.command,
                response=body_buf, original_exception=exc,
                kind="malformed_response",
            ) from exc
