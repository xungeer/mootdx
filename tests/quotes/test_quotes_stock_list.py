import unittest

from mootdx.consts import MARKET_BJ
from mootdx.exceptions import MootdxValidationException
from mootdx.quotes import StdQuotes


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_security_list(self, market, start, limit):
        self.calls.append((market, start, limit))
        count = min(limit, 1001 - start)
        return [
            {
                'code': f'{920001 + start + offset:06d}',
                'volunit': 100,
                'decimal_point': 2,
                'name': '北交所样本',
                'pre_close': 10.0,
            }
            for offset in range(count)
        ]


class TestStdQuotesStockList(unittest.TestCase):
    def test_bj_market_uses_explicit_pagination_limit(self):
        client = FakeClient()
        quotes = StdQuotes.__new__(StdQuotes)
        quotes.client = client
        quotes.stock_count = lambda market: 1001

        try:
            result = quotes.stocks(market=MARKET_BJ)
        finally:
            quotes.client = None

        self.assertEqual(client.calls, [(MARKET_BJ, 0, 1000), (MARKET_BJ, 1000, 1000)])
        self.assertEqual(len(result), 1001)
        self.assertEqual(result['code'].iloc[[0, -1]].tolist(), ['920001', '921001'])
        self.assertEqual(
            list(result.columns),
            ['code', 'volunit', 'decimal_point', 'name', 'pre_close'],
        )

    def test_rejects_short_non_final_page(self):
        client = FakeClient()
        quotes = StdQuotes.__new__(StdQuotes)
        quotes.client = client
        quotes.stock_count = lambda market: 1001
        original_get = client.get_security_list

        def short_first_page(market, start, limit):
            result = original_get(market, start, limit)
            return result[:-1] if start == 0 else result

        client.get_security_list = short_first_page

        with self.assertRaisesRegex(MootdxValidationException, '分页不完整'):
            quotes.stocks(market=MARKET_BJ)


if __name__ == '__main__':
    unittest.main()
