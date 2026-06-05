# 我的投资监控台

这是一个可安装到手机主屏幕的 PWA 版本。部署到 HTTPS 网站后，可以像 App 一样打开。

## 最快部署方式：Netlify

1. 打开 https://app.netlify.com/drop
2. 登录或注册 Netlify。
3. 把整个 `investment-app` 文件夹拖进去。
4. Netlify 会生成一个 `https://...netlify.app` 地址。
5. 用手机浏览器打开这个地址。

## iPhone 安装

1. 用 Safari 打开部署后的 HTTPS 地址。
2. 点底部分享按钮。
3. 选择“添加到主屏幕”。
4. 点“添加”。

## Android 安装

1. 用 Chrome 打开部署后的 HTTPS 地址。
2. 点右上角菜单。
3. 选择“安装应用”或“添加到主屏幕”。
4. 确认安装。

## 数据源

进入页面底部“数据源设置”，可以填写：

- 行情接口 URL
- 基金净值接口 URL
- 新闻接口 URL
- 情绪接口 URL
- API Key

接口暂时为空时，页面会自动使用模拟数据，方便先试用。

## 已按 API-REFERENCE.md 接入

- 黄金实时价格：`https://api.gold-api.com/price/XAU`
- 美元人民币汇率：`https://api.frankfurter.app/latest?from=USD&to=CNY`
- 天天基金实时估值：`https://fundgz.1234567.com.cn/js/{基金代码}.js`
- 溢价计算：`(场内价格 - 估算净值) / 估算净值 * 100%`

腾讯 A 股/ETF 行情 `https://qt.gtimg.cn/...` 返回 GBK 文本，浏览器端容易受跨域和编码限制。更稳定的接法是加一个后端代理，把 GBK 转成 UTF-8 JSON 后给前端使用。

## 本地预览

如果你想在电脑浏览器用 HTTP 预览，可以在当前目录运行：

```powershell
python -m http.server 4173
```

然后打开：

```text
http://localhost:4173/
```

手机安装通常需要 HTTPS 地址，本地 `file://` 打开不能安装成 PWA。

## 后端代理模式

新版提供 `server.js`，可以解决跨域、GBK 编码、JSONP 转 JSON 和新闻统一入口。

在当前目录运行：

```powershell
node server.js
```

然后打开：

```text
http://127.0.0.1:4173/
```

可用接口：

- `/api/quotes?symbols=159696,513650`
- `/api/funds?symbols=513650,510300`
- `/api/gold-fx`
- `/api/news?keywords=黄金,ETF`

新闻真实上游可通过环境变量配置：

```powershell
$env:NEWS_API_URL="https://your-news-api.example.com/news"
$env:NEWS_API_KEY="your-key"
node server.js
```

如果没有配置新闻上游，`/api/news` 会返回占位新闻，说明代理已就绪但还没有真实新闻源。
