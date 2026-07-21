通达信数据读取接口
==================

[![image](https://badge.fury.io/py/mootdx.svg)](http://badge.fury.io/py/mootdx)
[![image](https://img.shields.io/travis/bopo/mootdx.svg)](https://travis-ci.org/mootdx/mootdx)
[![Documentation Status](https://readthedocs.org/projects/mootdx/badge/?version=latest)](https://mootdx.readthedocs.io/zh/latest/?badge=latest)
[![Updates](https://pyup.io/repos/github/mootdx/mootdx/shield.svg)](https://pyup.io/repos/github/mootdx/mootdx/)

如果喜欢本项目可以在右上角给颗⭐！你的支持是我最大的动力😎！

**郑重声明: 本项目只作学习交流, 不得用于任何商业目的.**

-   开源协议: MIT license
-   在线文档: <https://www.mootdx.com>
-   国内镜像: <https://gitee.com/ibopo/mootdx>
-   项目仓库: <https://github.com/mootdx/mootdx>
-   问题交流: <https://github.com/mootdx/mootdx/issues>

版本更新(倒序)
--------------

版本更新日志: <https://mootdx.readthedocs.io/zh_CN/latest/history/>

运行环境
--------

-   操作系统: Windows / MacOS / Linux 都可以运行.
-   Python: 3.10 以及以上版本.

安装方法
--------

> 新手建议使用 `pip install -U 'mootdx[all]'` 安装

### PIP 安装方法
```shell

# 包含核心依赖安装
pip install 'mootdx'

# 包含命令行依赖安装, 如果使用命令行工具可以使用这种方式安装
pip install 'mootdx[cli]'

# 包含所有扩展依赖安装, 如果不清楚各种依赖关系就用这个命令
pip install 'mootdx[all]'
```

### 升级安装

```shell
# 公共 PyPI 上游版本
python -m pip install -U tdxpy mootdx
```

> 如果不清楚各种依赖关系就用这个命令 `pip install -U 'mootdx[all]'`

> 本 fork 的沪深北三市场股票列表与批量财务接口需要配套
> [`xungeer/tdxpy` v0.3.0](https://github.com/xungeer/tdxpy/tree/v0.3.0)。
> 上面的 PyPI 命令不会安装本 fork。通过源码部署时应按标签先安装配套 tdxpy，
> 再安装本仓库对应版本，具体命令见[安装文档](docs/setup.md)。这两个 fork
> 未发布到公共 PyPI；私有 wheelhouse 应先安装锁定的运行依赖和 tdxpy wheel，
> 再以 `--no-deps` 安装 mootdx wheel，避免安装器重新解析私有依赖来源。

使用说明
--------

> 以下只列举一些例子, 详细说明请查看在线文档: <https://www.mootdx.com>

通达信离线数据读取

```python
from mootdx.reader import Reader

# market 参数 std 为标准市场(就是股票), ext 为扩展市场(期货，黄金等)
# tdxdir 是通达信的数据目录, 根据自己的情况修改

reader = Reader.factory(market='std', tdxdir='C:/new_tdx')

# 读取日线数据
reader.daily(symbol='600036')

# 读取分钟数据
reader.minute(symbol='600036')

# 读取时间线数据
reader.fzline(symbol='600036')
```

通达信线上行情读取

```python
from mootdx.quotes import Quotes

# 标准市场
client = Quotes.factory(market='std', multithread=True, heartbeat=True)

# k 线数据
client.bars(symbol='600036', frequency=9, offset=10)

# 通达信服务端前复权/后复权 K 线，不请求外部复权因子
client.adjusted_bars(symbol='600036', frequency=9, offset=10, adjust='qfq')
client.adjusted_bars(symbol='600036', frequency=9, offset=10, adjust='hfq')

# 固定周期支持 1m/5m/15m/30m/1h/day/week/mon/3mon/year；也支持扩展周期
client.adjusted_bars(symbol='600036', frequency='10m', offset=1000, adjust='qfq')
client.adjusted_bars(symbol='600036', frequency='2d', offset=1000, adjust='qfq')
client.adjusted_bars(symbol='600036', frequency='5s', offset=1000, adjust='none')

# 以指定日期为锚点的定点前复权
client.adjusted_bars(
    symbol='600036',
    frequency=9,
    offset=10,
    adjust='fixed_qfq',
    anchor_date='2024-06-03',
)

# 指数
client.index(symbol='000001', frequency=9)

# 分钟
client.minute(symbol='000001')

# 查询沪、深、北市场证券列表
from mootdx import consts

sh_stocks = client.stocks(market=consts.MARKET_SH)
sz_stocks = client.stocks(market=consts.MARKET_SZ)
bj_stocks = client.stocks(market=consts.MARKET_BJ)

# 查询沪、深、北市场的通达信行业分类码
industry_codes = client.industry_codes()
```

`adjusted_bars()` 直接使用通达信 `0x052d` 的复权参数，不请求外部复权因子。
主站单次稳定返回最多 800 条，接口会对更大的 `offset` 自动分页；实际历史深度
取决于证券、周期和所连接主站的留存范围，并受 16 位 `start` 字段约束。

通达信财务数据读取

```python
from mootdx.affair import Affair

# 远程文件列表
files = Affair.files()

# 下载单个
Affair.fetch(downdir='tmp', filename='gpcw19960630.zip')

# 下载全部
Affair.parse(downdir='tmp')
```

源码开发与测试
------------

推荐使用 uv 0.11.17 或更高版本在项目根目录创建独立、可复现的开发测试环境。
`uv.lock` 已锁定运行依赖、默认测试依赖（包括 `freezegun`），以及 `xungeer/tdxpy` 的
`v0.3.0` 标签与实际提交：

```shell
uv sync --locked
uv run --locked pytest
```

仓库通过 `.python-version` 固定日常开发基线为 Python 3.12；发布包要求
Python 3.10 及以上版本，多版本兼容性由测试矩阵覆盖。

`tdxpy` 与 Poetry 原配置一样通过 GitHub SSH 获取；首次使用前需确保当前机器
可以访问 `git@github.com`。修改依赖时，应同时维护标准 `[project]` / uv 配置和
`[tool.poetry]` 配置，并分别更新 `uv.lock` 与 `poetry.lock`，避免两套环境漂移。

原 Poetry 1.7 发布与测试流程继续保留。测试依赖属于 Poetry 的 `test` 依赖组：

```shell
poetry install --sync --with test
poetry run pytest
```

不使用 Poetry 时，可以安装项目和测试两份依赖清单：

```shell
python -m pip install -r requirements.txt -r tests/requirements.txt
python -m pytest
```

加微信交流
----------

![](docs/img/IMG_2851.JPG)

常见问题
--------

M1 mac 系统PyMiniRacer不能使用，访问:
<https://github.com/sqreen/PyMiniRacer/issues/143>


## Stargazers over time

[![Stargazers over time](https://starchart.cc/mootdx/mootdx.svg)](https://starchart.cc/mootdx/mootdx)
