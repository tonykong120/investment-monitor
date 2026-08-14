# V2.13 自由布局 + 后台模型修复版

## 解决的问题

### 1. 总览拖拽更自由
每个总览模块现在支持：
- 拖动排序
- 短
- 中
- 长
- 整行
- 折叠 / 展开

布局会保存到浏览器 localStorage，下次打开保持你的设置。

### 2. 修复“后台模型读取失败”
页面读取 latest.json 时会依次尝试：
1. ./data/latest.json
2. data/latest.json
3. /investment-monitor/data/latest.json
4. GitHub raw 备用源

如果仍失败，会显示具体失败原因，而不是只显示“读取失败”。

### 3. 后台模型状态更清楚
如果模型太久没更新，会显示：
- 几分钟前
- 偏慢
- 过慢，盘中看实时雷达

## 重要说明
GitHub Actions 无法做到秒级全市场模型更新。V2.13 解决的是：
- 读取失败的容错
- 页面前端实时层可用
- 后台模型状态提示更清楚

真正全市场实时模型需要服务器常驻版。

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
