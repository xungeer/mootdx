# 标准行情接口

下面是如何在程序里面调用本接口

**参数说明:**

- market: 对应市场。 (std 标准股票市场，ext 扩展市场)

** 调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')
```

### 其他参数

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std', multithread=True, heartbeat=True, bestip=False, timeout=15)
# multithread 多线程
# heartbeat 开启心跳包
# bestip 重新测试最快服务器
# server 自行设置服务器IP, 格式 `server=('127.0.0.1', 7727)`
# timeout 设置超时时间
# quiet 日志静默方式, 默认False, 设置为 True 则不打印日志信息
# verbose 日志显示等级 0, 静默模式, 1 一般级别, 2 详细级别
```

## 01. 查询实时行情

可以获取**多**只股票的行情信息

**参数说明: **

- symbol: 多个股票号码。 `["000001", "600300"]` 格式

返回值：

- pd.DataFrame

**调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')
client.quotes(symbol=["000001", "600300"])
```

## 02. 获取k线数据

**调用方法：**

`frequency` 的固定周期如下：

| 编号 | 推荐字符串 | 含义 |
| ---: | --- | --- |
| 0 | `5m` | 5 分钟 |
| 1 | `15m` | 15 分钟 |
| 2 | `30m` | 30 分钟 |
| 3 | `1h` / `60m` | 60 分钟 |
| 4 | `days` | 兼容日线口径，成交量是 `day` 的约 100 倍 |
| 5 | `week` | 周线 |
| 6 | `mon` / `month` | 月线 |
| 7 | `ex_1m` | 兼容 1 分钟口径 |
| 8 | `1m` | 1 分钟 |
| 9 | `day` | 日线 |
| 10 | `3mon` / `quarter` | 季线 |
| 11 | `year` | 年线 |

`adjusted_bars()` 还支持通达信扩展周期：`2m`、`10m` 等任意 N 分钟使用
`8/N`，`2d`、`5d` 等任意 N 日使用 `9/N`，`5s`、`15s` 等任意 N 秒使用
`13/N`。N 必须是 1 到 32767 的整数；服务端是否有对应数据仍以实际返回为准。
也可以用 `(period_type, period_param)` 二元组直接传协议值。

协议参数范围不等于有意义的聚合范围。A 股主站实测中，自定义分钟通常在
`1m` 到 `239m` 内有日内聚合意义，达到或超过 240 分钟会退化为每交易日最多一根；
自定义秒线通常在 `1s` 到 `14399s` 内有日内聚合意义，达到或超过 14400 秒也
会退化为每交易日最多一根。秒线按实际成交生成，不保证每个时间桶都有记录。

如

**调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')
client.bars(symbol='600036', frequency=9, offset=10)

# 通达信服务端前复权，不访问新浪、同花顺或东方财富复权因子
client.adjusted_bars(symbol='600036', adjust='qfq')

# 通达信服务端后复权
client.adjusted_bars(symbol='600036', adjust='hfq')

# 定点前复权
client.adjusted_bars(
    symbol='600036',
    adjust='fixed_qfq',
    anchor_date='2024-06-03',
)

# 自定义 10 分钟、2 日和 5 秒 K 线
client.adjusted_bars(symbol='600036', frequency='10m', adjust='qfq')
client.adjusted_bars(symbol='600036', frequency='2d', adjust='qfq')
client.adjusted_bars(symbol='600036', frequency='5s', adjust='none')
```

`adjusted_bars()` 使用通达信行情主站 `0x052d` 的服务端复权参数，返回结构与
`bars()` 兼容；秒线会额外返回 `second` 列，`datetime` 精确到秒。通达信主站
单次稳定返回上限为 800 条，`offset` 大于 800 时 mootdx 会按 800 条自动分页，
因此一次公共接口调用不局限于 800 条。`start` 是 0 到 65535 的 16 位无符号位置
字段；按当前分页策略，`start=0` 时一次公共调用最多请求 65600 条，非零 start
的上限会相应降低。最终可取条数还受证券上市时间和主站对该周期的历史留存
范围限制，`offset` 是期望条数，不保证一定足量。

复权模式如下：

- `none` / `bfq`：不复权
- `qfq` / `front` / `before`：前复权
- `hfq` / `back` / `after`：后复权
- `fixed_qfq` / `fixed_front`：定点前复权，必须传 `anchor_date`
- `fixed_hfq` / `fixed_back`：定点后复权，必须传 `anchor_date`

通达信主站会忽略秒线请求中的复权位，因此 `13/N` 秒线只允许
`adjust='none'`；分钟、日、周、月、季、年和自定义 N 分钟/N 日支持上述复权模式。

`anchor_date` 支持 `YYYY-MM-DD`、`YYYYMMDD`、`date` 和 `datetime`。定点
复权会以该日期定位数据；分钟线的日期必须落在主站保留范围内，否则
返回空结果。为保持向后兼容，原有 `bars(adjust='qfq'/'hfq')` 仍保留旧复权
流程；不希望依赖外部复权因子时，应显式调用 `adjusted_bars()`。

该接口仅属于 `market='std'` 的标准行情，证券代码必须是裸 6 位 ASCII 字符。
期货、港股等 `ExtQuotes` 行情不是这个接口；指数 K 线包含额外的上涨/下跌家数
字段，也不应使用当前股票 K 线解析入口。

## 03. 查询股票数量

** 参数说明: **

- market: 市场代码. 0 - 深圳, 1 - 上海, 2 - 北京 (可以使用常量 `MARKET_SZ`, `MARKET_SH`, `MARKET_BJ` 代替)

** 调用方法：**

```python
from mootdx.quotes import Quotes
from mootdx import consts

client = Quotes.factory(market='std')
client.stock_count(market=consts.MARKET_SH)
```

## 04. 查询股票列表

** 参数说明: **

- market: 市场代码. 0 - 深圳, 1 - 上海, 2 - 北京 (可以使用常量 `MARKET_SZ`, `MARKET_SH`, `MARKET_BJ` 代替)

> 注意，在引入 consts 之后， （`from mootdx import consts`）
> 我们可以使用 consts.MARKET_SH、consts.MARKET_SZ、consts.MARKET_BJ 常量作为参数

** 调用方法：**

```python
from mootdx.quotes import Quotes
from mootdx import consts

client = Quotes.factory(market='std')
sh_stocks = client.stocks(market=consts.MARKET_SH)
sz_stocks = client.stocks(market=consts.MARKET_SZ)
bj_stocks = client.stocks(market=consts.MARKET_BJ)
```

## 05. 指数K线行情

** 参数说明: **

- frequency: K线种类
- market: 市场代码. 0 - 深圳, 1 - 上海 (可以使用常量 `MARKET_SZ`, `MARKET_SH` 代替)
- start: 开始位置
- offset: 用户要请求的 K 线数目，最大值为 800

> frequency -> K线种类
> 0 => 5分钟K线             => 5m
> 1 => 15分钟K线            => 15m
> 2 => 30分钟K线            => 30m
> 3 => 小时K线              => 1h
> 4 => 日K线 (小数点x100)    => days
> 5 => 周K线                => week
> 6 => 月K线                => mon
> 7 => 1分钟K线(好像一样)     => 1m
> 8 => 1分钟K线(好像一样)     => 1m
> 9 => 日K线                => day
> 10 => 季K线               => 3mon
> 11 => 年K线               => year

使用说明：

** 调用方法：**

```python
from mootdx.quotes import Quotes
from mootdx.consts import MARKET_SH

client = Quotes.factory(market='std')
client.index(frequency=9, market=MARKET_SH, symbol='000001', start=1, offset=2)
```

## 06. 查询分时行情

> 网友反馈，此接口数据有误，不建议使用，可以使用 后面的 `历史分时行情` 来替代

** 参数说明: **

- symbol: 股票代码

** 调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')
client.minute(symbol='000001')
```

## 07. 历史分时行情

** 参数说明: **

- market: 市场代码.
- symbol: 股票代码
- date: 时间

** 调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')
client.minutes(symbol='000001', date='20171010')
```

注意，在引入 consts 之后（`from mootdx import consts`），我们可以使用 `consts.MARKET_SZ`、`consts.MARKET_SH`、`consts.MARKET_BJ` 常量来代替 0、1、2 作为参数。

## 08. 查询分笔成交

** 参数说明: **

- market: 市场代码.
- start: 起始位置
- offset: 数量

** 调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')
client.transaction(symbol='600036', start=0, offset=10)
```

## 09. 查询历史分笔

** 参数说明: **

- symbol: 股票代码.
- start: 起始位置.
- offset: 数量.
- date: 日期.

** 调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')
client.transactions(symbol='000001', start=0, offset=10, date='20170209')
```

## 10. 公司信息目录

** 参数说明: **
市场代码， 股票代码， 如： 0,000001 或 1,600300

** 参数说明: **

- symbol: 股票代码.

** 调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')
client.F10C(symbol='000001')
```

## 11. 公司信息详情

** 参数说明: **

- symbol: 股票代码.
- name: 公司详情标题. 可使用`F10C`获取

**调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')
client.F10(symbol='000001', name='最新提示')
```

注意这里的 公司详情标题 参考上面接口的返回结果。

## 12. 除权除息信息

**参数说明: **

- symbol: 股票代码.

** 调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')
client.xdxr(symbol='600036')
```

## 13. 读取财务信息

**参数说明: **

- symbol: 股票代码.

**调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')
client.finance(symbol="600300")
```

## 14. 批量读取财务信息

`finances` 接口支持深圳、上海、北京三个市场，可一次传入任意长度的股票代码列表。
接口内部会自动按最多 80 只分页，并校验每批返回数量及代码是否完整。

**参数说明: **

- symbol: 股票代码列表。
- batch_size: 每批请求数量，取值范围 1 ~ 80，默认为 80。

**调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')
client.finances(symbol=["000001", "600300", "920971"])
```

返回值为 `pd.DataFrame`，字段与单只查询 `finance(symbol=...)` 一致。服务器若少返、多返或返回不同代码，
接口会明确抛出 `MootdxValidationException`，不会伪造或静默丢弃记录。

## 15. 读取通达信行业分类码

`industry_codes` 直接从行情服务器下载并解析 `tdxhy.cfg`，覆盖深圳、上海、北京三个市场，
不会在本地写入临时文件。

**调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')
industry_codes = client.industry_codes()
```

返回值为 `pd.DataFrame`，包含以下字段：

- `market`: 市场代码，0 - 深圳、1 - 上海、2 - 北京。
- `code`: 六位证券代码。
- `tdx_industry`: 通达信行业分类码，如 `T1001`。
- `tdx_detail`: 通达信细分分类码，如 `X500102`。

分类暂未维护的证券可能返回空分类码。接口会忽略空行和完全相同的重复记录；空文件、
畸形记录或同一市场同一证券的分类冲突会抛出 `MootdxValidationException`。

## 16. 读取 OHLC k线信息

**参数说明: **

- symbol: 股票代码.
- begin: 开始时间.
- end: 结束时间.
- adjust: 复权.

**调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='std')
client.k(symbol="600300", begin="2017-07-03", end="2017-07-10")

# 前复权
client.k(symbol="600300", begin="2017-07-03", end="2017-07-10", adjust='qfq')

# 后复权
client.k(symbol="600300", begin="2017-07-03", end="2017-07-10", adjust='hfq')

# ohlc 是k的别名, 功能相同
client.ohlc(symbol="600300", begin="2017-07-03", end="2017-07-10")

# 前复权
client.ohlc(symbol="600300", begin="2017-07-03", end="2017-07-10", adjust='qfq')

# 后复权
client.ohlc(symbol="600300", begin="2017-07-03", end="2017-07-10", adjust='hfq')
```
