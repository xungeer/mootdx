# 安装方式

## 普通安装

### 标准安装

> 新手建议使用 `pip install -U 'mootdx[all]'` 安装

```shell
# 包含核心依赖安装
pip install -U 'mootdx'

# 包含命令行依赖安装, 如果使用命令行工具可以使用这种方式安装
pip install -U 'mootdx[cli]'

# 包含所有扩展依赖安装, 如果不清楚各种依赖关系就用这个命令
pip install -U 'mootdx[all]'
```

## 升级版本

```shell
pip install -U mootdx
```

## 源码安装[不建议, 速度较慢]

直接远程源码安装

```shell
pip install git+https://github.com/mootdx/mootdx.git
```

本 fork 新增的沪深北三市场股票列表与批量财务接口依赖
`xungeer/tdxpy` v0.2.9；源码部署应成对安装这两个 Git 版本。普通 PyPI
安装仍以公开包实际发布版本为准。

## 源码开发与测试

测试依赖位于 Poetry 的 `test` 依赖组，其中包括使用冻结时间测试缓存逻辑所需的
`freezegun`。应在 mootdx 项目根目录使用独立虚拟环境，不要复用其它项目环境：

```shell
poetry install --sync --with test
poetry run pytest
```

不使用 Poetry 时，可以直接安装运行依赖和测试依赖：

```shell
python -m pip install -r requirements.txt -r tests/requirements.txt
python -m pytest
```
