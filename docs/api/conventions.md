# 公共约定

## 工厂方法

在线行情使用 `Quotes.factory()`：

```python
from mootdx.quotes import Quotes

standard = Quotes.factory(market='std')
extended = Quotes.factory(market='ext')
```

本地文件使用 `Reader.factory()`：

```python
from mootdx.reader import Reader

reader = Reader.factory(market='std', tdxdir='C:/new_tdx')
```

两个工厂都只把精确的字符串 `ext` 识别为扩展市场，其他值会回落到标准市场。为避免拼写错误被静默接受，请只传 `std` 或 `ext`。

## 连接与服务器

`Quotes.factory()` 会在构造对象时立即连接服务器。标准行情常用的有效连接参数如下：

```python
client = Quotes.factory(
    market='std',
    server=('110.41.147.114', 7709),  # 可省略，必须是 (IP, 端口)
    bestip=False,                     # True 时重新探测可用线路
    timeout=15,
    heartbeat=False,
    auto_retry=True,
    raise_exception=False,
)
```

扩展行情可使用 `server=(IP, 端口)` 和 `bestip=True/False`，通常应使用默认配置。不要依赖未在本文档列出的透传参数。

行情对象持有网络连接。使用结束后应显式关闭：

```python
client.close()
```

可通过 `client.closed` 查看标准或扩展行情连接是否已经关闭。不要把对象析构当作及时释放连接的保证。

行情、服务器列表和历史深度均由所连接主站决定。`offset` 表示期望数量，不保证服务器一定足量返回；网络失败或主站无数据也可能产生空结果。

## 市场常量与代码

标准市场使用以下常量：

```python
from mootdx.consts import MARKET_BJ, MARKET_SH, MARKET_SZ

MARKET_SZ  # 0，深圳
MARKET_SH  # 1，上海
MARKET_BJ  # 2，北京证券交易所
```

标准行情的大多数证券接口只接收证券代码，并由 Mootdx 推断市场。`stock_count()`、`stocks()` 等市场级接口才显式接收上述市场常量。

扩展行情使用服务器返回的数字市场 ID。应先调用 `markets()`，再以 `market=市场ID, symbol=代码` 查询；也可以把两者组合成 `symbol='市场ID#代码'`。

## 普通 K 线周期 {#ordinary-periods}

`bars()`、`index()` 等普通 K 线接口接受整数周期或下表中的字符串。常量定义在 `mootdx.consts`。

| 值 | 字符串 | 常量 | 含义 |
| ---: | --- | --- | --- |
| 0 | `5m` | `KLINE_5MIN` | 5 分钟 |
| 1 | `15m` | `KLINE_15MIN` | 15 分钟 |
| 2 | `30m` | `KLINE_30MIN` | 30 分钟 |
| 3 | `1h` | `KLINE_1HOUR` | 1 小时 |
| 4 | `days` | `KLINE_DAILY` | 兼容日线口径，成交量约为 `day` 的 100 倍 |
| 5 | `week` | `KLINE_WEEKLY` | 周线 |
| 6 | `mon` | `KLINE_MONTHLY` | 月线 |
| 7 | `ex_1m` | `KLINE_EX_1MIN` | 兼容 1 分钟口径 |
| 8 | `1m` | `KLINE_1MIN` | 1 分钟 |
| 9 | `day` | `KLINE_RI_K` | 日线 |
| 10 | `3mon` | `KLINE_3MONTH` | 季线 |
| 11 | `year` | `KLINE_YEARLY` | 年线 |

普通 K 线接口不支持 `10m`、`2d`、`5s` 等自定义周期。标准市场的自定义周期和服务端复权请使用 `adjusted_bars()`。

当前普通周期转换器会把不在表中的字符串静默回落为类别 `0`（5 分钟），而不会抛出
参数错误；扩展行情 `bars()` 的默认空字符串也因此等价于 5 分钟。不要依赖这种兼容
回落，调用时应显式使用表内字符串或常量。

## DataFrame 返回规则

大多数公开行情方法通过同一转换层返回 `pandas.DataFrame`：

- 协议返回空值时，通常得到空 DataFrame，而不是 `None`。
- 结果包含 `datetime` 或 `date` 列时，该列会转换为 `DatetimeIndex`；原列仍然保留。
- 结果包含 `vol` 列时，会额外创建同值的 `volume` 列；`vol` 仍然保留。
- 多页 K 线会按时间从旧到新合并。

少数方法有不同返回类型，例如 `stock_count()` 返回整数，`F10C()` 返回目录列表，`F10()` 返回文本或字典，`stocks()` 在市场数量为零时返回 `None`。每个接口页面会单独注明这些例外。

调用方应同时处理空 DataFrame、少返和接口明确列出的 `None` 情况，不要仅以请求的 `offset` 推断结果长度。

## 网络、缓存与文件副作用

- 所有 `Quotes` 接口都需要网络。
- 每次创建 `Quotes` 客户端都会读取 `~/.mootdx/config.json`；文件缺失或 JSON 损坏时，初始化会自动执行全线路测速并重写配置，即使没有显式传 `bestip=True`。
- `Reader.daily(..., adjust='qfq'/'hfq')` 虽然读取本地 K 线，但客户端复权还会查询通达信除权除息数据和新浪复权因子，并分别缓存到 `~/.mootdx/xdxr/` 与 `~/.mootdx/caches/factor/`。
- `Affair.fetch()` 会创建下载目录并写入文件；`Affair.parse()` 在目标文件不存在时会尝试下载。
- `StdQuotes.block()` 的参数虽然名为 `tofile`，实际表示服务器上的板块文件名；该方法只下载到内存并解析，不写本地同名文件。

## 公共接口边界

`mootdx._protocol` 是随 Mootdx 内置的协议实现，供公开高层接口使用，但下划线前缀表示它不是稳定公共 API。应用代码应优先使用：

- `mootdx.quotes.Quotes`
- `mootdx.reader.Reader`
- `mootdx.affair.Affair`
- `mootdx.consts`
- `mootdx.adjusted` 中明确导出的周期与复权辅助函数

不要直接依赖 `_protocol` 内的请求帧、解析器或 Socket 客户端；这些实现可能在不保留高层兼容性的情况下调整。
