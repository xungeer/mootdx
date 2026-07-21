# 第三方声明

Mootdx 的通达信协议层位于 `mootdx/_protocol/`，已经随源码和构建产物一起发布。
使用行情、财务和服务端复权接口时，无需另行安装 `tdxpy`，也不需要 GitHub SSH
权限。

## 来源与修改关系

内置协议层包含由以下项目演进而来的源码：

- `tdxpy` 0.2.7，公开发布于
  [PyPI](https://pypi.org/project/tdxpy/0.2.7/)；
- `xungeer/tdxpy` v0.3.0，提交
  `c8390abd02d3ff8df743302b0cd9b613607bd1f0`，在公开版本基础上增加沪、深、北
  三市场支持及服务端复权协议等改动。

公开的 `tdxpy` 0.2.7 源码采用 MIT License。Mootdx 对其修改、融合和再分发时保留
原始版权与许可声明，后续修改的版权归各自贡献者所有。随发行包提供的权威声明见
仓库根目录的
[THIRD_PARTY_NOTICES.md](https://github.com/xungeer/mootdx/blob/master/THIRD_PARTY_NOTICES.md)。

## tdxpy — MIT License

Copyright (c) 2022, tdxpy

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
