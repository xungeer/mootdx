# 离线行情：`Reader`

`Reader` 解析通达信客户端数据目录中的原始行情文件。原始文件读取不连接行情主站；
只有 `daily(..., adjust='qfq'/'hfq')` 的客户端复权路径会联网。入口是
`Reader.factory()`；`tdxdir` 必须指向一个已经存在的通达信目录。

```python
from mootdx.reader import Reader

reader = Reader.factory(market='std', tdxdir='C:/new_tdx')
```

如果目录不存在，构造 `Reader` 时会立即抛出异常。`market='ext'` 创建扩展市场读取器；
其他值都会回落到标准市场读取器，因此建议只使用 `std` 或 `ext`。

## 数据目录

标准市场文件通常位于：

```text
C:/new_tdx/
└── vipdoc/
    ├── sh/
    │   ├── lday/sh600000.day
    │   ├── minline/sh600000.lc1
    │   └── fzline/sh600000.lc5
    ├── sz/
    └── bj/
```

扩展市场文件位于 `vipdoc/ds/`，代码使用 `市场 ID#品种代码`，例如
`4#CF7D0LAO`。读取器会根据证券代码、目录和扩展名查找文件；它不解析通达信“数据
导出”功能生成的文本文件，文本转换请参见[辅助工具](extras.md)。

## 标准市场行情

### 日线

```python
daily = reader.daily(symbol='600036')
```

`daily()` 读取 `.day` 文件并返回 `pandas.DataFrame`。文件不存在时返回空
DataFrame。代码可以带 `sh`、`sz`、`bj` 前缀；未带前缀时由代码规则推断市场。

`daily()` 还接受 `adjust='qfq'` 或 `adjust='hfq'`：

```python
qfq = reader.daily(symbol='600036', adjust='qfq')
```

这条路径会联网查询通达信除权除息数据并缓存到 `~/.mootdx/xdxr/`，随后还会从新浪
获取复权因子并缓存到 `~/.mootdx/caches/factor/`。因此“读取本地日线并复权”不是
纯离线操作。只读取原始文件时不要传 `adjust`。

### 一分钟线和五分钟线

```python
one_minute = reader.minute(symbol='600036', suffix=1)
five_minutes = reader.minute(symbol='600036', suffix=5)

# fzline() 等价于 minute(..., suffix=5)
five_minutes = reader.fzline(symbol='600036')
```

`suffix=5` 查找 `fzline` 下的 `.lc5` 或 `.5` 文件；其他值查找 `minline` 下的
`.lc1` 或 `.1` 文件。找到文件时返回 DataFrame，未找到时返回 `None`。

## 板块文件 {#block-files}

`block()` 解析 `T0002/hq_cache` 下的板块或配置文件：

```python
concepts = reader.block(symbol='block_gn.dat')
grouped = reader.block(symbol='block_gn.dat', group=True)
```

常见文件包括 `block_gn.dat`、`block_fg.dat`、`block_zs.dat`、`hkblock.dat`、
`tdxhy.cfg` 和 `tdxzs.cfg`。返回值取决于文件类型和 `group`，可能是 DataFrame、
字典或 `None`。

`block_new()` 操作 `T0002/blocknew` 下的自定义板块：

```python
# 创建板块；目录必须已经存在
reader.block_new(name='自选示例', symbol=['600036', '000001'])

# 查询指定板块，返回代码列表或 None
codes = reader.block_new(name='自选示例')

# 查询全部板块，返回 DataFrame
blocks = reader.block_new(group=True)
```

创建操作会修改通达信本地文件；调用前请自行备份 `T0002/blocknew`。

## 扩展市场文件

```python
ext = Reader.factory(market='ext', tdxdir='C:/new_tdx')

daily = ext.daily(symbol='4#CF7D0LAO')
minute = ext.minute(symbol='4#CF7D0LAO')
five_minutes = ext.fzline(symbol='4#CF7D0LAO')
```

扩展读取器提供 `daily()`、`minute()` 和 `fzline()`，但 `minute()` 没有 `suffix`
参数。代码必须能映射到 `vipdoc/ds` 中的真实文件名。`daily()`、`minute()` 在文件
不存在时返回 `None`；当前 `fzline()` 不会预先保护缺失路径，调用前应确认对应
`.lc5` 文件存在。

## 返回值差异

- `StdReader.daily()` 经过统一转换，空结果是空 DataFrame。
- 标准分钟线和多数扩展读取接口在文件不存在时返回 `None`。
- 成功读取的行情数据以时间为索引；具体列由文件格式决定。
- 本页面只描述 `Reader` 的高层公开入口，`mootdx._protocol.reader` 属于内部实现，
  不承诺兼容性。
