import unittest
from unittest.mock import patch

import pandas as pd
import pytest
from pathlib import Path

from mootdx import get_config_path
from mootdx.utils.adjust import get_xdxr


@pytest.fixture(autouse=True)
def fake_xdxr_provider(monkeypatch, tmp_path):
    import mootdx.utils.adjust as adjust
    monkeypatch.setattr(adjust, 'get_config_path', lambda name: str(tmp_path / Path(name).name))
    # The tests inspect their own imported helper as well.
    monkeypatch.setattr(__import__(__name__, fromlist=['get_config_path']),
                        'get_config_path', lambda name: str(tmp_path / Path(name).name))
    frame = pd.DataFrame([{'year': 2026, 'month': 1, 'day': 5, 'category': 1}])
    with patch.object(adjust.Quotes, 'factory') as factory:
        factory.return_value.xdxr.side_effect = lambda **kwargs: frame.copy()
        yield factory


class XDXRTestCase(unittest.TestCase):
    symbol = '600000'

    def test_no_cache(self):
        Path(get_config_path(f'xdxr/{self.symbol}.plk')).unlink(missing_ok=True)
        xdxr = get_xdxr(symbol=self.symbol)

        assert xdxr.empty is False
        assert 'code' in xdxr.columns, xdxr.columns

    def test_cached(self):
        xdxr = get_xdxr(symbol=self.symbol)
        xdxr = get_xdxr(symbol=self.symbol)

        assert xdxr.empty is False
        assert 'code' in xdxr.columns, xdxr.columns
