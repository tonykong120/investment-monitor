export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const cors = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Access-Control-Allow-Headers": "Authorization, Content-Type",
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: cors });
    }

    try {
      if (url.pathname === "/api/gold-fx") {
        const [goldResponse, fxResponse] = await Promise.all([
          fetch("https://api.gold-api.com/price/XAU"),
          fetch("https://api.frankfurter.app/latest?from=USD&to=CNY"),
        ]);
        const gold = await goldResponse.json();
        const fx = await fxResponse.json();
        const priceUsdOz = Number(gold.price);
        const usdCny = Number(fx.rates?.CNY);
        return json(
          {
            gold: {
              priceUsdOz,
              changePercent: Number(gold.changePercent ?? gold.change ?? 0),
              timestamp: gold.timestamp || fx.date,
              priceCnyGram:
                Number.isFinite(priceUsdOz) && Number.isFinite(usdCny)
                  ? (priceUsdOz * usdCny) / 31.1035
                  : null,
            },
            fx: { usdCny, date: fx.date },
          },
          cors
        );
      }

      if (url.pathname === "/api/news") {
        const upstream = env.NEWS_API_URL;
        const key = env.NEWS_API_KEY;
        if (!upstream) {
          return json(
            {
              data: [
                {
                  title: "新闻代理已部署，等待配置真实新闻源",
                  summary: "在 Cloudflare Worker 环境变量里配置 NEWS_API_URL 和 NEWS_API_KEY 后即可返回真实新闻。",
                  source: "Cloudflare Worker",
                  sentiment: 0,
                },
              ],
            },
            cors
          );
        }

        const target = new URL(upstream);
        const keywords = url.searchParams.get("keywords") || url.searchParams.get("symbols") || "";
        if (keywords) target.searchParams.set("q", keywords);
        const response = await fetch(target, {
          headers: key ? { Authorization: `Bearer ${key}` } : {},
        });
        const payload = await response.json();
        const items = Array.isArray(payload) ? payload : payload.data || payload.news || payload.articles || [];
        return json(
          {
            data: items.slice(0, 8).map((item) => ({
              title: item.title || item.headline || "未命名新闻",
              summary: item.summary || item.description || item.content || "",
              source: item.source?.name || item.source || "新闻接口",
              sentiment: Number(item.sentiment ?? item.score ?? 0),
              url: item.url || "",
            })),
          },
          cors
        );
      }

      return json({ error: "Unknown endpoint" }, cors, 404);
    } catch (error) {
      return json({ error: error.message }, cors, 502);
    }
  },
};

function json(payload, headers, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { ...headers, "Content-Type": "application/json; charset=utf-8" },
  });
}
