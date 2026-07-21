# `mootdx affair`

## 用途

查询、下载和解析通达信历史专业财务文件。远程文件通常以 `gpcwYYYYMMDD.zip` 命名。

## 参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-p, --parse TEXT` | 不解析 | 解析指定财务 ZIP 文件；本地不存在时会先下载。 |
| `-f, --fetch TEXT` | 不下载单个文件 | 下载指定文件；传入 `all` 等价于批量下载。 |
| `-a, --downall` | 关闭 | 下载远程列表中的全部文件。 |
| `-o, --output TEXT` | 不写解析结果 | 导出解析后的 DataFrame。**仅 parse 操作时实际生效。** |
| `-d, --downdir TEXT` | `output` | 下载和查找财务文件的目录。 |
| `-l, --listfile` | 关闭 | 显示远程文件列表。 |
| `-v, --verbose` | 关闭 | 输出调试日志。该参数可重复，但当前没有多级详细度。 |
| `-h, --help` | — | 显示帮助。 |

旧文档中的长参数 `--files` 已不存在，请使用 `--listfile`；短参数仍是 `-l`。

## 示例

### 查询可用文件

```shell
mootdx affair --listfile
```

返回结果包含 `filename`、`filesize` 和 `hash`。列表来自远程服务，会随财务文件发布而变化。

### 下载单个文件

先从列表复制实际存在的 filename，再执行：

```shell
mootdx affair --fetch gpcw20241231.zip --downdir output
```

单文件下载会以写入模式重新创建目标 ZIP；同名文件已经存在时也会被覆盖。批量下载
才会用远程 MD5 跳过一致的本地文件。

### 下载全部文件

```shell
mootdx affair --downall --downdir output
```

也可以使用兼容写法：

```shell
mootdx affair --fetch all --downdir output
```

### 解析并导出

```shell
mootdx affair \
  --parse gpcw20241231.zip \
  --downdir output \
  --output output/gpcw20241231.csv
```

若 ZIP 文件尚未下载，parse 会先下载再解析。解析后的 DataFrame 会打印到终端，并写入指定 CSV。

## 操作优先级

同时传入多个操作参数时，命令按以下顺序选择并提前返回：

1. `--listfile`
2. `--downall` 或 `--fetch all`
3. `--fetch <filename>`
4. `--parse <filename>`

建议每次只指定一种操作，避免误解执行结果。

## `--output` 的实际范围

`--output` 只在 `--parse` 分支中写出解析数据。以下用法不会生成导出文件：

```shell
mootdx affair --fetch gpcw20241231.zip --output result.csv
mootdx affair --downall --output result.csv
```

解析结果的导出分支识别 `.csv`、`.json`、`.xlsx`、`.xls` 和 `.h5`。Excel 和 HDF5
需要 pandas 对应的可选引擎；现代 pandas 环境通常没有 `.xls` writer。现有输出文件
会被覆盖。

## 边界与限制

- 命令开始时总会先请求远程财务文件列表，包括 parse 和单文件 fetch 操作，因此需要外网。
- parse 参数会被规范为 `.zip` 文件名，并且必须出现在当前远程列表中。
- `--downall` 可能下载大量历史文件，请预留时间和磁盘空间；已存在且 MD5 匹配的文件会跳过。
- 不传任何操作参数时，命令仍会请求远程列表，但不会显示或下载内容。
- 下载进度、耗时和可用文件完全取决于远程服务状态。
- 配置缺失或 JSON 损坏时，财务客户端会先测速并重写
  `~/.mootdx/config.json`。
