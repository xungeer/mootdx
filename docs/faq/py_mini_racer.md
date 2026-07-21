# `mini-racer` 依赖说明

Mootdx 当前声明的依赖是 `mini-racer>=0.12.0,<0.13.0`，代码通过
`py_mini_racer.MiniRacer` 解码新浪交易日数据。正常安装 `mootdx` 时会一起安装，
不需要单独选择安装 extra。

如果导入失败，请先确认当前 Python 环境中安装的是与 Mootdx 同一环境的
`mini-racer`：

```shell
python -m pip show mini-racer
python -c "from py_mini_racer import MiniRacer; print(MiniRacer)"
```

该依赖只影响 `mootdx.utils.holiday.holidays()` / `holiday2()` 的 JavaScript 解码
路径，不影响在线行情、离线文件读取或财务文件接口。交易日工具还需要访问外部数据源，
即使导入成功也可能因网络或上游格式变化返回空结果。
