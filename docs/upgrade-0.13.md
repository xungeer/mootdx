# 升级到 v0.13.0

v0.13.0 将行情 API 与原 TDXPY 协议实现放入同一个 Mootdx 发行包，并合入握手、
传输和连接生命周期修复。此版本发布于 `xungeer/mootdx` 的 GitHub，安装方法见
[安装与开发](setup.md)。既有 v0.12.0 tag 保持不变。

## 依赖与导入

普通应用继续使用 `from mootdx.quotes import Quotes`，无需安装独立的 `tdxpy`。
更新应用的依赖声明和锁文件，移除由应用直接声明的 `tdxpy`；若其他依赖仍要求该包，
先分别完成它们的兼容迁移，不要强行删除其运行依赖。建议在新虚拟环境中安装并验证。

需要低层客户端或自定义解析器的调用方，按实际使用的入口迁移：

| 原入口 | v0.13.0 入口 |
| --- | --- |
| `tdxpy.hq.TdxHq_API` | `mootdx.protocol.TdxHq_API` |
| `tdxpy.exhq.TdxExHq_API` | `mootdx.protocol.TdxExHq_API` |
| `tdxpy.base_socket_client.last_ack_time` | `mootdx.protocol.last_ack_time` |
| `tdxpy.parser.std.get_security_bars.GetSecurityBarsCmd` | `mootdx.protocol.GetSecurityBarsCmd` |
| `tdxpy.parser.std.get_security_quotes.GetSecurityQuotesCmd` | `mootdx.protocol.GetSecurityQuotesCmd` |
| `tdxpy.helper` 中的 `get_datetime/get_price/get_volume` | `mootdx.protocol` 中的同名函数 |

结构化异常及复权专用客户端也从 `mootdx.protocol` 导出，完整边界见
[连接与协议](api/connection.md#low-level-extensions)。没有公开导出的 `_protocol` 模块属于私有实现。
Mootdx 不创建顶层 `tdxpy` 命名空间，也不满足其他包的 `Requires-Dist: tdxpy`；
不要通过旧包版本号判断当前进程加载的协议实现。

若应用以前通过 `PYTHONPATH`、补丁或私有副本覆盖行情 SDK，应先核对其中的修复是否
已由本版提供，再移除对应覆盖。避免覆盖层继续遮蔽新安装的 Mootdx。

## 连接行为

| 场景 | v0.13.0 行为 |
| --- | --- |
| 普通标准行情 | 默认 `minimal` 两步握手；需要旧序列时显式传 `handshake='legacy'` |
| 服务端复权 | 独立连接使用 `single` 单步握手，并继承调用方的网络重试预算 |
| 扩展行情 | 使用扩展协议握手，不接受标准 `handshake` 参数 |
| 指定服务器且 `bestip=False` | 使用当前实例的 endpoint，不扫描或改写 BESTIP |
| 主动关闭后恢复 | 调用 `reconnect()` 并检查结果；普通请求不会自动重新打开连接 |

拒绝响应、协议损坏和参数错误不会作为普通网络波动反复重试。`max_retries` 表示网络
失败后的额外尝试次数，`0` 即不追加尝试；`auto_retry=False` 关闭请求自动重试。

## 失败与返回结构

标准客户端初始化失败现在会抛错。`quotes()`、`bars()`、`adjusted_bars()`、
`minutes()`、`transaction()` 和 `transactions()` 会区分失败与合法无记录：底层
兼容模式返回 `None` 时，高层抛 `MootdxDataException`；严格模式保留底层异常。
合法空记录仍得到空 DataFrame，分页故障不会返回已经累计的部分 K 线。
其他接口仍按各自的 [API 返回约定](api/conventions.md) 处理，不能统一推断为空即成功。

`stocks()` 和 `stock_all()` 的证券列表增加 `market`、`exchange`、`instrument_id`
字段，证券主键形如 `SH.600036`、`SZ.000001`、`BJ.920971`。依赖固定列数或列顺序
的调用方应改为按列名选取。市场数量为零时，`stocks()` 仍返回 `None`。

K 线、分时和逐笔结果中的 `DataFrame.attrs['mootdx']` 提供请求与来源元数据；
`volume` 仍是 `vol` 的同值别名，不代表单位已标准化。服务端复权的定点日期是价格
锚点，结果不具备 point-in-time 语义，详见 [复权接口](api/quote1.md#server-adjusted-bars)。

升级验证应覆盖应用实际使用的证券、周期、返回字段、失败处理和关闭/重连路径。
协议可连接不等于每个主站都提供所需数据。
