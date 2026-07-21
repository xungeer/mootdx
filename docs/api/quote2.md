# 扩展行情 API

扩展行情用于查询通达信扩展主站提供的期货、期权、港股及其他非标准市场数据。市场 ID 和可用品种由服务器决定，必须以 `markets()` 的实时返回为准。

开始前请先阅读 [公共约定](conventions.md)，了解连接、普通 K 线周期、DataFrame 空结果和组合代码格式。

## 创建客户端

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='ext')
```

也可以指定扩展行情主站或重新探测线路：

```python
client = Quotes.factory(
    market='ext',
    server=('218.75.75.18', 7720),
    bestip=False,
)
```

`server` 必须是 `(IP, 端口)` 二元 tuple/list。扩展客户端在创建时立即连接，使用结束后应调用 `client.close()`。

## 市场 ID 与组合代码

先查询当前服务器支持的市场：

```python
markets = client.markets()
```

返回 DataFrame 的典型列包括 `market`、`name`、`short_name`，实际内容以服务器为准。市场可能随主站、时间和通达信配置变化，应用代码不应内置本文档中的历史市场清单。

查询某个品种有两种等价写法：

```python
# 显式传市场 ID 和代码
client.quote(market=47, symbol='IFL0')

# 把市场 ID 与代码组合到 symbol
client.quote(symbol='47#IFL0')
```

组合格式只能通过 `symbol=` 传入。下面这种位置参数写法是错误的，因为字符串会绑定到 `market`：

```python
# 错误：client.quote('47#IFL0')
```

若 `symbol` 不含 `#`，必须显式提供可转换为整数的非空 `market`。

## 接口总览

| 方法 | 用途 | 主要返回类型 |
| --- | --- | --- |
| `markets()` | 当前服务器支持的市场 | DataFrame |
| `instrument()` | 从指定位置读取品种列表 | DataFrame |
| `instrument_count()` | 当前服务器的品种总数 | `int` |
| `instruments()` | 分页读取全部品种 | DataFrame |
| `quote()` | 单个品种五档行情 | DataFrame |
| `minute()` / `minutes()` | 当日/历史分时 | DataFrame |
| `bars()` | 扩展市场 K 线 | DataFrame |
| `transaction()` / `transactions()` | 当日/历史分笔成交 | DataFrame |

这些行情接口依赖扩展主站。空响应通常转换为空 DataFrame；请求数量只是期望值，服务器可能少返。

## 查询市场

方法签名（省略 `self`）：`markets(**kwargs)`。

```python
markets = client.markets()
```

返回当前连接主站的市场列表 DataFrame。程序应从这里取得后续请求使用的市场 ID。

## 查询品种列表

### 单页 `instrument()`

方法签名（省略 `self`）：`instrument(start=0, offset=800, **kwargs)`。

```python
page = client.instrument(start=0, offset=100)
```

- `start`：列表起始位置。
- `offset`：本次期望数量。

该方法只发送一次请求，不自动分页；返回行数可能小于 `offset`。

### 总数 `instrument_count()`

```python
count = client.instrument_count()
```

返回服务器报告的品种总数 `int`。

### 全部品种 `instruments()`

```python
all_instruments = client.instruments()
```

方法先读取总数，再按每批 100 条请求并合并为 DataFrame。调用期间会显示进度。服务器中途少返时，当前实现不会像标准市场 `stocks()` 那样做完整性校验，因此调用方需要根据 `instrument_count()` 自行核对最终行数。

## 五档行情

方法签名（省略 `self`）：`quote(market='', symbol='', **kwargs)`。

```python
quote = client.quote(market=47, symbol='IFL0')
quote = client.quote(symbol='47#IFL0')
```

返回单个品种行情 DataFrame。市场缺失或组合代码格式错误时抛出 `ValueError`；主站无数据时返回空 DataFrame。

## 分时行情

### 当日分时 `minute()`

方法签名（省略 `self`）：`minute(market='', symbol='', **kwargs)`。

```python
today = client.minute(market=47, symbol='IFL0')
today = client.minute(symbol='47#IFL0')
```

该方法调用扩展主站的当前分时接口，返回 DataFrame。

### 历史分时 `minutes()`

方法签名（省略 `self`）：`minutes(market=None, symbol='', date='', **kwargs)`。

当前底层扩展协议要求 `date` 是普通整数 `YYYYMMDD`；默认空字符串不能形成有效请求，因此实际调用必须显式传日期：

```python
history = client.minutes(market=47, symbol='IFL0', date=20170810)
history = client.minutes(symbol='47#IFL0', date=20170810)
```

不要在该接口中传字符串日期。主站没有对应日期数据时返回空 DataFrame。

## K 线

方法签名（省略 `self`）：
`bars(frequency='', market='', symbol='', start=0, offset=800, **kwargs)`。

参数说明：

- `frequency`：0～11 的固定周期整数或 [公共约定](conventions.md#ordinary-periods) 中的字符串。
- `market`、`symbol`：显式市场与品种代码；也可以只传组合 `symbol='市场ID#代码'`。
- `start`：从最新数据向历史方向计算的起始位置。
- `offset`：期望条数。

扩展主站单次通常最多返回 700 条。`offset > 700` 时，Mootdx 按 700 条自动分页，并把较早批次放在前面，使最终结果按时间从旧到新排列。

```python
from mootdx.consts import KLINE_RI_K

daily = client.bars(
    frequency=KLINE_RI_K,
    market=47,
    symbol='IFL0',
    start=0,
    offset=100,
)

daily_by_combined_code = client.bars(
    frequency='day',
    symbol='47#IFL0',
    offset=100,
)
```

服务器可能在任意一页少返或返回空值；此时分页停止，最终行数会小于 `offset`。扩展市场没有 `adjusted_bars()`，也不支持普通接口之外的 `10m`、`2d`、`5s` 自定义周期。

## 分笔成交

### 当日分笔 `transaction()`

方法签名（省略 `self`）：
`transaction(market=None, symbol='', start=0, offset=800, **kwargs)`。

```python
trades = client.transaction(market=47, symbol='IFL0', start=0, offset=800)
trades = client.transaction(symbol='47#IFL0', start=0, offset=800)
```

该方法只发送一次请求，不自动分页。需要更早记录时应调整 `start`；单次实际可用数量和历史深度由主站决定。

### 历史分笔 `transactions()`

方法签名（省略 `self`）：
`transactions(market=None, symbol='', date='', start=0, offset=800, **kwargs)`。

`date` 是 `YYYYMMDD` 字符串或整数，高层接口会把它转换为整数：

```python
history = client.transactions(
    market=47,
    symbol='IFL0',
    date='20170810',
    start=0,
    offset=800,
)

history_by_combined_code = client.transactions(
    symbol='47#IFL0',
    date=20170810,
    start=0,
    offset=800,
)
```

历史分笔同样不自动分页，且可能少于 `offset`。不要误用 `transaction(..., date=...)`：`transaction()` 会把未知的 `date` 留在 `**kwargs` 中，实际仍请求当日分笔。

## 返回字段说明

扩展市场覆盖多类金融品种，不同接口和市场的协议字段并不完全相同：

- `markets()` 和品种列表返回市场、代码、名称及服务器提供的元数据。
- `quote()` 返回价格、盘口、成交量等实时字段。
- `bars()` 通常包含开、高、低、收、持仓、成交、时间和成交额字段。
- 分时与分笔通常包含价格、成交量、持仓变化、方向和时间字段。

字段含义及价格缩放可能因市场而异。应先查看目标市场的实际 DataFrame 列和样本值，不要假设所有扩展品种与 A 股字段一致。

## 关闭连接

```python
is_closed = client.closed
client.close()
```

关闭后不要继续复用该对象。需要新连接时重新调用 `Quotes.factory(market='ext')`。
