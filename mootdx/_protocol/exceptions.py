# cython: language_level=3


class TdxConnectionError(Exception):
    """
    当连接服务器出错的时候，会抛出的异常
    """

    pass


class TdxFunctionCallError(Exception):
    """
    当行数调用出错的时候
    """

    def __init__(self, *args):
        super().__init__(*args)
        self.original_exception = None


class ValidationException(Exception):
    ...


class _ResponseDiagnostic:
    """Bounded diagnostics; no complete wire payload is included in error text."""

    def _diagnostics(self, command, response, expected_length, original_exception, kind):
        response = bytes(response)
        self.command = command
        self.response_length = len(response)
        self.response_preview = response[:32].hex()
        self.expected_length = expected_length
        self.original_exception = original_exception
        self.kind = kind

    def _detail(self, message):
        command = f"0x{self.command:04x}" if self.command is not None else "unknown"
        return (f"{message} (command={command}, length={self.response_length}, "
                f"expected={self.expected_length}, preview={self.response_preview})")


class TdxProtocolError(_ResponseDiagnostic, Exception):
    """A complete response cannot be interpreted by the selected protocol."""

    def __init__(self, message, *, command=None, response=b"", expected_length=None,
                 original_exception=None, kind="malformed_response"):
        self._diagnostics(command, response, expected_length, original_exception, kind)
        super().__init__(self._detail(message))


class TdxResponseError(TdxProtocolError):
    """Truncated, malformed, or mismatched protocol response (not an empty result)."""


class TdxTransportError(_ResponseDiagnostic, TdxConnectionError):
    """Incomplete request/response transport; original network error is retained."""

    def __init__(self, message, *, command=None, response=b"", expected_length=None,
                 original_exception=None, kind="network_error"):
        self._diagnostics(command, response, expected_length, original_exception, kind)
        super().__init__(self._detail(message))


class TdxHandshakeError(_ResponseDiagnostic, TdxConnectionError):
    """Handshake failure without guessing undocumented status-code semantics."""

    def __init__(self, message, *, command=None, response=b"", original_exception=None,
                 status="unknown", step=None, profile=None):
        self.status = status
        self.step = step
        self.profile = profile
        self._diagnostics(command, response, None, original_exception, "handshake_error")
        super().__init__(self._detail(message))

    def _detail(self, message):
        return f"{super()._detail(message)} [profile={self.profile}, step={self.step}]"


class TdxHandshakeRejected(TdxHandshakeError):
    """A response explicitly reports a client/server mismatch or rejection."""
