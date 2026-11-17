"""Applications can extend the bundled parser without importing tdxpy."""
from unittest.mock import Mock

import mootdx.protocol as protocol
from mootdx._protocol.parser.std.get_security_bars import GetSecurityBarsCmd


def test_public_extension_runs_with_the_client_request_lock():
    class CustomBars(protocol.GetSecurityBarsCmd):
        def call_api(self):
            assert self.lock is api.lock
            return [{'close': 1.0}]

    @protocol.last_ack_time
    def read_custom(api):
        parser = CustomBars(api.client, lock=api.lock)
        parser.setParams(9, 0, '000001', 0, 1)
        return parser.call_api()

    api = protocol.TdxHq_API()
    api.client = Mock()
    api.closed = False
    try:
        assert read_custom(api) == [{'close': 1.0}]
        assert api.last_error is None
        assert protocol.GetSecurityBarsCmd is GetSecurityBarsCmd
    finally:
        api.close()


def test_public_errors_and_profiles_are_available_without_a_second_stack():
    import sys

    assert protocol.TdxHq_API().handshake == 'minimal'
    assert protocol.ServerAdjustedTdxHqAPI().handshake == 'single'
    assert issubclass(protocol.TdxHandshakeRejected, protocol.TdxConnectionError)
    assert issubclass(protocol.TdxResponseError, protocol.TdxProtocolError)
    assert not any(name == 'tdxpy' or name.startswith('tdxpy.') for name in sys.modules)
