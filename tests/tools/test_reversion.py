import unittest

import pandas as pd

from mootdx.quotes import Quotes
from mootdx.tools.reversion import _reversion, reversion
from mootdx.utils.adjust import get_xdxr


class TestReversion(unittest.TestCase):
    client = None
    symbol = '600000'

    # 初始化工作
    def setup_class(self):
        self.client = Quotes.factory(market='std', timeout=10)  # 标准市场

    # 退出清理工作
    def teardown_class(self):
        self.client.client.close()
        del self.client

    def test_get_xdxr(self):
        # data = self.client.bars(symbol=self.symbol)
        xdxr = get_xdxr(symbol=self.symbol)

        assert xdxr.empty is False
        assert 'code' in xdxr.columns

    def test_reversion(self):
        data = self.client.bars(symbol=self.symbol)
        xdxr = get_xdxr(symbol=self.symbol)

        reversion(self.symbol, data, xdxr, 'qfq')
        # self.assertFalse(result.empty)

    def test_xdxr_only_date_is_not_treated_as_a_trading_day(self):
        trading_dates = pd.to_datetime(['2026-07-09', '2026-07-11'])
        corporate_action_date = pd.to_datetime(['2026-07-10'])
        bfq_data = pd.DataFrame(
            {
                'open': [10.0, 10.5],
                'high': [10.8, 11.0],
                'low': [9.8, 10.2],
                'close': [10.5, 10.8],
                'volume': [1000.0, 1200.0],
            },
            index=trading_dates,
        )
        xdxr_data = pd.DataFrame(
            {
                'category': [1],
                'fenhong': [0.5],
                'peigu': [0.0],
                'peigujia': [0.0],
                'songzhuangu': [0.0],
            },
            index=corporate_action_date,
        )

        result = _reversion(bfq_data, xdxr_data, 'qfq')

        assert result.index.tolist() == trading_dates.tolist()

    def test_to_qfq(self):
        data = self.client.bars(symbol=self.symbol, offset=800)
        xdxr = get_xdxr(symbol=self.symbol)

        data0 = reversion(self.symbol, data, xdxr, 'qfq')
        assert data0.empty is False

        data1 = self.client.bars(symbol=self.symbol, offset=800, adjust='Qfq')
        assert data1.empty is False
        assert data1.equals(data0)

    def test_to_hfq(self):
        data = self.client.bars(symbol=self.symbol, offset=800)
        xdxr = get_xdxr(symbol=self.symbol)

        data0 = reversion(self.symbol, data, xdxr, 'hfq')
        assert data.empty is False

        data1 = self.client.bars(symbol=self.symbol, offset=800, adjust='HFQ')
        assert data1.empty is False
        assert data1.equals(data0)
