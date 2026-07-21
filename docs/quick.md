# 快速上手

完成[安装](setup.md)后，可以直接请求标准市场日线。下面的示例需要能够访问通达信
行情服务器。

## 获取最近 10 条日线

```python
from mootdx.quotes import Quotes

client = Quotes.factory(market="std")
try:
    data = client.bars(
        symbol="600036",
        frequency="day",
        start=0,
        offset=10,
    )
    print(data)
finally:
    client.close()
```

`bars()` 返回 `pandas.DataFrame`。实际返回数量和时间范围取决于证券、周期及所连接
服务器的历史留存；连接或请求失败时的统一处理方式见
[API 使用约定](api/conventions.md)。

## 下一步

- 获取前复权、后复权或定点复权 K 线：[标准行情 API](api/quote1.md)
- 获取期货、港股等扩展行情：[扩展行情 API](api/quote2.md)
- 读取通达信本地文件：[本地数据 API](api/reader.md)
- 下载并解析专业财务文件：[财务数据 API](api/affair.md)
- 使用命令行完成同类任务：[命令行工具](cli/index.md)
