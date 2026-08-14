# 短线机会工作台 V3.3 宽屏资金交易台版

## 这版改动

1. 总览“今日机会速览”整行填满
   - 不再只占左半边
   - 交易卡片横向展开
   - 买点、止损、目标、仓位、胜率、资金信息更完整

2. 资金流向总览整块展示
   - 板块资金流入/流出
   - 主力资金个股
   - 和 V3.2 一样合并展示，但总览里也铺满

3. 数据源方案说明加入“数据状态”
   - 免费稳定版
   - 服务器增强版
   - 专业行情版

## 关于数据源速度

当前 GitHub Pages + GitHub Actions 架构：
- 免费
- 易部署
- 但是模型扫描会延迟，通常 5~15 分钟
- 板块资金和实时行情依赖前端公开接口，有时会抽风

真正更快：
1. 云服务器常驻程序：30~60 秒扫描全市场
2. 专业行情接口：同花顺 iFinD / Wind / Choice / 券商 Level-2
3. 如果要主力资金、超大单、大单更准，必须上专业源

## 上传
覆盖：
- index.html
- scanner.py

建议覆盖：
- .github/workflows/scan.yml

可选：
- data/symbols.json

不要手动覆盖：
- data/latest.json

上传后运行：
Actions → Refresh market scan → Run workflow
