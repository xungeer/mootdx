# 标准行情 API

标准行情客户端用于查询深市、沪市和北交所证券。它在创建时连接通达信行情主站，使用结束后应调用 `close()`。

开始前请先阅读 [公共约定](conventions.md)，了解市场常量、普通周期、DataFrame 空结果和连接生命周期。

## 创建客户端

```python
from mootdx.quotes import Quotes

client = Quotes.factory(
    market='std',
    server=None,
    bestip=False,
    timeout=15,
    handshake="minimal",
    heartbeat=False,
    heartbeat_interval=10,
    auto_retry=True,
    max_retries=4,
    raise_exception=False,
)
```

参数说明：

- `server`：可选的 `(IP, 端口)` 二元 tuple/list。省略时使用配置中的标准行情主站。
- `bestip`：为 `True` 时重新探测线路并更新配置。
- `timeout`：连接超时秒数；传入假值时仍使用 15 秒。
- `handshake`：默认 `minimal` 两步；`legacy` 三步和 `single` 单步须显式选择。服务端复权另用单步连接。
- `heartbeat`：是否启用协议心跳。
- `heartbeat_interval`：成功响应后空闲多久触发心跳，单位为秒。
- `max_retries`：网络失败后的最大额外重试次数；默认 4。
- `auto_retry`：网络失败后是否有限重试；明确拒绝、协议损坏和参数错误不自动重试。
- `raise_exception`：底层请求失败时是否抛出协议异常。

## 接口总览

| 方法 | 用途 | 主要返回类型 |
| --- | --- | --- |
| `quotes()` | 单只或多只实时行情 | DataFrame |
| `bars()` | 普通 K 线，可在客户端复权 | DataFrame |
| `adjusted_bars()` | 通达信服务端复权及自定义周期 K 线 | DataFrame |
| `stock_count()` | 单个市场的证券数量 | `int` |
| `stocks()` / `stock_all()` | 单市场/全部标准市场证券列表 | DataFrame 或 `None` |
| `index()` / `index_bars()` | 指数 K 线 | DataFrame |
| `minute()` / `minutes()` | 当日/历史分时 | DataFrame |
| `transaction()` / `transactions()` | 当日/历史分笔成交 | DataFrame |
| `F10C()` / `F10()` | 公司资料目录与正文 | list、str、dict 或 `None` |
| `xdxr()` | 除权除息信息 | DataFrame |
| `finance()` / `finances()` | 单只/批量财务摘要 | DataFrame |
| `industry_codes()` | 通达信行业分类码 | DataFrame |
| `k()` / `ohlc()` | 按日期区间读取日 K 线 | DataFrame |
| `block()` | 下载并解析板块文件 | DataFrame |
| `traffic()` | 当前连接的流量统计 | `dict` |

## 实时行情

方法签名（省略 `self`）：`quotes(symbol=None, **kwargs)`。

`symbol` 可以是六位证券代码字符串，也可以是代码列表：

```python
single = client.quotes(symbol='600036')
multiple = client.quotes(symbol=['000001', '600036', '920971'])
```

市场由代码自动推断。未传 `symbol`、列表为空或主站合法返回无数据时返回空 DataFrame；协议校验、解析或传输失败抛出 `MootdxDataException` 或底层协议异常，不再与合法空行情混淆。

## 普通 K 线与客户端复权 {#client-adjusted-bars}

方法签名（省略 `self`）：
`bars(symbol='000001', frequency=9, start=0, offset=800, **kwargs)`。

参数说明：

- `symbol`：证券代码，市场自动推断。
- `frequency`：0～11 的普通周期整数或 [公共约定](conventions.md#ordinary-periods) 中的字符串。
- `start`：从最新数据向历史方向计算的起始位置。
- `offset`：期望条数。主站单次通常最多返回 800 条，超过 800 时自动分页。
- `adjust`：可通过关键字传 `qfq`、`01`、`before` 或 `hfq`、`02`、`after`。

分页结果按时间从旧到新合并。主站合法返回空页或短页时视为历史耗尽，最终行数可以小于 `offset`；底层传输、解压或解析失败返回 `None` 时抛出 `MootdxDataException`，不会返回已经累计的部分分页。

### `bars()` 的复权方式

`bars(adjust=...)` 先请求普通 K 线，再进入旧版客户端复权流程：

```python
qfq = client.bars(symbol='600036', frequency='day', offset=800, adjust='qfq')
hfq = client.bars(symbol='600036', frequency='day', offset=800, adjust='hfq')
```

这条兼容流程会查询通达信 `xdxr()` 并缓存到 `~/.mootdx/xdxr/`，随后还会从新浪
获取前/后复权因子并缓存到 `~/.mootdx/caches/factor/`。因此它同时依赖通达信行情
主站和新浪接口；复权合并、缺失值清理和去重可能使结果行数发生变化。

普通 `bars()` 只支持固定周期。`10m`、`2d`、`5s` 等自定义周期应使用 `adjusted_bars()`。

## 服务端复权与自定义周期 {#server-adjusted-bars}

方法签名（省略 `self`）：`adjusted_bars(symbol='000001', frequency=9, start=0,
offset=800, adjust='qfq', anchor_date=None, **kwargs)`。

该方法直接使用通达信 `0x052d` 请求中的复权参数，不下载客户端复权因子，也不调用 `bars()` 的旧版复权流程。它会使用当前主站建立一个临时单步握手连接，沿用调用方的 `auto_retry`、`raise_exception` 和 `max_retries`，保持心跳关闭，并在返回或抛错前关闭该连接。

### 参数限制

- `symbol`：必须是长度为 6 的 ASCII 字符串。接口本身只校验长度和 ASCII；标准证券通常使用六位数字代码。
- `start`：必须是 0～65535 的整数，布尔值不被视为整数。
- `offset`：必须是正整数，布尔值不被视为整数。
- 单批最多 800 条；更大的 `offset` 自动按 800 条分页。
- 当前 `start` 可请求的最大 `offset` 为 `((65535 - start) // 800 + 1) * 800`。因此 `start=0` 时最多请求 65600 条。
- `offset` 是期望值。实际历史深度还取决于证券、周期和主站留存范围。

### 周期

`frequency` 支持三类输入：

1. 整数类别：0～11 或 13。
2. 二元 tuple：`(category, period_param)`。
3. 固定别名或自定义字符串。

固定别名如下：

| 类别 | 支持的字符串 |
| ---: | --- |
| 0 | `5m`、`5min` |
| 1 | `15m`、`15min` |
| 2 | `30m`、`30min` |
| 3 | `1h`、`60m`、`60min`、`hour` |
| 4 | `days` |
| 5 | `week`、`1w` |
| 6 | `mon`、`month`、`1mo` |
| 7 | `ex_1m` |
| 8 | `1m`、`1min`、`minute` |
| 9 | `day`、`dk`、`1d`、`daily` |
| 10 | `3mon`、`quarter`、`1q` |
| 11 | `year`、`1y` |

自定义字符串格式：

- `Nm` 或 `Nmin`：N 分钟，对应类别 8。
- `Nd`：N 日，对应类别 9。
- `Ns`：N 秒，对应类别 13。

N 必须是 1～32767。固定的 1、5、15、30、60 分钟会归一到各自标准类别；其他分钟周期使用类别 8 和 N。二元 tuple 中，只有类别 8、9、13 允许 `period_param != 1`；其他类别的周期参数必须为 1。

协议参数合法不代表主站一定保存该周期。自定义分钟或秒数过大时，服务器也可能按每日少量记录返回；秒线按实际成交生成，不保证每个时间桶都有记录。

### 复权模式

| `adjust` | 协议值 | 含义 |
| --- | ---: | --- |
| `None`、空字符串、`none`、`bfq` | 0 | 不复权 |
| `qfq`、`front`、`before` | 1 | 前复权 |
| `hfq`、`back`、`after` | 2 | 后复权 |
| `fixed_qfq`、`fixed_front` | 3 | 定点前复权 |
| `fixed_hfq`、`fixed_back` | 4 | 定点后复权 |

也可以直接传整数 0～4。布尔值和其他值会抛出 `ValueError`。

定点复权必须提供 `anchor_date`，支持：

- `YYYY-MM-DD` 字符串；
- `YYYYMMDD` 字符串或整数；
- `datetime.date`；
- `datetime.datetime`。

```python
fixed = client.adjusted_bars(
    symbol='600036',
    frequency='15m',
    offset=100,
    adjust='fixed_qfq',
    anchor_date='2024-06-03',
)
```

`anchor_date` 只是服务端定点复权的价格锚点，不是历史知识截止日或 `as_of` 日期。
服务端会按查询时已经掌握的企业行动重算历史，即使锚点早于某次分红或份额折算，结果
仍可能包含该锚点之后的事件。调用 `fixed_*` 会产生警告，返回元数据明确标记
`point_in_time=False`、`anchor_date_semantics='price_anchor'`。正式回测不得把
`fixed_*` 当作点时数据；应读取 `adjust='none'` 原始价格，并使用带
`effective_date`、`observed_at` 和版本号的企业行动数据自行复权。

秒线不支持服务端复权，类别 13 必须使用 `adjust='none'`：

```python
seconds = client.adjusted_bars(
    symbol='600036',
    frequency='5s',
    offset=1600,
    adjust='none',
)
```

返回结构与普通股票 K 线兼容；秒线额外包含 `second` 列，`datetime` 精确到秒。
服务端复权只调整价格，`vol`、`volume` 和 `amount` 仍是未复权的协议原始口径。
连接或请求失败会抛出 `MootdxDataException` 或底层协议异常，合法无数据才返回空
DataFrame。创建客户端时传入 `raise_exception=True` 可以保留底层协议异常细节。

## 证券数量与列表

### `stock_count()`

```python
client.stock_count(market=MARKET_SH)
```

`market` 只能是 `MARKET_SZ`、`MARKET_SH`、`MARKET_BJ` 或对应整数 0、1、2。返回主站报告的证券数量 `int`；非法市场抛出 `MootdxValidationException`。

### `stocks()`

```python
from mootdx.consts import MARKET_BJ, MARKET_SH, MARKET_SZ

sz = client.stocks(market=MARKET_SZ)
sh = client.stocks(market=MARKET_SH)
bj = client.stocks(market=MARKET_BJ)
```

接口先读取市场数量，再按每批 1000 条下载完整列表。任何一页少返、最终数量不一致或市场非法都会抛出 `MootdxValidationException`，不会静默返回不完整结果。市场数量为零时返回 `None`，否则返回 DataFrame。结果新增 `market`、`exchange` 和 `instrument_id`；其中 `instrument_id` 使用 `SH.600036`、`SZ.000001`、`BJ.920971` 形式，可作为跨市场证券主键。

### `stock_all()`

```python
all_stocks = client.stock_all()
```

依次查询深市、沪市、北交所并合并为一个 DataFrame。调用期间会显示分页进度。

## 指数 K 线

方法签名（省略 `self`）：`index(symbol, frequency=9, start=0, offset=800, **kwargs)`；
`index_bars()` 接受相同参数。

两个方法行为相同：使用普通固定周期，单批最多 800 条，更大 `offset` 自动分页并按时间合并。

它们没有 `market` 参数，市场仅由指数代码推断：前两位为 `00`、`88`、`99`、`89` 时使用沪市，其余使用深市。传入额外的 `market=` 不会改变请求市场，因此不要传该参数。

## 分时行情

### 当日分时

```python
today = client.minute(symbol='000001')
```

`minute()` 按 `Asia/Shanghai` 的当天日期生成 `YYYYMMDD`，再调用历史分时接口；它不是底层实时分时命令的直接封装。

### 历史分时

```python
history = client.minutes(symbol='000001', date='20171010')
```

方法签名（省略 `self`）：`minutes(symbol, date='20191023', **kwargs)`。

`date` 使用 `YYYYMMDD` 字符串或整数。市场从 `symbol` 推断；不属于 0、1、2 时抛出 `MootdxValidationException`。无数据返回空 DataFrame，请求失败抛出 `MootdxDataException`。该协议只返回按顺序排列的价格和成交量，没有每条记录的真实时间戳，因此元数据标记 `fact_table_eligible=False`；分钟事实表应使用 `bars(frequency='1m')`。

## 分笔成交

### 当日分笔

方法签名（省略 `self`）：`transaction(symbol, start=0, offset=800, **kwargs)`。

底层协议只在交易时段提供当前分笔；非交易时段或无数据时通常返回空 DataFrame。该方法不自动分页，使用 `start` 和 `offset` 手动读取其他位置。

### 历史分笔

方法签名（省略 `self`）：
`transactions(symbol, start=0, offset=800, date='20170209', **kwargs)`。

`date` 会转换为整数 `YYYYMMDD`。该方法同样不自动分页，结果可能少于 `offset`。

实时和历史逐笔价格会按证券类型使用价格系数。沪市 `52`、`53`、`55` 等新 ETF
代码与既有 ETF 一样使用三位小数，避免旧版固定除以 100 造成的 10 倍价格错误。

## 公司资料

### 目录 `F10C()`

```python
catalog = client.F10C(symbol='000001')
```

市场从代码推断。返回目录列表，每项包含 `name`、`filename`、`start`、`length`；该方法不经过 DataFrame 转换。
底层协议当前不支持北交所 F10 目录，北交所代码会返回 `None` 并产生弃用警告。

### 正文 `F10()`

```python
overview = client.F10(symbol='000001', name='公司概况')
all_sections = client.F10(symbol='000001')
```

- 指定 `name`：找到同名目录时返回 GBK 解码后的正文字符串；没有同名项时继续返回全部栏目字典。
- 未指定 `name`：返回 `{栏目名称: 正文字符串}` 字典。
- 主站没有目录：返回 `None`。

非法市场会抛出 `MootdxValidationException`。
北交所目录当前不可用，因此 `F10()` 对北交所代码同样返回 `None`。

## 除权除息与财务摘要

### `xdxr()`

```python
data = client.xdxr(symbol='600036')
```

返回除权除息信息 DataFrame；无数据为空 DataFrame。

### `finance()`

```python
data = client.finance(symbol='600300')
```

返回单只证券的一行财务摘要 DataFrame，包含 `market`、`code`、股本、资产、负债、利润等协议字段。

### `finances()`

```python
data = client.finances(
    symbol=['000001', '600300', '920971'],
    batch_size=80,
)
```

方法签名（省略 `self`）：`finances(symbol=None, batch_size=80, **kwargs)`。

- `symbol` 必须是代码 `list`；空值返回空 DataFrame，字符串等其他类型抛出 `MootdxValidationException`。
- `batch_size` 必须是 1～80 的整数，布尔值不被接受。
- 任意长度列表会自动分批，支持深市、沪市和北交所。
- 每批返回数量、`market` 和 `code` 都会与请求严格核对；少返、多返、缺字段或代码不匹配均抛出 `MootdxValidationException`。
- 返回列和 `finance()` 一致；接口会校验每批返回的是同一组代码，但不会额外重排服务器返回的记录。

## 通达信行业分类码

```python
industry = client.industry_codes()
```

该方法从当前行情服务器读取内存中的 `tdxhy.cfg`，不写临时文件。返回四列 DataFrame：

| 列 | 含义 |
| --- | --- |
| `market` | 0 深圳、1 上海、2 北京 |
| `code` | 六位证券代码 |
| `tdx_industry` | 通达信行业分类码，例如 `T1001` |
| `tdx_detail` | 通达信细分分类码，例如 `X500102` |

未分类证券可有空分类码。空文件、非 GBK 内容、字段数量错误、非法代码、保留字段非空或同一证券出现冲突记录时，会抛出 `MootdxValidationException`；完全相同的重复记录会去重。

## 按日期区间读取日 K 线

方法签名（省略 `self`）：`k(symbol='', begin=None, end=None, **kwargs)`；`ohlc()`
把参数转发给 `k()`；`get_k_data(code, start_date, end_date)` 是其底层兼容入口。

`ohlc()` 转发到 `k()`；`k()` 使用 `get_k_data()` 读取固定的日线类别 9，再经过统一 DataFrame 转换。

```python
data = client.k(
    symbol='600300',
    begin='2017-07-03',
    end='2017-07-10',
)
```

日期区间为 `begin <= date < end`，结束日期不包含在结果内。实现会按日期距今天数估算协议位置，再每批读取 800 条，因此它不是精确的交易日游标接口；`begin`、`end` 应显式提供。

传 `adjust='qfq'/'hfq'` 时，`k()` 与 `bars()` 一样在客户端执行复权并可能产生缓存：

```python
qfq = client.ohlc(
    symbol='600300',
    begin='2017-07-03',
    end='2017-07-10',
    adjust='qfq',
)
```

## 板块信息

```python
data = client.block(tofile='block.dat')
```

`tofile` 是保留的历史参数名，实际表示要从服务器读取的板块文件名。接口把文件下载到
内存并解析为 DataFrame，不会在本地创建同名文件。获取板块元信息失败或主站无数据时
返回空 DataFrame；后续分块下载或 `BlockReader` 解析失败时，异常可能直接向调用方抛出。

## 流量与关闭连接

```python
stats = client.traffic()
is_closed = client.closed
client.close()
```

`traffic()` 返回字典，包含请求包数量、收发字节数、最近请求字节数、连接持续时间和估算速率。关闭后不要继续复用该对象；需要新连接时重新调用 `Quotes.factory()`。
