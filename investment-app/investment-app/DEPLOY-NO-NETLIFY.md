# 不用 Netlify 的发布方式

Netlify Drop 出现 daily limit 时，可以改用 GitHub Pages 或 Cloudflare Pages。

## 方案 A：GitHub Pages

适合先把 App 安装到手机。缺点是 GitHub Pages 只能托管静态页面，不能运行 `server.js` 后端代理。

步骤：

1. 登录 https://github.com
2. 新建一个仓库，例如 `investment-monitor`
3. 上传 `investment-app` 文件夹里的所有文件到仓库根目录
4. 进入仓库 `Settings`
5. 点击 `Pages`
6. Source 选择 `Deploy from a branch`
7. Branch 选择 `main`，目录选 `/root`
8. 保存
9. 等 1-3 分钟，GitHub 会给出一个 `https://你的用户名.github.io/investment-monitor/` 地址
10. 用手机浏览器打开这个地址并添加到主屏幕

## 方案 B：Cloudflare Pages

适合继续用静态 App，并且后续可以配合 Cloudflare Worker 代理真实数据。

步骤：

1. 登录 https://dash.cloudflare.com
2. 进入 `Workers & Pages`
3. 选择 `Pages`
4. 创建项目
5. 上传 `investment-app` 文件夹
6. 部署完成后，用手机打开 Cloudflare 给你的 HTTPS 地址
7. 添加到主屏幕

## 后端代理

`server.js` 是 Node 后端代理，适合部署在 Render、Railway、Zeabur、自己的服务器等能运行 Node 的平台。

`cloudflare-worker.js` 是 Cloudflare Worker 代理，适合部署到 Cloudflare Workers。

如果只是先安装到手机，可以先不用代理。后面再把新闻、行情、基金净值的真实接口逐步接上。
