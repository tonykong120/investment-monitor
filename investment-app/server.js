const http = require("http");
const fs = require("fs");
const path = require("path");
const { TextDecoder } = require("util");

const port = Number(process.env.PORT || 4173);
const root = __dirname;
const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".webmanifest": "application/manifest+json; charset=utf-8",
  ".svg": "image/svg+xml; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
};

function sendJson(res, payload, status = 200) {
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "access-control-allow-origin": "*",
  });
  res.end(JSON.stringify(payload));
}

function sendText(res, text, status = 200, contentType = "text/plain; charset=utf-8") {
  res.writeHead(status, { "content-type": contentType });
  res.end(text);
}

async function fetchText(url, encoding = "utf-8") {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const buffer = Buffer.from(await response.arrayBuffer());
  return new TextDecoder(encoding).decode(buffer);
}

function normalizeTencentSymbol(symbol) {
  const raw = String(symbol || "").trim();
  if (!raw) return "";
  if (/^(sh|sz|hk|us)\w+/i.test(raw)) return raw;
  if (/^6|^5/.test(raw)) return `sh${raw}`;
  if (/^0|^1|^2|^3/.test(raw)) return `sz${raw}`;
  return raw;
}

function parseTencentQuoteLine(line) {
  const match = line.match(/v_([^=]+)="([^"]*)"/);
  if (!match) return null;
  const symbol = match[1];
  const fields = match[2].split("~");
  const name = fields[1] || symbol;
  const price = Number(fields[3]);
  const previousClose = Number(fields[4]);
  const high = Number(fields[33]);
  const low = Number(fields[34]);
  const changePercent = Number(fields[32]);

  if (!Number.isFinite(price)) return null;
  return {
    symbol,
    code: symbol.replace(/^(sh|sz)/, ""),
    name,
    price,
    previousClose,
    high,
    low,
    changePercent: Number.isFinite(changePercent)
      ? changePercent
      : previousClose
        ? ((price - previousClose) / previousClose) * 100
        : 0,
    source: "腾讯行情",
  };
}

async function getTencentQuotes(symbols) {
  const normalized = symbols.map(normalizeTencentSymbol).filter(Boolean);
  if (!normalized.length) return [];
  const url = `https://qt.gtimg.cn/q=${normalized.join(",")}`;
  const text = await fetchText(url, "gb18030");
  return text
    .split(";")
    .map((line) => parseTencentQuoteLine(line))
    .filter(Boolean);
}

function parseFundJsonp(text) {
  const match = text.match(/jsonpgz\((.*)\);?/s);
  if (!match) return null;
  return JSON.parse(match[1]);
}

async function getFunds(codes) {
  const results = await Promise.all(
    codes.filter(Boolean).map(async (code) => {
      const url = `https://fundgz.1234567.com.cn/js/${encodeURIComponent(code)}.js?rt=${Date.now()}`;
      const text = await fetchText(url);
      const payload = parseFundJsonp(text);
      if (!payload) return null;
      return {
        code,
        name: payload.name,
        nav: Number(payload.dwjz),
        estimate: Number(payload.gsz),
        changePercent: Number(payload.gszzl),
        date: payload.jzrq,
        source: "天天基金",
      };
    })
  );
  return results.filter(Boolean);
}

async function getGoldFx() {
  const [goldResponse, fxResponse] = await Promise.all([
    fetch("https://api.gold-api.com/price/XAU"),
    fetch("https://api.frankfurter.app/latest?from=USD&to=CNY"),
  ]);
  const gold = await goldResponse.json();
  const fx = await fxResponse.json();
  const priceUsdOz = Number(gold.price);
  const usdCny = Number(fx.rates?.CNY);
  return {
    gold: {
      priceUsdOz,
      changePercent: Number(gold.changePercent ?? gold.change ?? 0),
      timestamp: gold.timestamp || fx.date,
      priceCnyGram: Number.isFinite(priceUsdOz) && Number.isFinite(usdCny) ? (priceUsdOz * usdCny) / 31.1035 : null,
    },
    fx: {
      usdCny,
      date: fx.date,
    },
  };
}

async function getNews(keywords) {
  const upstream = process.env.NEWS_API_URL;
  const apiKey = process.env.NEWS_API_KEY;

  if (upstream) {
    const url = new URL(upstream);
    if (keywords.length) url.searchParams.set("q", keywords.join(" "));
    const headers = apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
    const response = await fetch(url, { headers });
    if (!response.ok) throw new Error(`NEWS HTTP ${response.status}`);
    const payload = await response.json();
    const items = Array.isArray(payload) ? payload : payload.data || payload.news || payload.articles || [];
    return items.slice(0, 8).map((item) => ({
      title: item.title || item.headline || "未命名新闻",
      summary: item.summary || item.description || item.content || "",
      source: item.source?.name || item.source || "新闻接口",
      sentiment: Number(item.sentiment ?? item.score ?? 0),
      url: item.url || "",
    }));
  }

  const topic = keywords.length ? keywords.join("、") : "市场";
  return [
    {
      title: `${topic} 相关新闻代理已就绪`,
      summary: "当前没有配置 NEWS_API_URL，后端会先返回占位新闻。配置上游新闻接口后，这里会返回真实新闻。",
      source: "本地新闻代理",
      sentiment: 0,
      url: "",
    },
  ];
}

function serveStatic(req, res, pathname) {
  const safePath = pathname === "/" ? "/index.html" : pathname;
  const filePath = path.resolve(root, safePath.replace(/^\/+/, ""));
  if (!filePath.startsWith(root)) {
    sendText(res, "Forbidden", 403);
    return;
  }

  fs.readFile(filePath, (error, data) => {
    if (error) {
      fs.readFile(path.join(root, "index.html"), (fallbackError, fallback) => {
        if (fallbackError) sendText(res, "Not found", 404);
        else sendText(res, fallback, 200, "text/html; charset=utf-8");
      });
      return;
    }
    sendText(res, data, 200, mimeTypes[path.extname(filePath)] || "application/octet-stream");
  });
}

async function routeApi(req, res, url) {
  try {
    if (url.pathname === "/api/quotes") {
      const symbols = (url.searchParams.get("symbols") || "").split(",").map((item) => item.trim());
      sendJson(res, { data: await getTencentQuotes(symbols) });
      return;
    }

    if (url.pathname === "/api/funds") {
      const symbols = (url.searchParams.get("symbols") || "").split(",").map((item) => item.trim());
      sendJson(res, { data: await getFunds(symbols) });
      return;
    }

    if (url.pathname === "/api/gold-fx") {
      sendJson(res, await getGoldFx());
      return;
    }

    if (url.pathname === "/api/news") {
      const keywords = (url.searchParams.get("keywords") || url.searchParams.get("symbols") || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      sendJson(res, { data: await getNews(keywords) });
      return;
    }

    sendJson(res, { error: "Unknown API endpoint" }, 404);
  } catch (error) {
    sendJson(res, { error: error.message }, 502);
  }
}

http
  .createServer((req, res) => {
    const url = new URL(req.url, `http://127.0.0.1:${port}`);
    if (url.pathname.startsWith("/api/")) {
      routeApi(req, res, url);
      return;
    }
    serveStatic(req, res, url.pathname);
  })
  .listen(port, () => {
    console.log(`Investment monitor running at http://127.0.0.1:${port}`);
  });
