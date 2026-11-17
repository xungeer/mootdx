# 连接与协议

Mootdx 在同一安装包中维护公开 API 和通达信协议实现，无需安装独立的 `tdxpy`。
普通应用继续使用 `mootdx.quotes.Quotes`。本页说明连接行为及需要自定义解析器时的扩展入口。

## 握手策略

| 连接 | 默认策略 | 说明 |
| --- | --- | --- |
| 标准行情 | `minimal`：SetupCmd1 → 2 | 相比旧版本的三步默认有行为变化；避免已观察到的第三步兼容性故障 |
| 服务端复权 | `single`：SetupCmd1 | 使用独立连接，不能替换成普通行情的两步或三步策略 |
| 扩展行情 | 扩展协议初始化 | 不接受标准行情的 `handshake` 参数 |

普通标准行情可显式选择 `handshake='legacy'` 恢复三步序列，或 `handshake='single'`
仅执行第一步。不同模式必须在新连接上建立；不会在被拒绝的连接上自动降级或继续请求。
历史三节点对照支持默认两步的兼容修复，不能据此保证所有主站或全部接口永久可用。

```python
from mootdx.quotes import Quotes

client = Quotes.factory(
    market='std',
    server=('110.41.147.114', 7709),
    timeout=3,
    heartbeat=True,
    heartbeat_interval=10,
    auto_retry=False,
    raise_exception=True,
)
try:
    data = client.bars(symbol='600036', frequency='day', offset=10)
finally:
    client.close()
```

显式服务器且 `bestip=False` 不扫描或改写 BESTIP。省略服务器及显式测速仍遵循原有
配置流程。`timeout` 必须结合任务期限设置；连接成功并不代表所需行情接口一定可用。

## 失败与合法空结果

- 明确的客户端不匹配文本产生 `TdxHandshakeRejected`；空握手和初始化坏帧产生
  `TdxHandshakeError`，同时释放连接。
- 分片头和 body 会读满；部分发送会继续发送。截断、错误压缩、错误命令和请求标识
  不匹配不会当作正常数据。
- 收到完整非空但语义未知的握手响应记作 `unknown`，不能凭长度或未定义状态字节
  认定服务端能力。仍须用实际所需接口验证数据。
- 合法零记录保持合法空结果。协议错误与合法空不同：低层兼容模式请求返回 `None`
  并保留 `last_error`；严格模式抛 `TdxFunctionCallError` 并保留原始 cause。
- 标准客户端构造失败显式抛错；扩展客户端兼容模式保留 `closed` 和 `last_error`，
  严格模式抛错。高层各接口的失败约定以其 API 文档为准。

`client.last_error` 可用于诊断最近失败；下一次成功响应会清除低层错误。
`client.client.handshake_results` 保留握手策略、步骤、命令、状态、响应长度、有限
前缀和 SHA-256。异常保留命令、长度、有限摘要及原始原因，不在错误文本中输出完整报文。

## 重试、心跳与关闭

`auto_retry=True` 仅对网络错误进行有限重试，`max_retries` 表示额外尝试次数，默认 4。
明确拒绝、协议损坏及参数错误不盲目重试。重连使用新 socket 并保留服务器、timeout、
bind 和握手选项。`adjusted_bars()` 的独立连接也沿用调用方的 `auto_retry`、
`raise_exception` 和 `max_retries`，并保持心跳关闭。库内请求、心跳和连接状态操作共享每实例的锁。

心跳按最后一次成功响应后的空闲时间触发，使用单调时钟；发送失败不会刷新 ACK。
每个心跳线程绑定一代连接，旧线程不能向新 socket 发包。`close()` 幂等，停止心跳并
取消已建立连接上的收发及重试等待；显式关闭后普通请求不会偷偷重开连接。
需要恢复时调用 `reconnect()`，并检查结果。DNS、尚未建立的连接和用户回调仍应受有限
timeout 与外层任务期限约束，不承诺所有阻塞都能立即取消。

## 低层扩展 {#low-level-extensions}

需要实例局部自定义解析时，从 `mootdx.protocol` 导入受支持的入口：

```python
from mootdx.protocol import GetSecurityBarsCmd, last_ack_time

class CustomBarsParser(GetSecurityBarsCmd):
    def parseResponse(self, body):
        rows = super().parseResponse(body)
        # 在这里处理当前实例需要的附加字段，不改写全局解析器。
        return rows

@last_ack_time
def read_custom_bars(api, category, market, code, start, count):
    parser = CustomBarsParser(api.client, lock=api.lock)
    parser.setParams(category, market, code, start, count)
    return parser.call_api()
```

该入口导出三个协议客户端、结构化异常、`last_ack_time`、`GetSecurityBarsCmd`、
`GetSecurityQuotesCmd` 和 `get_datetime/get_price/get_volume`。它们与 Mootdx 内部
使用同一份实现。未导出的 `_protocol` 模块仍为私有实现。
低层返回值保持原始协议单位，扩展调用方仍须验证证券、日期、字段和数量。

升级时删除应用对独立 `tdxpy` 的依赖声明，并迁移实际使用的 import。Mootdx 不创建
顶层 `tdxpy` 命名空间，也不会自动满足其他包的 `Requires-Dist: tdxpy`。旧应用迁移应
独立验证，不能只替换安装包。
