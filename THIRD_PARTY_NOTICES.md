# Third-Party Notices

Mootdx v0.13.0 内置的通达信协议层包含由以下项目演进而来的源码：

- `tdxpy` 0.2.7，公开发布于 PyPI：<https://pypi.org/project/tdxpy/0.2.7/>
- `xungeer/tdxpy` v0.3.0，提交
  `c8390abd02d3ff8df743302b0cd9b613607bd1f0`，在公开版本基础上增加了沪、深、北
  三市场支持及服务端复权协议等改动

公开的 `tdxpy` 0.2.7 源码以 MIT License 发布。Mootdx 对其进行修改、融合和再分发时，
保留以下原始版权与许可声明。后续修改的版权归各自贡献者所有。

协议内收后，握手、报文边界和连接生命周期修复由 Mootdx 统一维护。原始来源版本用于追溯，不表示运行时仍依赖独立的 tdxpy 包。

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
