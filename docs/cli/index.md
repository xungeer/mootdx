# 命令行工具

Mootdx 提供 `mootdx` 命令，用于在线行情读取、本地通达信文件读取、财务文件处理和行情服务器测速。

安装项目后可以使用控制台入口：

```shell
mootdx --help
```

也可以使用等价的模块入口：

```shell
python -m mootdx --help
```

## 命令总览

| 命令 | 用途 | 重要说明 |
| --- | --- | --- |
| [`quotes`](quotes.md) | 读取单个证券的在线 K 线。 | 当前所有 action 实际均返回日 K。 |
| [`bundle`](bundle.md) | 批量下载在线 K 线。 | output 是目录，每个证券生成一个文件。 |
| [`reader`](reader.md) | 读取通达信本地 `vipdoc` 行情文件。 | 数据目录必须存在。 |
| [`affair`](affair.md) | 查询、下载和解析历史财务文件。 | output 仅在解析操作中生效。 |
| [`bestip`](bestip.md) | 测试行情服务器并选择地址。 | 每次执行都会写 `~/.mootdx/config.json`。 |

查看总版本：

```shell
mootdx --version
```

查看子命令帮助：

```shell
mootdx quotes --help
mootdx bundle --help
mootdx reader --help
mootdx affair --help
mootdx bestip --help
```

## 输出格式

需要写 DataFrame 的命令根据文件后缀选择格式：

| 后缀 | 格式 | 额外要求 |
| --- | --- | --- |
| `.csv` | CSV | 无额外 pandas engine。 |
| `.json` | JSON records | 无额外 pandas engine。 |
| `.xlsx` | Excel | 需要兼容的 Excel engine。 |
| `.xls` | 旧版 Excel 分支 | 当前依赖不提供可用 writer，通常会报错。 |
| `.h5` | HDF5 | 需要 PyTables。 |

Mootdx 当前没有自动安装 Excel 或 HDF5 的可选 engine。已存在的 CSV、JSON、Excel
目标会被覆盖，HDF5 中名为 `df` 的 key 会被替换。无法识别的后缀不会自动报错，
也不会写出文件，但其父目录仍可能被创建。

## 通用边界

- `quotes`、`bundle`、`affair` 和 `bestip` 需要访问外部网络；`reader` 只读本地文件。
- 在线行情和 bestip 使用通达信 TCP 协议，本项目没有通过这些命令启动 HTTP 服务。
- 导入 CLI 时会确保 `~/.mootdx/` 目录存在；在线行情或财务命令发现配置缺失、JSON
  损坏时，会先测速并重写 `~/.mootdx/config.json`。
- 多数参数是普通文本而非 Click 枚举，错误值可能回退、输出 `None` 或在运行时抛出异常。请优先使用各命令页面列出的值。
- 命令会直接输出 DataFrame 或底层异常；在自动化脚本中使用前，建议先检查退出状态和目标文件是否实际生成。
