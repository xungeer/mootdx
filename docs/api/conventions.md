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

`Quotes.factory()` 会在构造对象时立即连接服务器。标准行情连接失败时抛出
`MootdxDataException` 或底层连接异常，不再构造一个随后只返回空数据的客户端。
标准行情常用的有效连接参数如下：

```python
client = Quotes.factory(
    market='std',
    server=('110.41.147.114', 7709),  # 可省略，必须是 (IP, 端口)
    bestip=False,                     # True 时重新探测可用线路
    timeout=15,
    handshake="minimal",             # 默认两步标准握手
    heartbeat=False,
    heartbeat_interval=10,
    auto_retry=True,
    max_retries=4,
    raise_exception=False,
)
```

标准行情默认采用两步 `minimal` 握手，可显式选择 `legacy` 三步或 `single` 单步；服务端复权始终使用专用单步连接。扩展行情使用独立握手，不接受 `handshake` 参数，支持上述连接、心跳和重试参数。详细行为见 [连接与协议](connection.md)。

行情对象持有网络连接。使用结束后应显式关闭：

```python
client.close()
```

可通过 `client.closed` 查看标准或扩展行情连接是否已经关闭。不要把对象析构当作及时释放连接的保证。

行情、服务器列表和历史深度均由所连接主站决定。`offset` 表示期望数量，不保证服务器一定足量返回。普通兼容接口仍可能把网络失败转换为空结果；`StdQuotes.quotes()`、`bars()`、`adjusted_bars()`、`minutes()`、`transaction()` 和 `transactions()` 已区分协议失败与合法无数据：底层兼容模式返回 `None` 时抛出 `MootdxDataException`，严格模式则保留底层异常；合法无记录返回 `[]` 时得到空 DataFrame。分页中途失败不会返回已经累计的部分 K 线。

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

- 合法无记录通常返回空 DataFrame；协议失败的处理因接口而异，见上面的连接与失败约定。
- 结果包含 `datetime` 或 `date` 列时，该列会转换为 `DatetimeIndex`；原列仍然保留。
- 结果包含 `vol` 列时，会额外创建同值的 `volume` 列；`vol` 仍然保留。
- 多页 K 线会按时间从旧到新合并。

`vol` 和 `volume` 都是通达信协议原始口径，`volume` 只是别名，不是标准化后的股数。
类别 4 `days` 与类别 9 `day` 是两个不同的协议日线类别，实测成交量口径可能相差约
100 倍；Mootdx 不会静默乘除或合并两者。A 股和场内 ETF 接入层应固定使用
`day`/类别 9，保留 `volume_raw`，再结合证券主数据中的 `volunit` 生成经独立来源核验
的标准化成交量。

`bars()`、`adjusted_bars()` 和 `minutes()` 会在 `DataFrame.attrs['mootdx']` 中附加请求
和来源元数据，包括市场、证券、协议类别、请求/返回数量、复权模式、服务器、UTC
采集时间、时区、成交量语义及 `fact_table_eligible`。类别 4、服务端复权价格、旧版
客户端复权、无真实逐条时间戳的分时/逐笔会标记为不可直接进入事实表。这些属性不会
改变列结构，但在 `concat`、CSV 或 Parquet
转换中可能丢失；需要审计追踪的应用必须把它们持久化为批次字段。

行情 `DatetimeIndex` 当前仍是无时区的交易所本地时间，以保持兼容性；元数据中的
`timezone='Asia/Shanghai'` 是本地化提示。入库时应先本地化为上海时区，再按系统约定
转换为 UTC。

少数方法有不同返回类型，例如 `stock_count()` 返回整数，`F10C()` 返回目录列表，`F10()` 返回文本或字典，`stocks()` 在市场数量为零时返回 `None`。每个接口页面会单独注明这些例外。

调用方应同时处理空 DataFrame、合法少返和接口明确列出的 `None` 情况，不要仅以请求的 `offset` 推断结果长度。`MootdxDataException` 表示请求或分页失败，整批结果不可使用。

## 网络、缓存与文件副作用

- 所有 `Quotes` 接口都需要网络。
- 显式传入 `server` 且 `bestip=False` 时，连接不读取、扫描或改写 BESTIP 配置。省略服务器时仍使用原有配置发现流程：配置缺失或 JSON 损坏可能触发测速和写入；`bestip=True` 仍是显式测速入口。
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
- `mootdx.protocol.__all__` 中列出的低层客户端、异常和自定义解析扩展点

需要自定义解析器时，使用 [连接与协议](connection.md#low-level-extensions) 中的 `mootdx.protocol` 入口。不要直接依赖 `_protocol` 的私有路径；未通过公共入口导出的实现不承诺兼容。安装 Mootdx 不会提供顶层 `tdxpy` 命名空间，也不会满足其他包声明的 `tdxpy` 依赖。
