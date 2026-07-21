# `mootdx reader`

## 用途

读取通达信本地数据目录中的行情文件。该命令读取的是通达信安装目录下的 `vipdoc` 数据，不是普通 CSV 导出文件，也不访问在线行情服务器。

## 参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-d, --tdxdir TEXT` | `C:/new_tdx` | 通达信数据根目录，目录必须存在。 |
| `-s, --symbol TEXT` | `600000` | 证券代码。 |
| `-a, --action TEXT` | `daily` | 读取类型，常用值见下表。 |
| `-m, --market TEXT` | `std` | `std` 为标准市场，`ext` 为扩展市场。 |
| `-o, --output TEXT` | 不写文件 | 按文件扩展名导出读取结果。 |
| `-h, --help` | — | 显示帮助。 |

常用 action：

| action | 数据 |
| --- | --- |
| `daily` | 日 K 线。 |
| `minute` | 1 分钟 K 线。 |
| `fzline` | 5 分钟 K 线。 |

## 示例

读取日 K 并在终端显示：

```shell
mootdx reader --tdxdir C:/new_tdx --symbol 600000 --action daily
```

读取 1 分钟 K 并导出 CSV：

```shell
mootdx reader --tdxdir C:/new_tdx --symbol 600000 --action minute --output 600000-minute.csv
```

读取 5 分钟 K：

```shell
mootdx reader -d C:/new_tdx -s 600000 -a fzline
```

macOS 或 Linux 用户应将 `--tdxdir` 替换为实际的通达信数据目录。源码仓库内也可以用测试数据核对日线读取：

```shell
mootdx reader --tdxdir tests/fixtures --symbol 688001 --action daily
```

## 输出文件

当前导出工具识别以下后缀：

- `.csv`
- `.json`
- `.xlsx`、`.xls`
- `.h5`

Excel 和 HDF5 导出需要 pandas 对应的可选引擎，例如 `openpyxl` 或 `tables`；Mootdx
当前没有自动安装这些引擎，现代 pandas 环境通常也没有 `.xls` writer。目标文件已经
存在时会被覆盖。不传 `--output` 时只在终端打印结果。

## 边界与限制

- `--tdxdir` 必须是已经存在的目录，默认值主要面向 Windows。
- 目录内需要存在通达信约定的 `vipdoc/<市场>/<周期>/` 文件结构；找不到证券文件时通常输出 `None`。
- `--action` 和 `--market` 是普通文本参数，没有枚举校验。未知 action 会导致属性错误；除精确的 `ext` 外，其它 market 值会进入标准市场读取器。
- 扩展市场代码需要符合本地通达信文件命名，例如包含 `市场ID#代码` 的形式。
- 命令不提供日期范围、起始偏移或条数筛选；需要这些能力时应使用 Python API 进一步处理结果。
