# 短线机会工作台 V1.3

新增：
- 600105 永鼎股份、000021 深科技固定自选监控
- BaoStock 股票池/日K + 新浪实时行情 + 腾讯实时行情 fallback
- 东方财富资金流仅作为可选增强；失败不影响扫描
- 信号理由、风险提示、量比、盈亏比
- 数据源健康状态
- 浏览器本地交易记录
- 股票池异常时拒绝覆盖旧数据

## 覆盖文件
- `index.html`
- `scanner.py`
- `.github/workflows/scan.yml`

`data/latest.json` 只有首次安装时需要；如果你已有正常数据，可以不覆盖。

完成后：`Actions → Refresh market scan → Run workflow`
