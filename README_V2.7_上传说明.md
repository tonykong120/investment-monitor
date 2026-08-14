# V2.7 完整修复版

这版补齐了刚才缺失的核心文件。

## 上传到 GitHub 时覆盖

必须覆盖：
- index.html
- scanner.py

建议一起覆盖：
- .github/workflows/scan.yml

可选：
- data/symbols.json

不要手动覆盖：
- data/latest.json

## 这版重点

- 顶部新增“实时模型层”
- 实时行情约 10 秒更新
- 页面上已有股票 / 自选股票会用实时行情重算短线分
- 后台全市场模型仍然依赖 GitHub Actions，所以全市场深度扫描不是秒级

盘中主要看：
- 实时模型时间
- 实时短线分
- 1分钟 / 3分钟涨跌
- 5分钟成交额增量
- 买点区 / 不追线
