# Mootdx

Mootdx 是面向通达信数据的 Python 接口，覆盖在线行情、本地数据文件和专业财务数据。
项目支持 Python `>=3.10,<4.0`。沪深北行情、批量财务和服务端复权所需的通达信
协议层已经内置，安装时无需另装 `tdxpy`，也不需要 GitHub SSH 权限。

## 能力概览

- 标准市场：实时行情、K 线、服务端复权 K 线、指数、分时、分笔、F10、除权除息、
  沪深北证券列表、批量财务信息和行业分类码。
- 扩展市场：期货、港股等通达信扩展行情服务所提供的市场、代码、行情和成交数据。
- 本地数据：读取通达信日线、1 分钟、5 分钟和板块文件。
- 专业财务：查询、下载并解析通达信历史专业财务文件。
- 命令行：提供服务器测速、行情读取、财务文件处理和批量下载入口。

## 安装当前仓库版本

本文档对应仓库中的 Mootdx 0.12.0。公共 PyPI 当前最新版本仍是 0.11.7，不包含本文
记录的协议层内收和 0.12.0 接口；在 0.12.0 发布前，请从当前仓库安装：

```shell
git clone https://github.com/xungeer/mootdx.git
cd mootdx
python -m pip install .
```

0.12.0 发布到 PyPI 后，才可改用 `python -m pip install -U mootdx` 获得同等能力。

## 最小示例

下面的代码连接标准行情服务器并读取招商银行最近 10 条日线：

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market="std")
try:
    data = client.bars(symbol="600036", frequency="day", offset=10)
    print(data)
finally:
    client.close()
```

## 文档与开发

- [文档导航](docs/index.md)
- [安装与开发环境](docs/setup.md)
- [快速上手](docs/quick.md)
- [Python API](docs/api/index.md)
- [命令行工具](docs/cli/index.md)
- [版本历史](docs/history.md)
- [项目仓库](https://github.com/xungeer/mootdx)与
  [问题反馈](https://github.com/xungeer/mootdx/issues)

## 许可与声明

项目代码按 [MIT License](LICENSE) 提供。内置协议层的来源、修改关系和许可证全文见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

本项目仅用于学习与技术交流，不提供投资建议，也不保证数据的完整性、及时性或准确性。
行情与财务数据的使用还应遵守数据提供方的条款及适用法律法规。
