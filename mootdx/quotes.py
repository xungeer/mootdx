import math
import time
from datetime import datetime

import pandas
import pandas as pd
from tdxpy.exceptions import ValidationException
from tdxpy.exhq import TdxExHq_API
from tdxpy.hq import TdxHq_API
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import retry_if_result
from tenacity import stop_after_attempt
from tenacity import wait_random
from tqdm import tqdm

from mootdx import config
from mootdx.adjusted import ServerAdjustedTdxHqAPI
from mootdx.adjusted import SERVER_ADJUSTED_BAR_BATCH_SIZE
from mootdx.adjusted import normalize_adjust
from mootdx.adjusted import normalize_anchor_date
from mootdx.adjusted import normalize_period
from mootdx.consts import MARKET_SH
from mootdx.consts import MARKET_SZ
from mootdx.consts import MARKET_BJ
from mootdx.consts import return_last_value
from mootdx.exceptions import MootdxValidationException
from mootdx.logger import logger
from mootdx.server import check_server
from mootdx.utils import get_frequency
from mootdx.utils import get_stock_market
from mootdx.utils import get_stock_markets
from mootdx.utils import to_data


class Quotes(object):
    @staticmethod
    def factory(market='std', **kwargs):
        """
        股票市场 工厂方法

        :param market:  std 股票市场, ext 扩展市场， 默认股票市场
        :param kwargs:  可变参数
        :return: object
        """

        logger.debug(kwargs)

        if market == 'ext':
            return ExtQuotes(**kwargs)

        return StdQuotes(**kwargs)


def valid_server(server):
    import ipaddress

    if isinstance(server, tuple) or isinstance(server, list):
        try:
            address, port = server
            ipaddress.ip_address(address)
            return address, int(port)
        except Exception:
            raise ValueError('Server 格式错误. 例如: server = ("127.0.0.1", 2272)')

    return None


class BaseQuotes(object):
    client = None
    bestip = None
    server = None

    verbose = False
    timeout = 15

    def __init__(self, server=None, bestip: bool = False, timeout: int = None, **kwargs) -> None:
        logger.debug('config.setup()')
        config.setup()

        logger.debug(f'server => {server}')
        self.server = valid_server(server)

        logger.debug(f'bestip => {bestip}')
        bestip and check_server(sync=False)

        self.timeout = timeout or 15
        logger.debug(f'timeout => {self.timeout}')

        self.verbose = kwargs.get('verbose', False)
        logger.debug(f'verbose => {self.verbose}')

    def __del__(self):
        logger.debug('call __del__')
        self.close()

    def reconnect(self):
        if self.closed:
            logger.debug('服务器连接已断开，正进行重新连接...')
            self.client.connect(*self.bestip)

    def close(self):
        logger.debug('close')
        hasattr(self.client, 'close') and self.client.close()

    @property
    def closed(self) -> bool:
        if not hasattr(self.client.client, '_closed') or getattr(self.client.client, '_closed'):
            return True

        return False

    def pool(self):
        ...


instance: BaseQuotes


def check_empty(value):
    """
    重试判断函数

    :param value: 要判断的值
    :return:
    """
    _empty = value.all().empty if isinstance(value, pd.DataFrame) else not value

    # 判断状态空，则重连接
    if instance and _empty:
        logger.warning('返回数据空, 重新连接服务器...')
        # instance.client.connect(*instance.server)

    return _empty


class StdQuotes(BaseQuotes):
    """
    股票市场实时行情"""

    def __init__(self, server=None, bestip=False, timeout=15, heartbeat=False, auto_retry=True, raise_exception=False,
                 **kwargs):
        """构造函数

        :param bestip:  最佳 IP
        :param timeout: 超时时间
        :param kwargs:  可变参数
        """

        super().__init__(bestip=bestip, timeout=timeout, server=server, **kwargs)
        self.server and config.set('BESTIP', {'HQ': self.server})

        try:
            config.get('SERVER').get('HQ')[0]
        except ValueError as ex:
            logger.warning(ex)
        finally:
            default = config.get('SERVER').get('HQ')[0][1:]
            self.server = config.get('BESTIP').get('HQ', default)

        logger.debug(f'server: {self.server}')
        ip, port = self.server

        self.client = TdxHq_API(heartbeat=heartbeat, auto_retry=auto_retry, raise_exception=raise_exception)
        self.client.connect(ip, int(port), time_out=timeout)

        global instance
        instance = self

    def traffic(self):
        return self.client.get_traffic_stats()

    def quotes(self, symbol=None, **kwargs):
        """
        获取实时日行情数据

        :param symbol: 股票代码
        :return: pd.dataFrame or None
        """

        if not symbol:
            return to_data(None)

        if type(symbol) is str:
            symbol = [symbol]

        try:
            symbol = get_stock_markets(symbol)
            result = self.client.get_security_quotes(symbol)
        except ValidationException:
            return to_data(None)

        return to_data(result, symbol=symbol, client=self, **kwargs)

    def bars(self, symbol='000001', frequency=9, start=0, offset=800, **kwargs):
        """
        获取实时日K线数据

        :param symbol: 股票代码
        :param frequency: 数据频次
        :param start: 开始位置
        :param offset: 每次获取条数 (支持超过800条，会自动分页请求)
        :return: pd.dataFrame or None
        """
        frequency = get_frequency(frequency)
        market = get_stock_market(symbol)

        # 服务器单次请求最大返回约800条数据，超过则需要分页请求
        BATCH_SIZE = 800
        
        if offset <= BATCH_SIZE:
            result = self.client.get_security_bars(int(frequency), int(market), str(symbol), int(start), int(offset))
            return to_data(result, symbol=symbol, client=self, **kwargs)
        
        # 分页请求以突破800条限制
        all_data = []
        remaining = offset
        current_start = start
        
        while remaining > 0:
            batch_count = min(remaining, BATCH_SIZE)
            result = self.client.get_security_bars(int(frequency), int(market), str(symbol), int(current_start), int(batch_count))
            
            if not result:
                break
                
            all_data = result + all_data
            fetched = len(result)
            
            if fetched < batch_count:
                break
                
            remaining -= fetched
            current_start += fetched
            
            # 添加请求间隔，避免触发服务器限流
            if remaining > 0:
                time.sleep(0.3)
        
        return to_data(all_data, symbol=symbol, client=self, **kwargs)

    def adjusted_bars(
        self,
        symbol='000001',
        frequency=9,
        start=0,
        offset=800,
        adjust='qfq',
        anchor_date=None,
        **kwargs,
    ):
        """通过通达信 0x052d 服务端参数直接获取复权 K 线，不使用外部因子。"""
        category, period_param = normalize_period(frequency)

        if isinstance(start, bool) or not isinstance(start, int) or start < 0 or start > 0xFFFF:
            raise ValueError('start 必须是 0 到 65535 之间的整数')
        if isinstance(offset, bool) or not isinstance(offset, int) or offset <= 0:
            raise ValueError('offset 必须是大于 0 的整数')
        if not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isascii():
            raise ValueError('股票代码必须是 6 位 ASCII 字符')

        batch_size = SERVER_ADJUSTED_BAR_BATCH_SIZE
        max_offset = ((0xFFFF - start) // batch_size + 1) * batch_size
        if offset > max_offset:
            raise ValueError(f'当前 start 最多可分页获取 {max_offset} 条 K 线')

        market = get_stock_market(symbol)
        adjust_mode = normalize_adjust(adjust)
        anchor_date_raw = normalize_anchor_date(anchor_date)

        if adjust_mode in [3, 4] and not anchor_date_raw:
            raise ValueError('定点复权必须提供 anchor_date')
        if category == 13 and adjust_mode != 0:
            raise ValueError('通达信秒线不支持服务端复权, adjust 必须为 none')

        api = ServerAdjustedTdxHqAPI(
            heartbeat=False,
            auto_retry=self.client.auto_retry,
            raise_exception=self.client.raise_exception,
        )
        ip, port = self.server

        try:
            if not api.connect(ip, int(port), time_out=self.timeout):
                return to_data(None)

            if offset <= batch_size:
                result = api.get_server_adjusted_bars(
                    category,
                    int(market),
                    str(symbol),
                    int(start),
                    int(offset),
                    adjust_mode,
                    anchor_date_raw,
                    period_param,
                )
                return to_data(result, symbol=symbol, client=self, **kwargs)

            all_data = []
            remaining = offset
            current_start = start

            while remaining > 0:
                batch_count = min(remaining, batch_size)
                result = api.get_server_adjusted_bars(
                    category,
                    int(market),
                    str(symbol),
                    int(current_start),
                    int(batch_count),
                    adjust_mode,
                    anchor_date_raw,
                    period_param,
                )

                if not result:
                    break

                all_data = result + all_data
                fetched = len(result)

                if fetched < batch_count:
                    break

                remaining -= fetched
                # 13/N 秒线从 start=0 翻到第二页时会包含上一页最旧记录，
                # 仅首次需额外跳过一条；后续页恢复普通偏移语义。
                current_start += fetched + (1 if category == 13 and current_start == 0 else 0)

                if remaining > 0:
                    time.sleep(0.3)

            return to_data(all_data, symbol=symbol, client=self, **kwargs)
        finally:
            api.close()

    def stock_count(self, market=MARKET_SH):
        """
        获取市场股票数量

        :param market: 股票市场代码 sh 上海， sz 深圳， bj 北京
        :return: pd.dataFrame or None
        """
        if market not in [0, 1, 2]:
            raise MootdxValidationException('市场代码错误')

        result = self.client.get_security_count(market=market)

        return result

    def stocks(self, market=MARKET_SH):
        """
        获取股票列表

        :param market: 股票市场
        :return:
        """

        if market not in [0, 1, 2]:
            raise MootdxValidationException('市场代码错误, 目前只支持沪深京市场')

        counts = self.stock_count(market=market)
        page_size = 1000
        pages = []

        if counts > 0:
            for start in tqdm(range(0, counts, page_size), ascii=True):
                result = self.client.get_security_list(market=market, start=start, limit=page_size)
                page = to_data(result)
                expected_count = min(page_size, counts - start)
                if page is None or len(page) != expected_count:
                    actual_count = 0 if page is None else len(page)
                    raise MootdxValidationException(
                        f'股票列表分页不完整: market={market}, start={start}, '
                        f'expected={expected_count}, actual={actual_count}'
                    )
                pages.append(page)

        stocks = pandas.concat(pages, ignore_index=True) if pages else None
        if stocks is not None and len(stocks) != counts:
            raise MootdxValidationException(
                f'股票列表数量不完整: market={market}, expected={counts}, actual={len(stocks)}'
            )

        return stocks

    def stock_all(self):
        stocks = None

        for m in [0, 1, 2]:
            stocks = pandas.concat([stocks, self.stocks(m)], ignore_index=True)

        return stocks

    def index_bars(self, symbol='000001', frequency=9, start=0, offset=800, **kwargs):
        """
        获取指数k线

        :param symbol: 股票代码
        :param frequency: 数据频次
        :param start: 开始位置
        :param offset: 获取数量 (支持超过800条，会自动分页请求)
        :return:
        """
        frequency = get_frequency(frequency)
        market = (MARKET_SZ, MARKET_SH, MARKET_BJ)[symbol[:2] in ['00', '88', '99', '89']]
        
        # 服务器单次请求最大返回约800条数据，超过则需要分页请求
        BATCH_SIZE = 800
        
        if offset <= BATCH_SIZE:
            result = self.client.get_index_bars(int(frequency), int(market), str(symbol), int(start), int(offset))
            return to_data(result, symbol=symbol, client=self, **kwargs)
        
        # 分页请求以突破800条限制
        all_data = []
        remaining = offset
        current_start = start
        
        while remaining > 0:
            batch_count = min(remaining, BATCH_SIZE)
            result = self.client.get_index_bars(int(frequency), int(market), str(symbol), int(current_start), int(batch_count))
            
            if not result:
                break
                
            all_data = result + all_data
            fetched = len(result)
            
            if fetched < batch_count:
                break
                
            remaining -= fetched
            current_start += fetched
            
            # 添加请求间隔，避免触发服务器限流
            if remaining > 0:
                time.sleep(0.3)
        
        return to_data(all_data, symbol=symbol, client=self, **kwargs)

    def minute(self, symbol=None, **kwargs):
        """
        获取实时分时数据

        :param symbol: 股票代码
        :return: pd.DataFrame
        """

        today = datetime.now().strftime('%Y%m%d')
        return self.minutes(symbol=symbol, date=today, **kwargs)

    def minutes(self, symbol=None, date='20191023', **kwargs):
        """
        分时历史数据

        :param symbol:  股票代码
        :param date:    查询日期
        :return: pd.dataFrame or None
        """

        market = get_stock_market(symbol)

        if market not in [0, 1, 2]:
            raise MootdxValidationException('市场代码错误, 目前只支持沪深京市场')

        result = self.client.get_history_minute_time_data(market=market, code=symbol, date=date)

        return to_data(result, symbol=symbol, client=self, **kwargs)

    def transaction(self, symbol='', start=0, offset=800, **kwargs):
        """
        查询分笔成交

        :param symbol:  股票代码
        :param start:   起始位置
        :param offset:  结束位置
        :return: pd.dataFrame or None
        """

        market = get_stock_market(symbol)

        result = self.client.get_transaction_data(int(market), symbol, start, offset)

        return to_data(result, symbol=symbol, client=self, **kwargs)

    def transactions(self, symbol='', start=0, offset=800, date='20170209', **kwargs):
        """
        查询历史分笔成交

        :param symbol:  股票代码
        :param start:   起始位置
        :param offset:  获取数量
        :param date:    查询日期
        :return: pd.dataFrame or None
        """

        market = get_stock_market(symbol, string=False)

        if market not in [0, 1, 2]:
            raise MootdxValidationException('市场代码错误, 目前只支持沪深京市场')

        result = self.client.get_history_transaction_data(market, symbol, start, offset, int(date))
        return to_data(result, symbol=symbol, client=self, **kwargs)

    def F10C(self, symbol=''):  # noqa
        """
        查询公司信息目录

        :param symbol: 股票代码
        :return: pd.dataFrame or None
        """

        market = int(get_stock_market(symbol))

        if market not in [0, 1, 2 ]:
            raise MootdxValidationException('市场代码错误, 目前只支持沪深京市场')

        result = self.client.get_company_info_category(market, symbol)

        return result

    def F10(self, symbol='', name=''):  # noqa
        """
        读取公司信息详情

        :param name: 公司 F10 标题
        :param symbol: 股票代码
        :return: pd.dataFrame or None
        """

        result = {}
        market = int(get_stock_market(symbol, string=False))

        if market not in [0, 1, 2]:
            raise MootdxValidationException('市场代码错误, 目前只支持沪深京市场')

        category = self.client.get_company_info_category(market, symbol)

        if not category:
            return None

        if name:
            for x in category:
                if x['name'] == name:
                    return self.client.get_company_info_content(
                        market=market,
                        code=symbol,
                        filename=x['filename'],
                        start=x['start'],
                        length=x['length'],
                    )

        for x in category:
            result[x['name']] = self.client.get_company_info_content(
                market=market, code=symbol, filename=x['filename'], start=x['start'], length=x['length']
            )

        return result

    def xdxr(self, symbol='', **kwargs):
        """
        读取除权除息信息

        :param symbol: 股票代码
        :return: pd.dataFrame or None
        """

        market = get_stock_market(symbol)
        result = self.client.get_xdxr_info(int(market), symbol)

        return to_data(result, symbol=symbol, client=self, **kwargs)

    def finance(self, symbol='000001', **kwargs):
        """
        读取财务信息

        :param symbol: 股票代码
        :return:
        """

        market = get_stock_market(symbol)
        result = self.client.get_finance_info(market=market, code=symbol)

        return to_data(result, symbol=symbol, client=self, **kwargs)

    def finances(self, symbol=None, batch_size=80, **kwargs):
        """
        批量读取财务信息

        :param symbol: 股票代码列表
        :param batch_size: 每批请求数量，最大 80
        :return: pd.DataFrame
        """

        if not symbol:
            return to_data(None)

        if not isinstance(symbol, list):
            raise MootdxValidationException('symbol 必须是股票代码列表')

        if type(batch_size) is not int or not 1 <= batch_size <= 80:
            raise MootdxValidationException('batch_size 必须是 1 到 80 之间的整数')

        try:
            stocks = get_stock_markets(symbol)
        except (AssertionError, TypeError, ValueError) as exc:
            raise MootdxValidationException(f'股票代码列表无效: {exc}') from exc

        records = []
        for start in range(0, len(stocks), batch_size):
            batch = stocks[start : start + batch_size]
            result = self.client.get_finance_info_batch(batch)
            actual_count = len(result) if isinstance(result, list) else 0

            if actual_count != len(batch):
                raise MootdxValidationException(
                    f'批量财务信息返回数量不完整: start={start}, '
                    f'expected={len(batch)}, actual={actual_count}'
                )

            try:
                actual_stocks = [(item['market'], item['code']) for item in result]
            except (KeyError, TypeError) as exc:
                raise MootdxValidationException(
                    f'批量财务信息返回缺少 market/code: start={start}'
                ) from exc

            if sorted(actual_stocks) != sorted((market, code) for market, code in batch):
                raise MootdxValidationException(
                    f'批量财务信息返回代码不匹配: start={start}, '
                    f'expected={batch}, actual={actual_stocks}'
                )

            records.extend(result)

        return to_data(records, symbol=symbol, client=self, **kwargs)

    def industry_codes(self):
        """
        读取通达信行业分类码

        :return: 包含 market、code、tdx_industry、tdx_detail 的 pd.DataFrame
        """

        content = self.client.get_report_file_by_size('tdxhy.cfg')
        if content is None:
            raise MootdxValidationException('tdxhy.cfg 返回空文件')
        if isinstance(content, str):
            text = content
        elif isinstance(content, (bytes, bytearray, memoryview)):
            try:
                text = bytes(content).decode('gbk')
            except UnicodeDecodeError as exc:
                raise MootdxValidationException('tdxhy.cfg 不是有效的 GBK 文本') from exc
        else:
            raise MootdxValidationException('tdxhy.cfg 返回类型错误')

        if not text.strip():
            raise MootdxValidationException('tdxhy.cfg 返回空文件')

        records = {}
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            if not raw_line.strip():
                continue

            fields = raw_line.split('|')
            if len(fields) != 6:
                raise MootdxValidationException(
                    f'tdxhy.cfg 第 {line_number} 行字段数量错误: expected=6, actual={len(fields)}'
                )

            market_value, code, tdx_industry, reserved1, reserved2, tdx_detail = fields
            if market_value not in {'0', '1', '2'}:
                raise MootdxValidationException(
                    f'tdxhy.cfg 第 {line_number} 行市场代码错误: {market_value!r}'
                )
            if len(code) != 6 or not code.isascii() or not code.isdigit():
                raise MootdxValidationException(
                    f'tdxhy.cfg 第 {line_number} 行证券代码错误: {code!r}'
                )
            if reserved1 or reserved2:
                raise MootdxValidationException(
                    f'tdxhy.cfg 第 {line_number} 行保留字段非空'
                )
            if tdx_industry and not (
                tdx_industry.startswith('T')
                and tdx_industry[1:].isascii()
                and tdx_industry[1:].isdigit()
            ):
                raise MootdxValidationException(
                    f'tdxhy.cfg 第 {line_number} 行通达信行业分类码错误: {tdx_industry!r}'
                )
            if tdx_detail and not (
                tdx_detail.startswith('X')
                and tdx_detail[1:].isascii()
                and tdx_detail[1:].isdigit()
            ):
                raise MootdxValidationException(
                    f'tdxhy.cfg 第 {line_number} 行通达信细分分类码错误: {tdx_detail!r}'
                )

            market = int(market_value)
            key = (market, code)
            record = {
                'market': market,
                'code': code,
                'tdx_industry': tdx_industry,
                'tdx_detail': tdx_detail,
            }
            previous = records.get(key)
            if previous is not None and previous != record:
                raise MootdxValidationException(
                    f'tdxhy.cfg 第 {line_number} 行证券分类冲突: market={market}, code={code}'
                )
            records[key] = record

        if not records:
            raise MootdxValidationException('tdxhy.cfg 没有有效记录')

        columns = ['market', 'code', 'tdx_industry', 'tdx_detail']
        return pd.DataFrame.from_records(list(records.values()), columns=columns)

    def k(self, symbol='', begin=None, end=None, **kwargs):
        """
        读取k线信息

        :param symbol:  股票代码
        :param begin:   开始日期
        :param end:     截止日期
        :return: pd.dataFrame or None
        """

        result = self.get_k_data(symbol, begin, end)
        return to_data(result, symbol=symbol, **kwargs)

    def ohlc(self, **kwargs):
        return self.k(**kwargs)

    def get_k_data(self, code, start_date, end_date):
        # 开始时间离现在有几天
        first = (pd.to_datetime(end_date) - pd.to_datetime(datetime.now().date())).days
        first = (abs(first), 0)[first >= 0]

        # 结束时间离现在有几天
        last = (pd.to_datetime(start_date) - pd.to_datetime(datetime.now().date())).days
        last = (abs(last), 0)[last >= 0]

        # 去除节假日
        first -= int(first / 2.8)  # 非交易日大概是全年的1/3
        last -= int(last / 3.5)  # 非交易日大概是全年的1/3

        temp = []
        market = get_stock_market(code)

        for i in range(math.ceil((last - first) / 800)):
            data = self.client.get_security_bars(9, market, code, (first + i * 800), 800)
            temp.append(self.client.to_df(data))

        data = pd.concat(temp)
        data = data.assign(date=data['datetime'].apply(lambda x: str(x)[0:10])).assign(code=str(code))
        data = data.set_index('date', drop=False, inplace=False)
        data = data.drop(['year', 'month', 'day', 'hour', 'minute', 'datetime'], axis=1)
        data = data.loc[(data.date >= start_date) & (data.date < end_date)]
        data = data.sort_index()

        return data

    def index(self, symbol='000001', frequency=9, start=0, offset=800, **kwargs):
        """
        获取指数k线

        K线种类:
        - 0 5分钟K线
        - 1 15分钟K线
        - 2 30分钟K线
        - 3 1小时K线
        - 4 日K线
        - 5 周K线
        - 6 月K线
        - 7 1分钟
        - 8 1分钟K线
        - 9 日K线
        - 10 季K线
        - 11 年K线

        :param symbol:      股票代码
        :param frequency:   数据频次
        :param market:      证券市场
        :param start:       开始位置
        :param offset:      每次获取条数 (支持超过800条，会自动分页请求)
        :return: pd.dataFrame or None
        """
        frequency = get_frequency(frequency)
        market = (MARKET_SZ, MARKET_SH, MARKET_BJ)[symbol[:2] in ['00', '88', '99', '89']]
        
        # 服务器单次请求最大返回约800条数据，超过则需要分页请求
        BATCH_SIZE = 800
        
        if offset <= BATCH_SIZE:
            # 单次请求即可满足
            result = self.client.get_index_bars(int(frequency), int(market), str(symbol), int(start), int(offset))
            return to_data(result, symbol=symbol, client=self, **kwargs)
        
        # 分页请求以突破800条限制
        all_data = []
        remaining = offset
        current_start = start
        
        while remaining > 0:
            batch_count = min(remaining, BATCH_SIZE)
            result = self.client.get_index_bars(int(frequency), int(market), str(symbol), int(current_start), int(batch_count))
            
            if not result:
                break
                
            all_data = result + all_data
            fetched = len(result)
            
            # 如果返回数据少于请求数量，说明已到数据末尾
            if fetched < batch_count:
                break
                
            remaining -= fetched
            current_start += fetched
            
            # 添加请求间隔，避免触发服务器限流
            if remaining > 0:
                time.sleep(0.3)
        
        return to_data(all_data, symbol=symbol, client=self, **kwargs)

    def block(self, tofile='block.dat', **kwargs):
        """
        获取证券板块信息

        :param tofile: 保存文件
        :return: pd.dataFrame or None
        """

        result = self.client.get_and_parse_block_info(tofile)
        return to_data(result, **kwargs)


class ExtQuotes(BaseQuotes):
    """扩展市场实时行情"""

    server = ("218.75.75.18", 7720)

    def __init__(self, server: list = None, bestip=False, timeout=15, **kwargs):
        """
        构造函数

        :param bestip:  最优服务器IP
        :param timeout: 超时时间
        :param kwargs:  可变参数
        """
        super().__init__(bestip=bestip, timeout=timeout, server=server, **kwargs)
        self.server and config.set('BESTIP', {'EX': self.server})

        # 扩展市场行情接口（期货、港股通等）

        try:
            config.get('SERVER').get('EX')[0]
        except ValueError as ex:
            logger.warning(ex)
        finally:
            default = config.get('SERVER').get('EX')[0]
            self.server = config.get('BESTIP').get('EX', default)

        for x in ['verbose', 'server', 'quiet']:
            if x in kwargs.keys():
                del kwargs[x]

        try:
            self.client = TdxExHq_API(raise_exception=False, auto_retry=True, **kwargs)
            self.client.connect(*self.server)
        except Exception:  # noqa
            logger.error('服务器连接超时.')

        global instance
        instance = self

    @staticmethod
    def validate(market, symbol):
        """
        验证股票市场

        :param market: 股票市场
        :param symbol: 股票代码
        :return: tuple
        """

        if not market:
            if len(symbol.split('#')) > 1:
                market = symbol.split('#')[0]
                symbol = symbol.split('#')[1]

        if not market:
            raise ValueError('市场参数错误, 市场参数不能为空.')

        return int(market), symbol

    @retry(
        wait=wait_random(min=1, max=10),
        stop=stop_after_attempt(3),
        retry_error_callback=return_last_value,
        retry=(retry_if_exception_type() | retry_if_result(check_empty)),
    )
    def markets(self, **kwargs):
        """
        获取实时市场列表

        :return: pd.dataFrame or None
        """

        result = self.client.get_markets()
        return to_data(result, **kwargs)

    @retry(
        wait=wait_random(min=1, max=10),
        stop=stop_after_attempt(3),
        retry_error_callback=return_last_value,
        retry=(retry_if_exception_type() | retry_if_result(check_empty)),
    )
    def instrument(self, start=0, offset=800, **kwargs):
        """
        查询代码列表

        :param start:   开始位置
        :param offset:  获取数量
        :return:
        """

        result = self.client.get_instrument_info(start=start, count=offset)
        return to_data(result, **kwargs)

    @retry(
        wait=wait_random(min=1, max=10),
        stop=stop_after_attempt(3),
        retry_error_callback=return_last_value,
        retry=(retry_if_exception_type() | retry_if_result(check_empty)),
    )
    def instrument_count(self):
        """
        市场商品数量

        :return:
        """

        result = self.client.get_instrument_count()

        return result

    @retry(
        wait=wait_random(min=1, max=10),
        stop=stop_after_attempt(3),
        retry_error_callback=return_last_value,
        retry=(retry_if_exception_type() | retry_if_result(check_empty)),
    )
    def instruments(self, **kwargs):
        """
        查询所有代码列表

        :return:
        """

        result = []

        count = self.client.get_instrument_count()
        pages = math.ceil(count / 100)

        for page in tqdm(range(0, pages), ascii=True):
            result += self.client.get_instrument_info(page * 100, 100)

        return to_data(result, **kwargs)

    @retry(
        wait=wait_random(min=1, max=10),
        stop=stop_after_attempt(3),
        retry_error_callback=return_last_value,
        retry=(retry_if_exception_type() | retry_if_result(check_empty)),
    )
    def quote(self, market='', symbol='', **kwargs):
        """
        查询五档行情

        :param market: 市场ID
        :param symbol: 证券代码
        :return:
        """

        market, symbol = self.validate(market, symbol)
        result = self.client.get_instrument_quote(market, symbol)

        return to_data(result, symbol=symbol, client=self, **kwargs)

    @retry(
        wait=wait_random(min=1, max=10),
        stop=stop_after_attempt(3),
        retry_error_callback=return_last_value,
        retry=(retry_if_exception_type() | retry_if_result(check_empty)),
    )
    def minute(self, market='', symbol='', **kwargs):
        """
        查询分时行情

        :param market: 市场ID
        :param symbol: 证券代码
        :return:
        """

        market, symbol = self.validate(market, symbol)
        result = self.client.get_minute_time_data(market, symbol)

        return to_data(result, symbol=symbol, client=self, **kwargs)

    @retry(
        wait=wait_random(min=1, max=10),
        stop=stop_after_attempt(3),
        retry_error_callback=return_last_value,
        retry=(retry_if_exception_type() | retry_if_result(check_empty)),
    )
    def minutes(self, market=None, symbol='', date='', **kwargs):
        """
        查询历史分时行情

        :param market:  市场ID
        :param symbol:  证券代码
        :param date:    查询日期
        :return:
        """

        market, symbol = self.validate(market, symbol)
        result = self.client.get_history_minute_time_data(market, symbol, date)

        return to_data(result, symbol=symbol, client=self, **kwargs)

    @retry(
        wait=wait_random(min=1, max=10),
        stop=stop_after_attempt(3),
        retry_error_callback=return_last_value,
        retry=(retry_if_exception_type() | retry_if_result(check_empty)),
    )
    def bars(self, frequency='', market='', symbol='', start=0, offset=800, **kwargs):
        """
        查询k线数据

        :param frequency: 数据频次, K线周期
        :param market: 市场ID
        :param symbol: 证券代码
        :param start:  起始位置
        :param offset: 获取数量 (支持超过700条，会自动分页请求)
        :return:
        """

        frequency = get_frequency(frequency)
        market, symbol = self.validate(market, symbol)
        
        # 扩展市场服务器单次请求最大返回约700条数据，超过则需要分页请求
        BATCH_SIZE = 700
        
        if offset <= BATCH_SIZE:
            result = self.client.get_instrument_bars(
                category=frequency, market=market, code=symbol, start=start, count=offset
            )
            return to_data(result, symbol=symbol, **kwargs)
        
        # 分页请求以突破700条限制
        # 注意：通达信API的start参数表示从最新数据往回的偏移量
        # start=0返回最新数据，start=700返回更早的历史数据
        # 每批数据内部已按时间从旧到新排序，但后获取的批次是更早的历史数据
        # 因此需要将后获取的数据插入到列表前面
        all_data = []
        remaining = offset
        current_start = start
        
        while remaining > 0:
            batch_count = min(remaining, BATCH_SIZE)
            result = self.client.get_instrument_bars(
                category=frequency, market=market, code=symbol, start=current_start, count=batch_count
            )
            
            if not result:
                break
            
            # 将历史数据插入到列表前面，保持时间顺序（从旧到新）
            all_data = result + all_data
            fetched = len(result)
            
            # 如果返回数据少于请求数量，说明已到数据末尾
            if fetched < batch_count:
                break
                
            remaining -= fetched
            current_start += fetched
            
            # 添加请求间隔，避免触发服务器限流
            if remaining > 0:
                time.sleep(0.3)
        
        return to_data(all_data, symbol=symbol, **kwargs)

    @retry(
        wait=wait_random(min=1, max=10),
        stop=stop_after_attempt(3),
        retry_error_callback=return_last_value,
        retry=(retry_if_exception_type() | retry_if_result(check_empty)),
    )
    def transaction(self, market=None, symbol='', start=0, offset=800, **kwargs):
        """
        查询分笔成交

        :param market: 市场ID
        :param symbol: 证券代码
        :param start:  开始位置
        :param offset: 获取数量
        :return:
        """

        market, symbol = self.validate(market, symbol)
        result = self.client.get_transaction_data(market=market, code=symbol, start=start, count=offset)

        return to_data(result, symbol=symbol, client=self, **kwargs)

    @retry(
        wait=wait_random(min=1, max=10),
        stop=stop_after_attempt(3),
        retry_error_callback=return_last_value,
        retry=(retry_if_exception_type() | retry_if_result(check_empty)),
    )
    def transactions(self, market=None, symbol='', date='', start=0, offset=800, **kwargs):
        """
        查询历史分笔成交

        :param market:  市场ID
        :param symbol:  证券代码
        :param date:    查询日期
        :param start:   开始位置
        :param offset:  获取数量
        :return:
        """

        market, symbol = self.validate(market, symbol)
        result = self.client.get_history_transaction_data(
            market=market, code=symbol, date=int(date), start=start, count=offset
        )

        return to_data(result, symbol=symbol, client=self, **kwargs)
