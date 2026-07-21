# `mootdx quotes`

## 用途

连接通达信在线行情服务器，读取单个证券的 K 线数据，并在终端显示或导出到文件。

## 参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-o, --output TEXT` | 不写文件 | 按文件扩展名导出结果。 |
| `-s, --symbol TEXT` | `600000` | 证券代码。 |
| `-a, --action TEXT` | `bars` | 操作名称；当前实现的限制见下文。 |
| `-m, --market TEXT` | `std` | `std` 为标准市场，`ext` 为扩展市场。 |
| `-h, --help` | — | 显示帮助。 |

## 当前 action 行为

当前版本会在执行时把 action 固定为 `bars`，并使用频率 9 请求日 K。因此：

- 不传 `--action` 时读取日 K。
- `--action daily` 读取日 K。
- `--action minute` **仍然读取日 K**。
- `--action fzline` **仍然读取日 K**。
- 其它 action 文本也仍然读取日 K。

在该实现修复前，请只把 `mootdx quotes` 当作在线日 K 命令使用；不要依赖旧文档中关于 1 分钟或 5 分钟 action 的描述。

## 示例

读取默认证券的在线日 K：

```shell
mootdx quotes
```

读取指定证券并导出 CSV：

```shell
mootdx quotes --symbol 600000 --output 600000-daily.csv
```

显式写出当前有效的数据类型：

```shell
python -m mootdx quotes -s 000001 -a daily
```

命令执行后即使写入了文件，也仍会在终端打印 DataFrame。

## 输出文件

当前导出工具识别 `.csv`、`.json`、`.xlsx`、`.xls` 和 `.h5`。Excel 和 HDF5 导出
需要 pandas 对应的可选引擎，例如 `openpyxl` 或 `tables`；Mootdx 当前没有自动安装
这些引擎，现代 pandas 环境通常也没有 `.xls` writer。目标文件已经存在时会被覆盖。

## 边界与限制

- 命令需要外网和可连接的通达信 TCP 行情服务器。
- 标准市场每次命令使用 `bars()` 的默认范围：从最新位置开始，最多请求 800 条。
- CLI 没有提供 `start`、`offset` 或更多 K 线周期参数；这些能力需要使用 Python API。
- `--market ext` 只选择扩展市场客户端，扩展市场 symbol 还需携带市场 ID，例如 `市场ID#代码`；CLI 没有单独的市场 ID 参数。
- 首次运行若缺少 `~/.mootdx/config.json`，或现有文件不是有效 JSON，行情客户端会先
  测速并重写配置。
- `--action` 和 `--market` 没有枚举校验，不能据此判断输入一定有效。
