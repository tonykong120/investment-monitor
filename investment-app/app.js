const storageKey = "personal-investment-monitor-v2";

const defaultState = {
  preferences: {
    riskPreference: "balanced",
    maxSinglePosition: 25,
    targetCash: 15,
    themePreference: "quality",
  },
  settings: {
    refreshInterval: 30,
    marketMode: "demo",
    dropAlert: 3,
    riseAlert: 4,
    autoRefresh: true,
    quoteEndpoint: "",
    fundEndpoint: "",
    newsEndpoint: "",
    sentimentEndpoint: "",
    indexEndpoint: "",
    apiKey: "",
    indexSymbol: "sh000001",
    klinePeriod: "1m",
  },
  signals: {
    news: 20,
    fundamental: 35,
    policy: 10,
    sentiment: -15,
  },
  holdings: [
    { name: "沪深300ETF", code: "510300", type: "基金", value: 32000, risk: "medium", price: 4.18, change: 0.42 },
    { name: "黄金ETF", code: "518880", type: "黄金", value: 18000, risk: "low", price: 5.76, change: -0.18 },
    { name: "宁德时代", code: "300750", type: "股票", value: 12000, risk: "high", price: 197.2, change: 1.36 },
    { name: "现金", code: "", type: "现金", value: 15000, risk: "low", price: 1, change: 0 },
  ],
  feeds: {
    funds: [],
    news: [],
    klines: [],
    gold: null,
    fx: null,
    source: "demo",
  },
};

const riskWeights = {
  low: 18,
  medium: 48,
  high: 82,
};

const ideas = [
  {
    name: "沪深300ETF",
    type: "基金",
    theme: "quality",
    risk: "medium",
    base: 72,
    reason: "宽基分散，适合作为权益底仓，和均衡/稳健偏好兼容度较高。",
  },
  {
    name: "中证红利低波ETF",
    type: "基金",
    theme: "dividend",
    risk: "medium",
    base: 70,
    reason: "偏防御和现金流属性，适合在情绪偏弱时提高组合稳定性。",
  },
  {
    name: "黄金ETF",
    type: "黄金",
    theme: "gold",
    risk: "low",
    base: 64,
    reason: "可作为避险与资产分散工具，适合政策或情绪不确定阶段。",
  },
  {
    name: "科创50ETF",
    type: "基金",
    theme: "growth",
    risk: "high",
    base: 68,
    reason: "成长属性强，适合进取偏好，但需要控制单笔和整体仓位。",
  },
  {
    name: "高股息龙头股票池",
    type: "股票",
    theme: "dividend",
    risk: "medium",
    base: 66,
    reason: "强调盈利稳定和分红质量，适合用作股票候选观察池。",
  },
  {
    name: "AI算力龙头股票池",
    type: "股票",
    theme: "growth",
    risk: "high",
    base: 62,
    reason: "弹性较高，适合只在信号强、仓位轻时小比例观察。",
  },
];

const els = {
  holdingRows: document.querySelector("#holdingRows"),
  totalValue: document.querySelector("#totalValue"),
  cashRatio: document.querySelector("#cashRatio"),
  riskScore: document.querySelector("#riskScore"),
  riskLabel: document.querySelector("#riskLabel"),
  opportunityScore: document.querySelector("#opportunityScore"),
  opportunityLabel: document.querySelector("#opportunityLabel"),
  todayAction: document.querySelector("#todayAction"),
  lastUpdate: document.querySelector("#lastUpdate"),
  dataMode: document.querySelector("#dataMode"),
  signalNarrative: document.querySelector("#signalNarrative"),
  quoteGrid: document.querySelector("#quoteGrid"),
  alertList: document.querySelector("#alertList"),
  alertCount: document.querySelector("#alertCount"),
  ideaList: document.querySelector("#ideaList"),
  dailyReport: document.querySelector("#dailyReport"),
  fundList: document.querySelector("#fundList"),
  newsList: document.querySelector("#newsList"),
  fundStatus: document.querySelector("#fundStatus"),
  newsStatus: document.querySelector("#newsStatus"),
  indexSummary: document.querySelector("#indexSummary"),
  klineCanvas: document.querySelector("#klineCanvas"),
  dialog: document.querySelector("#holdingDialog"),
  toggleAutoBtn: document.querySelector("#toggleAutoBtn"),
};

let state = loadState();
let refreshTimer = null;
let latestMetrics = {};

function loadState() {
  const saved = localStorage.getItem(storageKey);
  if (!saved) return structuredClone(defaultState);

  try {
    const parsed = JSON.parse(saved);
    return {
      ...structuredClone(defaultState),
      ...parsed,
      preferences: { ...defaultState.preferences, ...parsed.preferences },
      settings: { ...defaultState.settings, ...parsed.settings },
      signals: { ...defaultState.signals, ...parsed.signals },
    };
  } catch {
    return structuredClone(defaultState);
  }
}

function saveState() {
  localStorage.setItem(storageKey, JSON.stringify(state));
}

function sameOriginApi(path) {
  if (location.protocol === "file:") return "";
  return path;
}

function getSymbols() {
  return state.holdings.filter((item) => item.type !== "现金").map((item) => item.name);
}

function getHoldingCode(item) {
  if (item.code) return String(item.code).trim();
  const match = String(item.name || "").match(/\b\d{6}\b/);
  return match ? match[0] : "";
}

async function fetchJson(endpoint, params = {}) {
  if (!endpoint) return null;

  const url = new URL(endpoint);
  Object.entries(params).forEach(([key, value]) => {
    url.searchParams.set(key, Array.isArray(value) ? value.join(",") : value);
  });

  const headers = {};
  if (state.settings.apiKey) headers.Authorization = `Bearer ${state.settings.apiKey}`;

  const response = await fetch(url.toString(), { headers });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function fetchJsonpFund(code) {
  return new Promise((resolve, reject) => {
    if (!code) {
      resolve(null);
      return;
    }

    const script = document.createElement("script");
    const previous = window.jsonpgz;
    const timeout = window.setTimeout(() => {
      cleanup();
      reject(new Error("fund jsonp timeout"));
    }, 8000);

    function cleanup() {
      window.clearTimeout(timeout);
      script.remove();
      window.jsonpgz = previous;
    }

    window.jsonpgz = (payload) => {
      cleanup();
      resolve(payload);
    };

    script.onerror = () => {
      cleanup();
      reject(new Error("fund jsonp failed"));
    };
    script.src = `https://fundgz.1234567.com.cn/js/${encodeURIComponent(code)}.js?rt=${Date.now()}`;
    document.head.appendChild(script);
  });
}

async function fetchGoldAndFx() {
  try {
    const proxyEndpoint = sameOriginApi("/api/gold-fx");
    if (proxyEndpoint) {
      const payload = await fetchJson(proxyEndpoint);
      if (payload?.gold && payload?.fx) {
        state.feeds.gold = {
          priceUsdOz: Number(payload.gold.priceUsdOz),
          change: Number(payload.gold.changePercent ?? 0),
          priceCnyGram: Number(payload.gold.priceCnyGram),
          timestamp: payload.gold.timestamp || payload.fx.date || "实时",
        };
        state.feeds.fx = { usdCny: Number(payload.fx.usdCny), date: payload.fx.date || "今日" };
        return;
      }
    }

    const [gold, fx] = await Promise.all([
      fetch("https://api.gold-api.com/price/XAU").then((response) => response.json()),
      fetch("https://api.frankfurter.app/latest?from=USD&to=CNY").then((response) => response.json()),
    ]);
    const priceUsdOz = Number(gold.price);
    const usdCny = Number(fx.rates?.CNY);
    if (Number.isFinite(priceUsdOz) && Number.isFinite(usdCny)) {
      state.feeds.gold = {
        priceUsdOz,
        change: Number(gold.changePercent ?? gold.change ?? 0),
        priceCnyGram: (priceUsdOz * usdCny) / 31.1035,
        timestamp: gold.timestamp || fx.date || "实时",
      };
      state.feeds.fx = { usdCny, date: fx.date || "今日" };
    }
  } catch {
    state.feeds.gold = state.feeds.gold || null;
    state.feeds.fx = state.feeds.fx || null;
  }
}

function normalizeQuotes(payload) {
  const items = Array.isArray(payload) ? payload : payload?.quotes || payload?.data || [];
  return items
    .map((item) => ({
      name: item.name || item.symbol || item.code,
      price: Number(item.price ?? item.latest ?? item.nav),
      change: Number(item.changePercent ?? item.change ?? item.pct ?? 0),
    }))
    .filter((item) => item.name && Number.isFinite(item.price));
}

function normalizeFunds(payload) {
  const items = Array.isArray(payload) ? payload : payload?.funds || payload?.data || [];
  return items
    .map((item) => ({
      name: item.name || item.fundName || item.symbol || item.code,
      nav: Number(item.nav ?? item.netValue ?? item.price),
      change: Number(item.changePercent ?? item.change ?? item.dayChange ?? 0),
      date: item.date || item.navDate || "今日",
    }))
    .filter((item) => item.name && Number.isFinite(item.nav));
}

function normalizeEastmoneyFund(payload, holding) {
  if (!payload) return null;
  const nav = Number(payload.dwjz);
  const estimate = Number(payload.gsz);
  const change = Number(payload.gszzl);
  const marketPrice = Number(holding.price || 0);
  const premiumBase = Number.isFinite(estimate) && estimate > 0 ? estimate : nav;
  const premium =
    Number.isFinite(marketPrice) && Number.isFinite(premiumBase) && premiumBase > 0
      ? ((marketPrice - premiumBase) / premiumBase) * 100
      : null;

  return {
    code: getHoldingCode(holding),
    name: payload.name || holding.name,
    nav,
    estimate,
    change,
    premium,
    date: payload.jzrq || "今日",
    source: "天天基金",
  };
}

function normalizeNews(payload) {
  const items = Array.isArray(payload) ? payload : payload?.news || payload?.articles || payload?.data || [];
  return items
    .map((item) => ({
      title: item.title || item.headline || "未命名消息",
      summary: item.summary || item.description || item.content || "",
      sentiment: Number(item.sentiment ?? item.score ?? 0),
      source: item.source || item.provider || "外部接口",
    }))
    .slice(0, 6);
}

function normalizeKlines(payload) {
  const items = Array.isArray(payload) ? payload : payload?.klines || payload?.candles || payload?.data || [];
  return items
    .map((item) => ({
      time: item.time || item.date || item.timestamp || "",
      open: Number(item.open ?? item.o),
      high: Number(item.high ?? item.h),
      low: Number(item.low ?? item.l),
      close: Number(item.close ?? item.c),
      volume: Number(item.volume ?? item.vol ?? 0),
    }))
    .filter((item) => [item.open, item.high, item.low, item.close].every(Number.isFinite))
    .slice(-80);
}

function getIndexName(symbol = state.settings.indexSymbol) {
  return {
    sh000001: "上证指数",
    sz399001: "深证成指",
    sz399006: "创业板指",
    sh000300: "沪深300",
    hkHSI: "恒生指数",
    usIXIC: "纳斯达克",
  }[symbol] || symbol;
}

function buildDemoKlines() {
  const symbol = state.settings.indexSymbol;
  const baseMap = {
    sh000001: 3070,
    sz399001: 9600,
    sz399006: 1890,
    sh000300: 3560,
    hkHSI: 18400,
    usIXIC: 17100,
  };
  const base = baseMap[symbol] || 3000;
  const existing = state.feeds.klines?.length ? state.feeds.klines : [];

  if (existing.length >= 20 && state.feeds.klineSymbol === symbol && state.feeds.klinePeriod === state.settings.klinePeriod) {
    const last = existing[existing.length - 1];
    const drift = (Math.random() - 0.48 + getSignalScore() / 420) * (base * 0.004);
    const open = last.close;
    const close = Math.max(1, open + drift);
    const spread = Math.abs(drift) + Math.random() * (base * 0.002);
    return [
      ...existing.slice(-79),
      {
        time: new Date().toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit" }),
        open,
        high: Math.max(open, close) + spread * 0.45,
        low: Math.min(open, close) - spread * 0.45,
        close,
        volume: Math.round(Math.random() * 90000 + 10000),
      },
    ];
  }

  const rows = [];
  let price = base;
  for (let index = 0; index < 60; index += 1) {
    const drift = (Math.random() - 0.5) * (base * 0.006);
    const open = price;
    const close = Math.max(1, open + drift);
    const spread = Math.abs(drift) + Math.random() * (base * 0.002);
    rows.push({
      time: `${index + 1}`,
      open,
      high: Math.max(open, close) + spread * 0.5,
      low: Math.min(open, close) - spread * 0.5,
      close,
      volume: Math.round(Math.random() * 90000 + 10000),
    });
    price = close;
  }
  return rows;
}

function buildDemoFunds() {
  return state.holdings
    .filter((item) => item.type === "基金" || item.type === "黄金")
    .map((item) => ({
      name: item.name,
      nav: Number(item.price || 1),
      change: Number(item.change || 0),
      date: new Date().toLocaleDateString("zh-CN"),
    }));
}

function buildDemoNews() {
  const signalScore = getSignalScore();
  const tone = signalScore >= 20 ? "偏积极" : signalScore >= -10 ? "中性" : "偏谨慎";
  return [
    {
      title: `市场情绪当前${tone}`,
      summary: "根据你手动设置的消息面、政策性和情绪滑块生成，用于试用新闻情绪模块。",
      sentiment: signalScore,
      source: "本地情绪模型",
    },
    {
      title: "组合监控建议关注政策和资金面是否同向",
      summary: "当政策信号改善但情绪仍弱时，更适合观察或小额分批，而不是一次性重仓。",
      sentiment: Math.round(signalScore * 0.7),
      source: "本地规则",
    },
  ];
}

async function updateExternalData() {
  const symbols = getSymbols();
  let source = "demo";

  await fetchGoldAndFx();

  try {
    const quotePayload = await fetchJson(state.settings.quoteEndpoint || sameOriginApi("/api/quotes"), {
      symbols: state.holdings.map((item) => getHoldingCode(item) || item.name),
    });
    const quotes = normalizeQuotes(quotePayload);
    if (quotes.length) {
      state.holdings = state.holdings.map((holding) => {
        const quote = quotes.find((item) => item.name === holding.name);
        return quote ? { ...holding, price: quote.price, change: quote.change } : holding;
      });
      source = "external";
    }
  } catch {
    source = "demo";
  }

  try {
    const fundPayload = await fetchJson(state.settings.fundEndpoint || sameOriginApi("/api/funds"), {
      symbols: state.holdings.map((item) => getHoldingCode(item)).filter(Boolean),
    });
    const funds = normalizeFunds(fundPayload);
    state.feeds.funds = funds.length ? funds : buildDemoFunds();
    if (funds.length) source = "external";
  } catch {
    const fundHoldings = state.holdings.filter((item) => item.type === "基金" || item.type === "黄金");
    const fetchedFunds = await Promise.all(
      fundHoldings.map((holding) =>
        fetchJsonpFund(getHoldingCode(holding))
          .then((payload) => normalizeEastmoneyFund(payload, holding))
          .catch(() => null)
      )
    );
    const validFunds = fetchedFunds.filter(Boolean);
    state.feeds.funds = validFunds.length ? validFunds : buildDemoFunds();
    if (validFunds.length) source = "external";
  }

  try {
    const newsPayload = await fetchJson(state.settings.newsEndpoint || sameOriginApi("/api/news"), { symbols });
    const news = normalizeNews(newsPayload);
    state.feeds.news = news.length ? news : buildDemoNews();
    if (news.length) source = "external";
  } catch {
    state.feeds.news = buildDemoNews();
  }

  try {
    const sentimentPayload = await fetchJson(state.settings.sentimentEndpoint, { symbols });
    const sentiment = Number(sentimentPayload?.sentiment ?? sentimentPayload?.score);
    if (Number.isFinite(sentiment)) {
      state.signals.sentiment = Math.max(-100, Math.min(100, Math.round(sentiment)));
      source = "external";
    }
  } catch {
    // Keep manually tuned sentiment when the external source is unavailable.
  }

  try {
    const klinePayload = await fetchJson(state.settings.indexEndpoint, {
      symbol: state.settings.indexSymbol,
      period: state.settings.klinePeriod,
    });
    const klines = normalizeKlines(klinePayload);
    state.feeds.klines = klines.length ? klines : buildDemoKlines();
    if (klines.length) source = "external";
  } catch {
    state.feeds.klines = buildDemoKlines();
  }

  state.feeds.klineSymbol = state.settings.indexSymbol;
  state.feeds.klinePeriod = state.settings.klinePeriod;

  state.feeds.source = source;
}

function currency(value) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0,
  }).format(value);
}

function totalValue() {
  return state.holdings.reduce((sum, item) => sum + Number(item.value || 0), 0);
}

function getSignalScore() {
  const { news, fundamental, policy, sentiment } = state.signals;
  return Math.round(news * 0.25 + fundamental * 0.35 + policy * 0.2 + sentiment * 0.2);
}

function getPortfolioRisk() {
  const total = totalValue() || 1;
  const weighted = state.holdings.reduce((sum, item) => {
    return sum + (Number(item.value || 0) / total) * riskWeights[item.risk];
  }, 0);
  const concentration = Math.max(...state.holdings.map((item) => Number(item.value || 0) / total), 0) * 18;
  return Math.min(100, Math.round(weighted + concentration));
}

function getCashRatio() {
  const total = totalValue() || 1;
  const cash = state.holdings
    .filter((item) => item.type === "现金")
    .reduce((sum, item) => sum + Number(item.value || 0), 0);
  return Math.round((cash / total) * 100);
}

function riskText(score) {
  if (score >= 72) return "偏高，需要控制回撤";
  if (score >= 45) return "中等，适合分批操作";
  return "较低，防守性较强";
}

function opportunityText(score) {
  if (score >= 35) return "信号较强，可关注加仓窗口";
  if (score >= 5) return "信号温和，以观察和定投为主";
  if (score >= -20) return "信号偏弱，谨慎等待确认";
  return "信号较差，优先防守和止损纪律";
}

function getAction(opportunity, risk, cashRatio, alerts) {
  const targetCash = Number(state.preferences.targetCash);
  if (alerts.some((alert) => alert.level === "danger")) return "先处理预警";
  if (risk > 74 && cashRatio < targetCash) return "降风险";
  if (opportunity > 36 && risk < 68 && cashRatio > Math.max(5, targetCash - 5)) return "分批加仓";
  if (opportunity < -20) return "防守观察";
  if (cashRatio < targetCash - 8) return "补现金";
  return "持有观察";
}

function simulateMarketTick() {
  if (state.settings.marketMode !== "demo") return;

  const signalBias = getSignalScore() / 220;
  state.holdings = state.holdings.map((item) => {
    if (item.type === "现金") return { ...item, price: 1, change: 0 };

    const riskScale = item.risk === "high" ? 1.45 : item.risk === "medium" ? 0.9 : 0.45;
    const drift = (Math.random() - 0.48 + signalBias) * riskScale;
    const nextChange = Math.max(-9.9, Math.min(9.9, Number((Number(item.change || 0) * 0.64 + drift).toFixed(2))));
    const nextPrice = Math.max(0.01, Number((Number(item.price || 10) * (1 + nextChange / 1000)).toFixed(3)));
    const nextValue = Math.max(0, Math.round(Number(item.value || 0) * (1 + nextChange / 10000)));

    return { ...item, price: nextPrice, change: nextChange, value: nextValue };
  });
}

function buildAlerts(risk, cashRatio) {
  const total = totalValue() || 1;
  const alerts = [];
  const maxPosition = Number(state.preferences.maxSinglePosition);
  const dropAlert = Number(state.settings.dropAlert);
  const riseAlert = Number(state.settings.riseAlert);

  state.holdings.forEach((item) => {
    if (item.type === "现金") return;
    const ratio = Math.round((Number(item.value || 0) / total) * 100);
    const change = Number(item.change || 0);

    if (ratio > maxPosition) {
      alerts.push({
        level: "danger",
        title: `${item.name} 仓位过重`,
        text: `当前约 ${ratio}%，超过你设置的 ${maxPosition}%。建议先评估是否需要再平衡。`,
      });
    }

    if (change <= -dropAlert) {
      alerts.push({
        level: "danger",
        title: `${item.name} 跌幅触发预警`,
        text: `当前变化 ${change}% ，先看是否由消息面或基本面变化驱动，不建议情绪化补仓。`,
      });
    }

    if (change >= riseAlert) {
      alerts.push({
        level: "good",
        title: `${item.name} 涨幅触发观察`,
        text: `当前变化 +${change}% ，可检查是否接近止盈、减仓或持有计划。`,
      });
    }
  });

  if (risk >= 72) {
    alerts.push({
      level: "warning",
      title: "组合风险偏高",
      text: `风险评分 ${risk}/100。建议优先看高风险标的、单一仓位和现金水位。`,
    });
  }

  if (cashRatio < Number(state.preferences.targetCash) - 8) {
    alerts.push({
      level: "warning",
      title: "现金水位偏低",
      text: `现金占比 ${cashRatio}%，低于你的目标 ${state.preferences.targetCash}%。遇到回撤时缓冲不足。`,
    });
  }

  return alerts.slice(0, 6);
}

function renderHoldings() {
  const total = totalValue() || 1;
  els.holdingRows.innerHTML = state.holdings
    .map((item, index) => {
      const ratio = Math.round((Number(item.value || 0) / total) * 100);
      const riskName = { low: "低", medium: "中", high: "高" }[item.risk];
      return `
        <tr>
          <td><strong>${item.name}</strong><br><small>${ratio}% · ${formatChange(item.change)}</small></td>
          <td>${getHoldingCode(item) || "--"}</td>
          <td>${item.type}</td>
          <td>${currency(item.value)}</td>
          <td>${riskName}</td>
          <td><button type="button" data-delete="${index}">删除</button></td>
        </tr>
      `;
    })
    .join("");
}

function formatChange(change) {
  const value = Number(change || 0);
  if (value > 0) return `+${value.toFixed(2)}%`;
  return `${value.toFixed(2)}%`;
}

function renderQuotes() {
  const total = totalValue() || 1;
  els.quoteGrid.innerHTML = state.holdings
    .filter((item) => item.type !== "现金")
    .map((item) => {
      const ratio = Math.round((Number(item.value || 0) / total) * 100);
      const changeClass = Number(item.change || 0) >= 0 ? "change-up" : "change-down";
      const barWidth = Math.max(6, Math.min(100, ratio));
      return `
        <article class="quote-card">
          <div class="quote-top">
            <strong>${item.name}</strong>
            <span class="${changeClass}">${formatChange(item.change)}</span>
          </div>
          <div class="quote-price">${Number(item.price || 0).toFixed(3)}</div>
          <p>${item.type} · 仓位约 ${ratio}% · 风险 ${riskTextShort(item.risk)}</p>
          <div class="mini-bar" aria-label="仓位占比"><span style="width:${barWidth}%"></span></div>
        </article>
      `;
    })
    .join("");
}

function riskTextShort(risk) {
  return { low: "低", medium: "中", high: "高" }[risk];
}

function scoreIdea(idea, opportunity, risk, cashRatio) {
  let score = idea.base + opportunity * 0.28;

  if (idea.theme === state.preferences.themePreference) score += 14;
  if (state.preferences.riskPreference === "conservative" && idea.risk === "high") score -= 24;
  if (state.preferences.riskPreference === "aggressive" && idea.risk === "high") score += 8;
  if (risk > 70 && idea.risk === "low") score += 12;
  if (risk > 70 && idea.risk === "high") score -= 18;
  if (cashRatio < Number(state.preferences.targetCash) && idea.risk === "high") score -= 10;

  return Math.max(0, Math.min(100, Math.round(score)));
}

function actionForIdea(score, idea) {
  if (score >= 78 && idea.risk !== "high") return "可分批关注";
  if (score >= 78) return "小仓位观察";
  if (score >= 62) return "加入观察";
  return "暂不操作";
}

function renderIdeas(opportunity, risk, cashRatio) {
  const heldNames = new Set(state.holdings.map((item) => item.name));
  const ranked = ideas
    .map((idea) => ({ ...idea, score: scoreIdea(idea, opportunity, risk, cashRatio) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 4);

  els.ideaList.innerHTML = ranked
    .map((idea) => {
      const alreadyHeld = heldNames.has(idea.name) ? "已持有，关注再平衡" : actionForIdea(idea.score, idea);
      return `
        <article class="idea">
          <div class="idea-top">
            <strong>${idea.name}</strong>
            <span class="action-tag">${alreadyHeld}</span>
          </div>
          <p>${idea.reason}</p>
          <p>匹配度 ${idea.score}/100 · 类型：${idea.type}</p>
        </article>
      `;
    })
    .join("");
}

function renderAlerts(alerts) {
  els.alertCount.textContent = `${alerts.length} 条`;

  if (!alerts.length) {
    els.alertList.innerHTML = `
      <article class="alert-item good">
        <strong>暂无重大预警</strong>
        <p>仓位、现金和单日波动都在你设定的边界内。继续观察信号变化即可。</p>
      </article>
    `;
    return;
  }

  els.alertList.innerHTML = alerts
    .map((alert) => `
      <article class="alert-item ${alert.level}">
        <strong>${alert.title}</strong>
        <p>${alert.text}</p>
      </article>
    `)
    .join("");
}

function renderSignals() {
  Object.entries(state.signals).forEach(([key, value]) => {
    document.querySelector(`[data-signal="${key}"]`).value = value;
    document.querySelector(`#${key}Value`).textContent = value;
  });

  const signalScore = getSignalScore();
  const tone = signalScore >= 25 ? "偏积极" : signalScore >= -10 ? "中性震荡" : "偏谨慎";
  els.signalNarrative.textContent = `当前综合信号为 ${signalScore}，市场环境判断为${tone}。当基本面与政策性同向改善时，可提高候选标的权重；若情绪明显转弱，应优先检查仓位集中度和现金水位。`;
}

function renderDailyReport(metrics, alerts) {
  const topMover = state.holdings
    .filter((item) => item.type !== "现金")
    .sort((a, b) => Math.abs(Number(b.change || 0)) - Math.abs(Number(a.change || 0)))[0];
  const alertLine = alerts.length ? `今日有 ${alerts.length} 条预警，优先处理“${alerts[0].title}”。` : "今日暂无重大预警。";

  els.dailyReport.innerHTML = `
    <p>今日组合资产 ${currency(metrics.total)}，现金占比 ${metrics.cashRatio}%，风险评分 ${metrics.risk}/100，机会评分 ${metrics.opportunity}。</p>
    <p>${alertLine}</p>
    <p>波动最大的标的是 ${topMover ? `${topMover.name}（${formatChange(topMover.change)}）` : "暂无"}。建议动作：${metrics.action}。</p>
  `;
}

function renderFeeds() {
  const usingExternal = state.feeds.source === "external";
  els.fundStatus.textContent = usingExternal ? "外部接口" : "模拟/接口兜底";
  els.newsStatus.textContent = usingExternal ? "外部接口" : "模拟/接口兜底";

  els.fundList.innerHTML = (state.feeds.funds.length ? state.feeds.funds : buildDemoFunds())
    .map((fund) => {
      const changeClass = Number(fund.change || 0) >= 0 ? "change-up" : "change-down";
      const estimate = Number.isFinite(Number(fund.estimate)) ? `估值 ${Number(fund.estimate).toFixed(4)} · ` : "";
      const premium =
        Number.isFinite(Number(fund.premium)) ? ` · 溢价 ${Number(fund.premium).toFixed(2)}%` : "";
      return `
        <article class="feed-item">
          <strong>${fund.name}</strong>
          <p>净值 ${Number(fund.nav || 0).toFixed(4)} · ${estimate}<span class="${changeClass}">${formatChange(fund.change)}</span>${premium}</p>
          <small>${fund.code || ""} ${fund.date} ${fund.source || ""}</small>
        </article>
      `;
    })
    .join("");

  const macroItems = [];
  if (state.feeds.gold) {
    macroItems.push(`
      <article class="feed-item">
        <span class="source-tag">黄金/汇率</span>
        <strong>现货黄金 ${state.feeds.gold.priceUsdOz.toFixed(2)} 美元/盎司</strong>
        <p>折合人民币 ${state.feeds.gold.priceCnyGram.toFixed(2)} 元/克 · USD/CNY ${state.feeds.fx?.usdCny?.toFixed(4) || "--"}</p>
        <small>${state.feeds.gold.timestamp}</small>
      </article>
    `);
  }

  els.newsList.innerHTML = [
    ...macroItems,
    ...(state.feeds.news.length ? state.feeds.news : buildDemoNews()).map((item) => {
      const sentimentClass = Number(item.sentiment || 0) >= 0 ? "change-up" : "change-down";
      return `
        <article class="feed-item">
          <span class="source-tag">${item.source}</span>
          <strong>${item.title}</strong>
          <p>${item.summary}</p>
          <small class="${sentimentClass}">情绪 ${Number(item.sentiment || 0)}</small>
        </article>
      `;
    }),
  ].join("");
}

function renderKlineChart() {
  const canvas = els.klineCanvas;
  if (!canvas) return;

  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(320, Math.floor(rect.width * dpr));
  canvas.height = Math.max(220, Math.floor(rect.height * dpr));

  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  const width = canvas.width / dpr;
  const height = canvas.height / dpr;
  const padding = { top: 20, right: 46, bottom: 28, left: 10 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const data = state.feeds.klines?.length ? state.feeds.klines : buildDemoKlines();

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#fbfcfb";
  ctx.fillRect(0, 0, width, height);

  if (!data.length) return;

  const highs = data.map((item) => item.high);
  const lows = data.map((item) => item.low);
  const max = Math.max(...highs);
  const min = Math.min(...lows);
  const range = max - min || 1;
  const yFor = (value) => padding.top + ((max - value) / range) * plotHeight;
  const candleGap = 3;
  const candleWidth = Math.max(3, plotWidth / data.length - candleGap);

  ctx.strokeStyle = "#e2e8e1";
  ctx.lineWidth = 1;
  ctx.font = "12px Microsoft YaHei, sans-serif";
  ctx.fillStyle = "#657065";

  for (let i = 0; i <= 4; i += 1) {
    const y = padding.top + (plotHeight / 4) * i;
    const value = max - (range / 4) * i;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(width - padding.right, y);
    ctx.stroke();
    ctx.fillText(value.toFixed(0), width - padding.right + 8, y + 4);
  }

  data.forEach((item, index) => {
    const x = padding.left + index * (plotWidth / data.length) + candleGap / 2;
    const openY = yFor(item.open);
    const closeY = yFor(item.close);
    const highY = yFor(item.high);
    const lowY = yFor(item.low);
    const rising = item.close >= item.open;
    const color = rising ? "#0b6b3b" : "#9d2c2c";

    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x + candleWidth / 2, highY);
    ctx.lineTo(x + candleWidth / 2, lowY);
    ctx.stroke();

    const bodyTop = Math.min(openY, closeY);
    const bodyHeight = Math.max(2, Math.abs(closeY - openY));
    if (rising) {
      ctx.strokeRect(x, bodyTop, candleWidth, bodyHeight);
    } else {
      ctx.fillRect(x, bodyTop, candleWidth, bodyHeight);
    }
  });

  const first = data[0];
  const last = data[data.length - 1];
  const change = ((last.close - first.close) / first.close) * 100;
  const changeClass = change >= 0 ? "change-up" : "change-down";

  els.indexSummary.innerHTML = `
    <span>${getIndexName()}</span>
    <span>周期 ${state.settings.klinePeriod}</span>
    <span>最新 ${last.close.toFixed(2)}</span>
    <span class="${changeClass}">${change >= 0 ? "+" : ""}${change.toFixed(2)}%</span>
    <span>高 ${max.toFixed(2)} / 低 ${min.toFixed(2)}</span>
  `;
}

function renderSettings() {
  [
    "refreshInterval",
    "marketMode",
    "dropAlert",
    "riseAlert",
    "quoteEndpoint",
    "fundEndpoint",
    "newsEndpoint",
    "sentimentEndpoint",
    "indexEndpoint",
    "apiKey",
    "indexSymbol",
    "klinePeriod",
  ].forEach((id) => {
    document.querySelector(`#${id}`).value = state.settings[id];
  });
  els.dataMode.textContent =
    state.settings.marketMode === "demo"
      ? "模拟行情源"
      : state.settings.marketMode === "external"
        ? "外部接口行情"
        : "手动/接口预留";
  els.toggleAutoBtn.textContent = state.settings.autoRefresh ? "暂停自动刷新" : "开启自动刷新";
}

function renderPreferences() {
  Object.entries(state.preferences).forEach(([key, value]) => {
    document.querySelector(`#${key}`).value = value;
  });
}

function computeMetrics(alerts = []) {
  const total = totalValue();
  const risk = getPortfolioRisk();
  const signalScore = getSignalScore();
  const cashRatio = getCashRatio();
  const opportunity = Math.round(signalScore - risk * 0.18 + cashRatio * 0.12);
  const action = getAction(opportunity, risk, cashRatio, alerts);
  return { total, risk, signalScore, cashRatio, opportunity, action };
}

function renderSummary(metrics) {
  els.totalValue.textContent = currency(metrics.total);
  els.cashRatio.textContent = `现金占比 ${metrics.cashRatio}%`;
  els.riskScore.textContent = `${metrics.risk}/100`;
  els.riskLabel.textContent = riskText(metrics.risk);
  els.opportunityScore.textContent = `${metrics.opportunity}`;
  els.opportunityLabel.textContent = opportunityText(metrics.opportunity);
  els.todayAction.textContent = metrics.action;
}

async function render({ tick = false } = {}) {
  await updateExternalData();
  if (tick) simulateMarketTick();

  const firstMetrics = computeMetrics();
  const alerts = buildAlerts(firstMetrics.risk, firstMetrics.cashRatio);
  const metrics = computeMetrics(alerts);
  latestMetrics = metrics;

  renderPreferences();
  renderSettings();
  renderHoldings();
  renderQuotes();
  renderSignals();
  renderSummary(metrics);
  renderAlerts(alerts);
  renderIdeas(metrics.opportunity, metrics.risk, metrics.cashRatio);
  renderFeeds();
  renderKlineChart();
  renderDailyReport(metrics, alerts);

  els.lastUpdate.textContent = new Date().toLocaleString("zh-CN", { hour12: false });
  saveState();
  scheduleRefresh();
}

function scheduleRefresh() {
  window.clearTimeout(refreshTimer);
  if (!state.settings.autoRefresh) return;

  refreshTimer = window.setTimeout(() => {
    render({ tick: true });
  }, Number(state.settings.refreshInterval) * 1000);
}

document.querySelectorAll("[data-signal]").forEach((input) => {
  input.addEventListener("input", (event) => {
    const key = event.target.dataset.signal;
    state.signals[key] = Number(event.target.value);
    render();
  });
});

["riskPreference", "maxSinglePosition", "targetCash", "themePreference"].forEach((id) => {
  document.querySelector(`#${id}`).addEventListener("change", (event) => {
    state.preferences[id] = event.target.type === "number" ? Number(event.target.value) : event.target.value;
    render();
  });
});

[
  "refreshInterval",
  "marketMode",
  "dropAlert",
  "riseAlert",
  "quoteEndpoint",
  "fundEndpoint",
  "newsEndpoint",
  "sentimentEndpoint",
  "indexEndpoint",
  "apiKey",
  "indexSymbol",
  "klinePeriod",
].forEach((id) => {
  document.querySelector(`#${id}`).addEventListener("change", (event) => {
    state.settings[id] = event.target.type === "number" ? Number(event.target.value) : event.target.value;
    if (id === "indexSymbol" || id === "klinePeriod") {
      state.feeds.klines = [];
    }
    render();
  });
});

els.holdingRows.addEventListener("click", (event) => {
  const index = event.target.dataset.delete;
  if (index === undefined) return;
  state.holdings.splice(Number(index), 1);
  render();
});

document.querySelector("#addHoldingBtn").addEventListener("click", () => {
  els.dialog.showModal();
});

document.querySelector("#cancelDialogBtn").addEventListener("click", () => {
  els.dialog.close();
});

els.dialog.addEventListener("submit", () => {
  const name = document.querySelector("#newName").value.trim();
  const value = Number(document.querySelector("#newValue").value);
  if (!name || !value) return;

  state.holdings.push({
    name,
    code: document.querySelector("#newCode").value.trim(),
    type: document.querySelector("#newType").value,
    value,
    risk: document.querySelector("#newRisk").value,
    price: Number((Math.random() * 20 + 2).toFixed(3)),
    change: Number((Math.random() * 2 - 1).toFixed(2)),
  });

  document.querySelector("#newName").value = "";
  document.querySelector("#newCode").value = "";
  document.querySelector("#newValue").value = "";
  render();
});

document.querySelector("#refreshBtn").addEventListener("click", () => render({ tick: true }));
document.querySelector("#rebuildIdeasBtn").addEventListener("click", render);

els.toggleAutoBtn.addEventListener("click", () => {
  state.settings.autoRefresh = !state.settings.autoRefresh;
  render();
});

document.querySelector("#copyReportBtn").addEventListener("click", async () => {
  const text = els.dailyReport.textContent.trim().replace(/\s+/g, " ");
  try {
    await navigator.clipboard.writeText(text);
    document.querySelector("#copyReportBtn").textContent = "已复制";
    window.setTimeout(() => {
      document.querySelector("#copyReportBtn").textContent = "复制摘要";
    }, 1200);
  } catch {
    alert(text);
  }
});

render({ tick: true });

window.addEventListener("resize", () => renderKlineChart());

if ("serviceWorker" in navigator && location.protocol !== "file:") {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
