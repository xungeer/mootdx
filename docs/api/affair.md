# 历史财务文件：`Affair`

`Affair` 用于查询、下载和解析通达信专业财务文件。它与在线行情中的
`StdQuotes.finance()` / `finances()` 不同：前者处理按报告期发布的 `gpcw*.zip`
历史文件，后者查询行情主站提供的单只或批量财务快照。

财务文件字段参见[财务字段对照](fields.md)。

## 推荐流程

```python
from mootdx.affair import Affair

# 1. 查询远程文件清单
files = Affair.files()

# 2. 下载一个文件
Affair.fetch(downdir='output', filename='gpcw20231231.zip')

# 3. 解析为 DataFrame
data = Affair.parse(downdir='output', filename='gpcw20231231.zip')
```

这些操作都可能连接财务数据主站；服务端可用性和可下载的报告期以 `Affair.files()`
的实时结果为准。

## 查询文件清单

```python
files = Affair.files()
```

返回值是字典列表，每项包含：

| 字段 | 含义 |
| --- | --- |
| `filename` | 文件名，例如 `gpcw20231231.zip` |
| `hash` | 服务端提供的 MD5 值 |
| `filesize` | 文件大小（字节） |

## 下载文件

### 下载一个文件

```python
ok = Affair.fetch(
    downdir='output',
    filename='gpcw20231231.zip',
)
```

指定 `filename` 时，下载成功后返回 `True`。`downdir` 不存在时会自动创建。

### 同步全部文件

```python
Affair.fetch(downdir='output')
```

不传 `filename` 时会根据远程清单异步同步全部文件：本地文件 MD5 与清单一致时跳过，
否则重新下载。该调用完成后返回 `None`，应通过目标目录或后续解析确认结果。

## 解析文件

```python
data = Affair.parse(
    downdir='output',
    filename='gpcw20231231.zip',
)
```

- `filename` 必填；省略时记录错误并返回 `None`。
- 文件在本地不存在时，`parse()` 会先尝试下载，所以它不保证是纯本地操作。
- 当前实现要求真实文件名带 `.zip` 或 `.dat` 扩展名，不会自动猜测扩展名。
- 返回值是以证券代码 `code` 为索引的 DataFrame；默认使用中文字段名。

如果需要原始编号列名，可传入非 `zh` 的 `header`：

```python
raw = Affair.parse(
    downdir='output',
    filename='gpcw20231231.zip',
    header='raw',
)
# report_date, col1, col2, ...
```

## 保存解析结果

保存是 pandas 的职责：

```python
data.to_csv('gpcw20231231.csv')
data.to_excel('gpcw20231231.xlsx')
```

Excel 输出需要环境中存在 pandas 对应的写入引擎。命令行下载和解析方式参见
[财务文件命令](../cli/affair.md)。
