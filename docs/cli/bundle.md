# `mootdx bundle`

## 用途

连接通达信在线行情服务器，批量下载一个或多个证券的 K 线，并为每个证券写出一个文件。

该命令处理在线行情，不读取本地通达信导出文件。

## 参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-o, --output TEXT` | `bundle` | **输出目录**，不是单个文件名。 |
| `-s, --symbol TEXT` | `600000` | 一个或多个证券代码，使用英文或中文逗号分隔。 |
| `-a, --action TEXT` | `bars` | K 线类型，映射见下表。 |
| `-m, --market TEXT` | `std` | `std` 为标准市场，`ext` 为扩展市场。 |
| `-e, --extension TEXT` | `csv` | 每个证券的文件扩展名，不需要前导点。 |
| `-h, --help` | — | 显示帮助。 |

action 映射：

| action | 请求频率 | 数据 |
| --- | --- | --- |
| `bars`、`daily` | `9` | 日 K。 |
| `minute` | `8` | 1 分钟 K。 |
| `fzline` | `0` | 5 分钟 K。 |
| 其它值 | `9` | 当前会回退为日 K。 |

## 示例

批量下载两只证券的日 K：

```shell
mootdx bundle \
  --symbol 600000,000001 \
  --action daily \
  --output bundle \
  --extension csv
```

以上命令生成：

```text
bundle/600000.csv
bundle/000001.csv
```

下载 1 分钟 K 到另一个目录：

```shell
mootdx bundle -s 600000,000001 -a minute -o minute-data -e csv
```

也可以使用中文逗号：

```shell
mootdx bundle --symbol 600000，000001 --output daily-data
```

## 输出目录与格式

`--output` 始终作为目录使用，最终路径为：

```text
<output>/<symbol>.<extension>
```

因此不要使用旧示例中的 `--output minute.csv` 来表示单个文件；那会创建名为 `minute.csv` 的目录，并在其中写入 `600000.csv`。

导出分支识别 `csv`、`json`、`xlsx`、`xls` 和 `h5`。Excel 和 HDF5 需要 pandas
对应的可选引擎，例如 `openpyxl` 或 `tables`；当前依赖未提供这些引擎，现代 pandas
环境通常也没有 `.xls` writer。目标文件已经存在时会被覆盖。

## 边界与限制

- 命令需要外网和可连接的通达信 TCP 行情服务器。
- CLI 不提供 `start` 或 `offset`；每个证券使用 `bars()` 默认范围，标准市场默认最多请求 800 条。
- `--action`、`--market` 和 `--extension` 都没有枚举校验。未知 action 回退到日 K；未知扩展名可能不写文件，但命令仍打印“下载完成”。
- `--market ext` 时，symbol 还需要包含扩展市场 ID，例如 `市场ID#代码`。
- 任一证券请求抛出异常时命令会终止，后续证券不会继续处理。
- 输出目录不存在时会在首次写文件时自动创建。
- 配置缺失或 JSON 损坏时，创建行情客户端会先测速并重写
  `~/.mootdx/config.json`。
