# 安装与开发

## 运行要求

- Python `>=3.10,<4.0`
- Windows、macOS 或 Linux
- 在线接口需要能够访问通达信行情或财务服务器
- 本地读取接口需要已有的通达信数据目录

通达信协议层已经融合进 Mootdx。安装发布包、源码或构建后的 wheel 时，都无需
单独安装 `tdxpy`，也不需要 GitHub SSH 权限。内置源码的归属与许可见
[第三方声明](third-party.md)。

## 安装当前文档对应版本

本文档对应仓库中的 Mootdx 0.12.0。公共 PyPI 当前最新版本仍是 0.11.7，不包含
协议层内收及本文记录的 0.12.0 接口。在 0.12.0 发布前，通过 HTTPS 克隆当前仓库，
并在仓库根目录安装：

```shell
git clone https://github.com/xungeer/mootdx.git
cd mootdx
python -m pip install .
```

项目没有 `cli` 或 `all` 安装附加项；命令行及协议层所需的运行依赖由基础包统一声明。

安装后可以检查版本和命令行入口：

```shell
python -c "import mootdx; print(mootdx.__version__)"
python -m mootdx --help
```

## PyPI 发布包

可在 [PyPI 项目页](https://pypi.org/project/mootdx/)核对最新公开版本。只有版本达到
0.12.0 或更高时，下面的命令才会安装到与本文档一致的接口：

```shell
python -m pip install -U mootdx
```

从当前仓库构建出的 Mootdx wheel 包含协议层，只需安装该 wheel 及其公开运行依赖。

## 开发与测试

仓库以 Python 3.12 作为日常开发基线，推荐使用 uv 0.11.17 或更高版本创建锁定环境：

```shell
uv sync --locked
uv run --locked pytest
```

项目保留 Poetry 工作流时，测试依赖位于 `test` 依赖组：

```shell
poetry install --sync --with test
poetry run pytest
```

不使用 uv 或 Poetry 时，也可以安装项目与测试依赖清单：

```shell
python -m pip install . -r tests/requirements.txt
python -m pytest
```

## 构建文档

文档使用 MkDocs：

```shell
python -m pip install -r docs/requirements.txt
python scripts/verify/verify_docs.py --pre-release
```

校验脚本会检查 Markdown 相对链接、Python 代码块语法、MkDocs 导航、全部 CLI 帮助入口，
并在发布模式执行 `mkdocs build --strict`。未安装 MkDocs 时，可以先执行不要求站点
构建的快速检查：

```shell
python scripts/verify/verify_docs.py --pre-commit
```

Makefile 提供等价入口：`make docs-check`、`make docs-release-check`；本地预览运行
`make docs`。

## 维护依赖与许可证

修改运行依赖时，应同步维护标准 `[project]` / uv 配置和 `[tool.poetry]` 配置，并分别
更新 `uv.lock` 与 `poetry.lock`，避免两套环境漂移。修改内置协议层来源或内容时，
还应同步维护根目录 `THIRD_PARTY_NOTICES.md` 与站内[第三方声明](third-party.md)。
