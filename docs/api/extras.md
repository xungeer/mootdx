# 辅助工具

本页记录当前仓库中可直接使用、但不属于 `Quotes` / `Reader` / `Affair` 主入口的
辅助能力。它们可能访问第三方网络或修改本地通达信文件，调用前请留意每节的边界。

## 同花顺年度复权数据

```python
from mootdx.contrib.adjust import get_adjust_year

data = get_adjust_year(
    symbol='600036',
    year=2024,
    factor='before',
)
```

`get_adjust_year(symbol, year=None, factor='00')` 访问同花顺 HTTP 接口并返回
DataFrame。尽管函数默认值仍是 `00`，当前实现只接受：

- `before` 或 `01`：前复权；
- `after` 或 `02`：后复权。

其他值（包括默认 `00`）会记录警告并返回空 DataFrame。常见 HTTP、连接或限频解析
失败会在当前调用中被捕获并返回空 DataFrame；只有未被函数内部捕获的异常才可能由
外层重试装饰器再次调用。

标准市场 K 线优先使用 `StdQuotes.adjusted_bars()`，它直接请求通达信服务端复权，
不依赖第三方复权数据。参见[标准行情](quote1.md#server-adjusted-bars)。

## 通达信导出文本转 CSV

### 单文件

```python
from mootdx.tools import tdx2csv

data = tdx2csv.txt2csv(
    infile='C:/tdx/export/SH#600036.txt',
    outfile='C:/tdx/export/SH#600036.csv',
)
```

`txt2csv()` 按通达信导出文本格式读取 GBK 文件，返回以 `date` 为索引的 DataFrame。
未传 `outfile` 时默认将输入文件的 `.txt` 替换为 `.csv`。输入不存在或无法解析时返回
空 DataFrame。

只有目标文件的父目录已经存在时才会写出 CSV；函数不会自动创建目标目录。

### 批量转换

```python
tdx2csv.batch(
    src='C:/tdx/export',
    dst='C:/tdx/output',
)
```

`batch()` 异步处理 `src` 目录下所有 `.txt`。当前实现保留了 `dst` 参数但没有使用它，
生成的 `.csv` 实际写在源文件旁边。不要依赖 `dst` 选择输出目录。

## 日期与节假日 {#calendar-tools}

```python
from mootdx.utils import holiday

is_holiday = holiday.holiday(date='2026-10-01')
row = holiday.holiday_(date='2026-10-01')
trading_days = holiday.holidays()
one_trading_day = holiday.holiday2(date='2026-07-21')
```

这些名称的口径不同：

| 接口 | 实际返回 |
| --- | --- |
| `holiday()` | 日期是法定节假日或周末时为 `True`；否则为 `False` |
| `holiday_()` | 对应节假日记录的 DataFrame |
| `holidays()` | 从新浪数据解码得到的历史交易日 DataFrame |
| `holiday2()` | 全部交易日，或指定日期对应的交易日 DataFrame |

函数会访问通达信网站或新浪接口并使用本地缓存；它们不是无需更新的静态交易日历。
`holidays()` 依赖安装包中的 `mini-racer` 运行 JavaScript 解码逻辑；导入问题参见
[mini-racer 依赖说明](../faq/py_mini_racer.md)。

## 自定义板块 {#custom-blocks}

`Customize` 直接读写通达信 `T0002/blocknew` 目录：

```python
from mootdx.tools.customize import Customize

custom = Customize(tdxdir='C:/new_tdx')

custom.create(name='示例板块', symbol=['600036', '000001'])
custom.update(name='示例板块', symbol=['688001'])
codes = custom.search(name='示例板块')
all_blocks = custom.search(group=True)
custom.remove(name='示例板块')
```

| 方法 | 返回与副作用 |
| --- | --- |
| `create()` | 写入配置和 `.blk` 文件；通常成功时返回 `True`，名称重复时抛异常 |
| `update()` | 未传名称时返回 `False`；名称不存在时创建并返回 `True`；更新已有板块时返回写入的字符数 |
| `search()` | 指定名称时返回代码列表或 `None`；未指定时返回 DataFrame |
| `remove()` | 删除 `.blk` 并改写配置；返回写入字节数或 `None` |

目录必须已经存在。`remove()` 是破坏性操作，建议先备份 `T0002/blocknew`。只需要创建
或查询板块时，也可以使用 `StdReader.block_new()`，参见[离线行情](reader.md#block-files)。
