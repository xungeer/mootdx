import importlib

import httpx
import pytest

import mootdx.utils as utils
from mootdx.contrib import adjust as contrib_adjust
from mootdx.utils import adjust as utils_adjust
from mootdx.utils import factor as utils_factor


@pytest.fixture
def mocked_httpx(monkeypatch):
    requests = []
    clients = []
    client_options = []

    def handler(request):
        requests.append(request)
        url = str(request.url)

        if '10jqka' in url:
            return httpx.Response(
                200,
                text='callback({"data":"20240101,1,2,0,1,10,100,1"})',
                request=request,
            )

        if 'finance.sina.com.cn' in url:
            return httpx.Response(
                200,
                text='var factor={"data":[["2024-01-01","1.23"]]}\n',
                request=request,
            )

        if 'eastmoney.com' in url:
            return httpx.Response(
                200,
                json={'data': {'diff': []}},
                request=request,
            )

        if 'tdx.com.cn' in url:
            body = (
                '<textarea id="data" style="display:none;">'
                'date|holiday|country|exchange|extra\n'
                '20240101|元旦|中国|SH|x'
                '</textarea>'
            )
            return httpx.Response(200, content=body.encode('gbk'), request=request)

        return httpx.Response(404, text='not found', request=request)

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def client_factory(*args, **kwargs):
        client_options.append(dict(kwargs))
        kwargs['transport'] = transport
        client = original_client(*args, **kwargs)
        clients.append(client)
        return client

    def module_get(url, *args, **kwargs):
        with original_client(transport=transport) as client:
            return client.get(url, *args, **kwargs)

    monkeypatch.setattr(httpx, 'Client', client_factory)
    monkeypatch.setattr(httpx, 'get', module_get)

    yield requests, client_options

    for client in clients:
        client.close()


def test_httpx_client_paths_use_stable_public_contract(monkeypatch, mocked_httpx):
    requests, client_options = mocked_httpx
    monkeypatch.setattr(contrib_adjust.time, 'sleep', lambda _seconds: None)

    adjusted = contrib_adjust.get_adjust_year('600000', '2024', '01')
    factor = utils_adjust.fq_factor('qfq', 'sh600000')

    assert len(adjusted) == 1
    assert adjusted.iloc[0]['adjust'] == '1'
    assert len(factor) == 1
    assert factor.iloc[0]['qfq_factor'] == '1.23'
    assert any(options.get('verify') is False for options in client_options)
    assert any('10jqka' in str(request.url) for request in requests)
    assert any('finance.sina.com.cn' in str(request.url) for request in requests)


def test_httpx_top_level_get_paths_parse_text_encoding_and_json(
    monkeypatch,
    tmp_path,
    mocked_httpx,
):
    requests, _client_options = mocked_httpx
    holiday_module = importlib.import_module('mootdx.utils.holiday')

    def no_cache(*_args, **_kwargs):
        return lambda function: function

    monkeypatch.setattr(utils_factor, 'file_cache', no_cache)
    monkeypatch.setattr(utils_factor, 'get_config_path', lambda _name: tmp_path / 'factor.plk')

    factor = utils_factor.fq_factor('600000', 'qfq')
    stocks = utils.stock_bj_a()
    holidays = holiday_module._holiday.__wrapped__()

    assert len(factor) == 1
    assert factor.iloc[0]['factor'] == '1.23'
    assert stocks.empty
    assert list(holidays.columns) == ['日期', '节日', '国家', '交易所']
    assert holidays.iloc[0]['国家'] == '中国'
    assert any('eastmoney.com' in str(request.url) for request in requests)
    assert any('tdx.com.cn' in str(request.url) for request in requests)


def test_httpx_status_and_exception_contract():
    request = httpx.Request('GET', 'https://example.test/failure')
    response = httpx.Response(503, request=request)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        response.raise_for_status()

    connect_error = httpx.ConnectError('connection failed', request=request)

    assert isinstance(exc_info.value, httpx.HTTPError)
    assert isinstance(connect_error, httpx.HTTPError)
