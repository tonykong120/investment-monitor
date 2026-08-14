# V2.14 数据源稳定修复版

## 这版主要修复

1. 页面脚本重构为单脚本版本
   - 不再多版本补丁叠加
   - 避免“数据读到了，但某个模块报错导致后台模型显示读取失败”

2. 后台模型读取更稳
   - 依次尝试：
     - ./data/latest.json
     - data/latest.json
     - /investment-monitor/data/latest.json
     - GitHub raw 备用源

3. 加入本地缓存兜底
   - 只要成功读到过一次 latest.json，就保存到浏览器本地缓存
   - 后续接口短暂失败时，页面用缓存继续显示，不会整页空掉

4. 渲染容错
   - 每个模块独立渲染
   - 一个模块失败，不影响其他模块

5. 板块资金仍然前端单独拉取
   - 接口失败时用后台 sector_flow 或上次可用数据

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

上传后执行：
Actions → Refresh market scan → Run workflow
