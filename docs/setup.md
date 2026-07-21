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

本 fork 的服务端复权接口依赖配套的 `xungeer/tdxpy` v0.3.0。源码部署时应
按标签成对安装：

```shell
python -m pip install 'git+ssh://git@github.com/xungeer/tdxpy.git@v0.3.0'
python -m pip install 'git+ssh://git@github.com/xungeer/mootdx.git@v0.12.0'
```

两个 fork 版本均未发布到公共 PyPI；以上命令要求当前机器已有对应私有仓库的
SSH 访问权限。私有 wheelhouse 部署时，应先安装环境锁定的运行依赖和
`tdxpy-0.3.0` wheel，再以 `--no-deps` 安装 `mootdx-0.12.0` wheel，避免
安装器重新解析 wheel 元数据中的私有依赖来源。

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
