import pytest

from mootdx.exceptions import MootdxValidationException
from mootdx.quotes import StdQuotes


class FakeIndustryClient:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def get_report_file_by_size(self, filename):
        self.calls.append(filename)
        return self.content

    def close(self):
        pass


def _quotes(content):
    quotes = object.__new__(StdQuotes)
    quotes.client = FakeIndustryClient(content)
    return quotes


def test_industry_codes_parses_gbk_content_for_all_markets_without_file_io():
    content = (
        '\u3000\r\n'
        '0|000001|T1001|||X500102\r\n'
        '1|600000|T1001|||X500102\r\n'
        '2|920971|T1205|||X420201\r\n'
    ).encode('gbk')
    quotes = _quotes(bytearray(content))

    data = quotes.industry_codes()

    assert quotes.client.calls == ['tdxhy.cfg']
    assert data.columns.tolist() == ['market', 'code', 'tdx_industry', 'tdx_detail']
    assert data.to_dict('records') == [
        {'market': 0, 'code': '000001', 'tdx_industry': 'T1001', 'tdx_detail': 'X500102'},
        {'market': 1, 'code': '600000', 'tdx_industry': 'T1001', 'tdx_detail': 'X500102'},
        {'market': 2, 'code': '920971', 'tdx_industry': 'T1205', 'tdx_detail': 'X420201'},
    ]


def test_industry_codes_allows_unclassified_security():
    quotes = _quotes(b'2|920001||||')

    data = quotes.industry_codes()

    assert data.iloc[0].to_dict() == {
        'market': 2,
        'code': '920001',
        'tdx_industry': '',
        'tdx_detail': '',
    }


@pytest.mark.parametrize('content', [None, b'', b'\r\n \t\r\n'])
def test_industry_codes_rejects_empty_file(content):
    quotes = _quotes(content)

    with pytest.raises(MootdxValidationException, match='空文件'):
        quotes.industry_codes()


@pytest.mark.parametrize(
    'content, message',
    [
        (b'0|000001|T1001|X500102', '字段数量错误'),
        (b'3|000001|T1001|||X500102', '市场代码错误'),
        (b'0|00001|T1001|||X500102', '证券代码错误'),
        (b'0|000001|T1001|unexpected||X500102', '保留字段非空'),
        (b'0|000001|A1001|||X500102', '行业分类码错误'),
        (b'0|000001|T1001|||D500102', '细分分类码错误'),
        (b'\x81', 'GBK 文本'),
    ],
)
def test_industry_codes_rejects_non_empty_malformed_line(content, message):
    quotes = _quotes(content)

    with pytest.raises(MootdxValidationException, match=message):
        quotes.industry_codes()


def test_industry_codes_deduplicates_identical_records():
    quotes = _quotes(
        b'0|000001|T1001|||X500102\n'
        b'0|000001|T1001|||X500102\n'
    )

    data = quotes.industry_codes()

    assert len(data) == 1


def test_industry_codes_rejects_conflicting_duplicate():
    quotes = _quotes(
        b'0|000001|T1001|||X500102\n'
        b'0|000001|T1002|||X5101\n'
    )

    with pytest.raises(MootdxValidationException, match='证券分类冲突'):
        quotes.industry_codes()
