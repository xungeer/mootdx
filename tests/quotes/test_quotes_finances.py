from collections import OrderedDict

import pytest

from mootdx.exceptions import MootdxValidationException
from mootdx.quotes import StdQuotes


def _finance_row(market, code):
    return OrderedDict(
        [
            ('market', market),
            ('code', code),
            ('liutongguben', 10000.0),
            ('province', 1),
            ('industry', 2),
            ('updated_date', 20260711),
            ('ipo_date', 19910403),
            ('zongguben', 20000.0),
        ]
    )


class FakeFinanceClient:
    def __init__(self, response_factory=None):
        self.calls = []
        self.response_factory = response_factory

    def get_finance_info(self, market, code):
        return _finance_row(market, code)

    def get_finance_info_batch(self, stocks):
        stocks = list(stocks)
        self.calls.append(stocks)
        if self.response_factory is not None:
            return self.response_factory(stocks)
        return [_finance_row(market, code) for market, code in stocks]

    def close(self):
        pass


def _quotes(client=None):
    quotes = object.__new__(StdQuotes)
    quotes.client = client or FakeFinanceClient()
    return quotes


def test_finances_pages_arbitrary_symbol_list_and_supports_all_markets():
    client = FakeFinanceClient()
    quotes = _quotes(client)
    symbols = ['000001', '600000', '920971'] + [f'601{index:03d}' for index in range(79)]

    data = quotes.finances(symbol=symbols)

    assert [len(batch) for batch in client.calls] == [80, 2]
    assert data['code'].tolist() == symbols
    assert set(data['market']) == {0, 1, 2}


def test_finances_has_same_columns_as_single_finance():
    quotes = _quotes()

    single = quotes.finance(symbol='600000')
    batch = quotes.finances(symbol=['600000'])

    assert batch.columns.tolist() == single.columns.tolist()
    assert batch.iloc[0].to_dict() == single.iloc[0].to_dict()


def test_finances_raises_when_batch_response_count_is_incomplete():
    client = FakeFinanceClient(
        response_factory=lambda stocks: [
            _finance_row(market, code) for market, code in stocks[:-1]
        ]
    )
    quotes = _quotes(client)

    with pytest.raises(MootdxValidationException, match='返回数量不完整'):
        quotes.finances(symbol=['000001', '600000'])


def test_finances_raises_when_batch_response_symbols_do_not_match():
    client = FakeFinanceClient(
        response_factory=lambda stocks: [
            _finance_row(stocks[0][0], '999999'),
            *[_finance_row(market, code) for market, code in stocks[1:]],
        ]
    )
    quotes = _quotes(client)

    with pytest.raises(MootdxValidationException, match='返回代码不匹配'):
        quotes.finances(symbol=['000001', '600000'])


@pytest.mark.parametrize('batch_size', [0, 81, True, 1.5])
def test_finances_rejects_invalid_batch_size(batch_size):
    quotes = _quotes()

    with pytest.raises(MootdxValidationException, match='batch_size'):
        quotes.finances(symbol=['000001'], batch_size=batch_size)


def test_finances_rejects_non_list_symbols():
    quotes = _quotes()

    with pytest.raises(MootdxValidationException, match='symbol'):
        quotes.finances(symbol='000001')
