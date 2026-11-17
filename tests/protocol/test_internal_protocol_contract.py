import subprocess
import sys
import textwrap


def test_public_quote_stack_uses_internal_protocol_without_external_tdxpy():
    script = textwrap.dedent(
        """
        import importlib.abc
        import sys
        import tempfile
        from pathlib import Path

        home = tempfile.TemporaryDirectory(prefix='mootdx-child-home-')
        Path.home = classmethod(lambda cls: Path(home.name))
        def deny_network(event, args):
            if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto'}:
                raise AssertionError('internal protocol import attempted networking')
        sys.addaudithook(deny_network)


        class RejectExternalTdxpy(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "tdxpy" or fullname.startswith("tdxpy."):
                    raise ModuleNotFoundError("external tdxpy import is forbidden")
                return None


        sys.meta_path.insert(0, RejectExternalTdxpy())

        from mootdx import adjusted
        from mootdx import quotes
        from mootdx._protocol.exhq import TdxExHq_API
        from mootdx._protocol.hq import ServerAdjustedTdxHqAPI
        from mootdx._protocol.hq import TdxHq_API

        assert quotes.TdxHq_API is TdxHq_API
        assert quotes.TdxExHq_API is TdxExHq_API
        assert quotes.ServerAdjustedTdxHqAPI is ServerAdjustedTdxHqAPI
        assert adjusted.ServerAdjustedTdxHqAPI is ServerAdjustedTdxHqAPI
        assert not any(name == "tdxpy" or name.startswith("tdxpy.") for name in sys.modules)
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
