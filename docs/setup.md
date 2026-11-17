# 安装与开发

## 运行要求

- Python `>=3.10,<4.0`
- Windows、macOS 或 Linux
- 在线接口需要能够访问通达信行情或财务服务器
- 本地读取接口需要已有的通达信数据目录

通达信协议层已经融合进 Mootdx。安装发布包、源码或构建后的 wheel 时，都无需
单独安装 `tdxpy`，也不需要 GitHub SSH 权限。内置源码的归属与许可见
[第三方声明](third-party.md)。

## 安装 v0.13.0

本文档对应 `xungeer/mootdx` 的 [GitHub v0.13.0 发行版](https://github.com/xungeer/mootdx/releases/tag/v0.13.0)。
本次通过 GitHub 提供源码、wheel 和校验文件，不发布到 PyPI。安装发行版 wheel：

```shell
python -m pip install "https://github.com/xungeer/mootdx/releases/download/v0.13.0/mootdx-0.13.0-py3-none-any.whl"
```

需要源码时，固定到同一 tag：

```shell
git clone --branch v0.13.0 --depth 1 https://github.com/xungeer/mootdx.git
cd mootdx
python -m pip install .
```

`pip install -U mootdx` 访问的是所配置软件源中的同名项目，不能保证得到本 fork。

也可以从同一 Release 下载 wheel、源码包及校验文件，核对 SHA-256 后安装本地文件：

```shell
python -m pip install ./mootdx-0.13.0-py3-none-any.whl
# 或安装源码包
python -m pip install ./mootdx-0.13.0.tar.gz
```

wheel 已包含协议层，安装时只需解析公开运行依赖。项目没有 `cli` 或 `all` 安装
附加项。安装后检查版本和命令行入口，版本应为 `0.13.0`：

```shell
python -c "import mootdx; print(mootdx.__version__)"
python -m mootdx --help
```

同名 PyPI 项目及其版本号不能证明它包含本 fork 的实现。复现本文档应使用上述固定
tag 或 Release 产物。已有环境需要按 [升级说明](upgrade-0.13.md) 更新依赖及 import，
不能仅凭安装成功判断应用已经迁移。

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
