## 扩展行情接口

扩展市场接口用于获取期货、港股通、基金等非A股市场的行情数据。

### 快速入门

```python
from mootdx.quotes import Quotes

# 方式一：使用工厂方法创建扩展市场连接（推荐）
client = Quotes.factory(market='ext')

# 方式二：直接使用 ExtQuotes 类
from mootdx.quotes import ExtQuotes
client = ExtQuotes()

# 获取市场列表
print(client.markets())

# 获取期货K线数据（上海期货 market=30, 沪铜主力 CUL8）
df = client.bars(frequency=9, market=30, symbol='CUL8', offset=10)
print(df)

# 获取港股通K线数据（market=71, 腾讯 00700）
df = client.bars(frequency=9, market=71, symbol='00700', offset=10)
print(df)
```

### 连接参数

```python
from mootdx.quotes import Quotes

client = Quotes.factory(
    market='ext',       # 扩展市场
    bestip=True,        # 自动选择最快服务器
    timeout=15,         # 超时时间（秒）
)
```

**支持的市场类型包括：**

| 市场ID | 名称 | 简称 | 说明 |
|:-------:|:------|:-----:|:-----|
| 1 | 临时股 | TP | - |
| 7 | 中金所期权 | OJ | - |
| 8 | 个股期权 | QQ | - |
| 9 | 深圳期权 | SQ | - |
| 27 | 香港指数 | FH | - |
| 28 | 郑州商品 | QZ | 郑商所期货 |
| 29 | 大连商品 | QD | 大商所期货 |
| 30 | 上海期货 | QS | 上期所期货 |
| 31 | 香港主板 | KH | 香港证券市场 |
| 33 | 开放式基金 | FU | - |
| 34 | 货币型基金 | FB | - |
| 35 | 银河理财产品 | LC | - |
| 37 | 全球指数(静态) | FW | - |
| 38 | 宏观指标 | HG | - |
| 40 | 中国概念股 | CH | - |
| 43 | B股转H股 | HB | - |
| 44 | 股份转让 | SB | - |
| 47 | 中金所期货 | CZ | 股指期货等 |
| 48 | 香港创业板 | KG | - |
| 49 | 香港基金 | KT | - |
| 54 | 国债预发行 | GY | - |
| 56 | 阳光私募基金 | TA | - |
| 57 | 券商集合理财 | TB | - |
| 58 | 券商货币理财 | TC | - |
| 60 | 主力期货合约 | MA | - |
| 62 | 中证指数 | ZZ | - |
| 65 | 广州套利期货 | EG | - |
| 66 | 广州期货 | QG | 广期所期货 |
| 71 | 港股通 | GH | - |
| 74 | 美国股票 | US | 美股市场 |
| 102 | 国证指数 | GZ | - |

---

## 01. 获取市场代码

可以获取该api服务器可以使用的市场列表，类别等信息

** 调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='ext')
markets = client.markets()
print(markets)

# 返回示例:
#    market      name short_name
# 0       1       临时股         TP
# 1       7     中金所期权         OJ
# ...
```

> 注意点：非股票品种代码，有些获取的价格不是实际价格，比如可转债获取价格为实际价格 x 10。
> 这是可能是TDX为了防止浮点数错误，报价在传输和存储时实际都保存为整数，然后根据品种进行处理的结果。

## 02. 查询代码列表

** 参数说明: **

- start: 起始位置.
- offset: 获取数量.

** 调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='ext')
client.instrument(start=0, offset=100)

# 获取全部
client.instruments()
```

## 03. 市场商品数量

** 调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='ext')
client.instrument_count()

```

## 04. 查询五档行情

** 参数说明: **

- market: 市场代码.
- symbol: 证券代码.

** 调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='ext')
client.quote(market=47, symbol="IF1709")

# 简写方式
client.quote(symbol="47#IF1709")
```

## 05. 查询分时行情

** 参数说明: **

- market: 市场代码. 市场代码可以通过 `markets` 方法获得
- symbol: 证券代码.

** 调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='ext')
client.minute(market=47, symbol='IF1709')

# 简写方式
client.minute(symbol="47#IF1709")
```

## 06. 历史分时行情

** 参数说明: **

- market: 市场代码. 场ID可以通过 `markets` 方法获得
- symbol: 证券代码

** 调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='ext')
client.minutes(market=47, symbol='IF1709')

# 简写方式
client.minutes(symbol="47#IF1709")
```

## 07. 查询k线数据

** 参数说明: **

- frequency: K线周期参考 `mootdx.consts`
- market: 市场代码. 市场ID可以通过 `markets` 方法获得
- symbol: 证券代码
- start: 起始位置
- offset: 数量

**K线周期常量：**

| 常量 | 值 | 说明 |
|:-----|:--:|:-----|
| KLINE_5MIN | 0 | 5分钟K线 |
| KLINE_15MIN | 1 | 15分钟K线 |
| KLINE_30MIN | 2 | 30分钟K线 |
| KLINE_1HOUR | 3 | 1小时K线 |
| KLINE_DAILY | 4 | 日K线 |
| KLINE_WEEKLY | 5 | 周K线 |
| KLINE_MONTHLY | 6 | 月K线 |
| KLINE_1MIN | 8 | 1分钟K线 |
| KLINE_RI_K | 9 | 日K线(常用) |

** 调用方法：**

```python
from mootdx.quotes import Quotes
from mootdx.consts import KLINE_DAILY

client = Quotes.factory(market='ext')

# 中金所期货 - 股指期货 (market=47)
df = client.bars(frequency=KLINE_DAILY, market=47, symbol='IFL0', start=0, offset=100)
print(df)

# 上海期货 - 沪铜主力 (market=30)
df = client.bars(frequency=9, market=30, symbol='CUL8', offset=50)
print(df)

# 港股通 - 腾讯 (market=71)
df = client.bars(frequency=9, market=71, symbol='00700', offset=50)
print(df)

# 大连商品 - 铁矿石主力 (market=29)
df = client.bars(frequency=9, market=29, symbol='IL8', offset=50)
print(df)

# 简写方式：使用 "市场ID#代码" 格式
df = client.bars(frequency=KLINE_DAILY, symbol="47#IFL0", start=0, offset=100)
print(df)
```

> **自动分页功能**: 扩展市场单次请求上限为700条，现已支持自动分页。
> 可直接请求超过700条的数据，如 `offset=2000`，接口会自动分页获取并合并结果。

```python
# 获取大量历史数据示例（自动分页）
df = client.bars(frequency=9, market=71, symbol='00700', offset=5000)
print(f'获取到 {len(df)} 条K线数据')
# 输出: 获取到 5000 条K线数据
```

## 08. 查询分笔成交

** 参数说明: **

- market: 市场代码. 场ID可以通过 `markets` 方法获得
- symbol: 证券代码

** 调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='ext')
client.transaction(31, "00020")

# 简写方式
client.transaction("31#00020")
```

注意，这个接口最多返回`1800`条记录, 如果有超过1800条记录的请求，我们有一个start 参数作为便宜量，可以取出超过1800条记录

如期货的数据：这个接口可以取出1800条之前的记录，数量也是1800条

** 调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='ext')
client.transaction(market=31, symbol='00020')

# 简写方式
client.transaction("31#00020")
```

## 09. 历史分笔成交

** 参数说明: **

- market: 市场代码. 场ID可以通过 `markets` 方法获得
- symbol: 证券代码
- date: 日期. 日期格式 YYYYMMDD 如 20170811
- start: 起始位置
- offset: 数量

** 调用方法：**

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market='ext')
client.transactions(market=47, symbol='IFL0', date='20170810', start=1800)

# 简写方式
client.transaction(symbol="47#IFL0", date='20170810', start=1800)
```
