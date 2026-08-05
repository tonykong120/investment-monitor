import json, math, time, statistics, re
from pathlib import Path
from datetime import datetime, timedelta, timezone
import requests
import baostock as bs

CN = timezone(timedelta(hours=8))
WATCHLIST = ["600105", "000021"]  # 默认自选；网页端还可本地自由添加/删除
S = requests.Session()
S.headers.update({
    "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Accept":"*/*",
})

def clamp(x,a=0,b=100): return max(a,min(b,x))
def mean(xs):
    xs=[x for x in xs if isinstance(x,(int,float)) and math.isfinite(x)]
    return sum(xs)/len(xs) if xs else 0
def median(xs):
    xs=[x for x in xs if isinstance(x,(int,float)) and math.isfinite(x)]
    return statistics.median(xs) if xs else 0
def code_only(bs_code): return bs_code.split(".")[-1]

def allowed(bs_code, name=""):
    c=code_only(bs_code)
    if c.startswith(("688","300","301","8","4")): return False
    if "ST" in str(name) or "退" in str(name): return False
    return c.startswith(("600","601","603","605","000","001","002","003"))

def get_universe():
    for back in range(10):
        day=(datetime.now(CN)-timedelta(days=back)).strftime("%Y-%m-%d")
        rs=bs.query_all_stock(day=day)
        rows=[]
        while rs.error_code=="0" and rs.next():
            d=rs.get_row_data()
            if len(d)>=2 and allowed(d[0],d[1]):
                rows.append({"bs_code":d[0],"code":code_only(d[0]),"name":d[1]})
        if len(rows)>2000: return rows
    raise RuntimeError("BaoStock 未取得有效A股股票池")

def parse_sina(text):
    out={}
    for line in text.splitlines():
        m=re.search(r'var hq_str_(s[hz]\d{6})="(.*)";',line)
        if not m: continue
        sym,body=m.group(1),m.group(2); a=body.split(",")
        if len(a)<10 or not a[0]: continue
        try:
            name=a[0]; openp=float(a[1] or 0); prev=float(a[2] or 0); cur=float(a[3] or 0)
            high=float(a[4] or 0); low=float(a[5] or 0); vol=float(a[8] or 0); amt=float(a[9] or 0)
            if cur<=0 or prev<=0: continue
            out[sym[2:]]={"name":name,"price":cur,"pct":(cur-prev)/prev*100,"open":openp,
                          "high":high,"low":low,"volume":vol,"amount":amt,"quote_source":"新浪"}
        except: pass
    return out

def fetch_sina(symbols):
    result={}
    for i in range(0,len(symbols),150):
        q=[("sh" if c.startswith("6") else "sz")+c for c in symbols[i:i+150]]
        try:
            r=S.get("https://hq.sinajs.cn/list="+",".join(q),headers={"Referer":"https://finance.sina.com.cn/"},timeout=20)
            r.raise_for_status(); r.encoding="gbk"; result.update(parse_sina(r.text))
        except: pass
        time.sleep(.1)
    return result

def fetch_tencent(symbols):
    result={}
    for i in range(0,len(symbols),120):
        q=[("sh" if c.startswith("6") else "sz")+c for c in symbols[i:i+120]]
        try:
            r=S.get("https://qt.gtimg.cn/q="+",".join(q),headers={"Referer":"https://gu.qq.com/"},timeout=20)
            r.raise_for_status(); r.encoding="gbk"
            for line in r.text.split(";"):
                m=re.search(r'v_(s[hz]\d{6})="(.*)"',line)
                if not m: continue
                sym,body=m.group(1),m.group(2); a=body.split("~")
                if len(a)<38: continue
                try:
                    name=a[1]; cur=float(a[3]); prev=float(a[4]); openp=float(a[5])
                    vol=float(a[6] or 0)*100; high=float(a[33] or cur); low=float(a[34] or cur); amt=float(a[37] or 0)*10000
                    if cur<=0 or prev<=0: continue
                    result[sym[2:]]={"name":name,"price":cur,"pct":(cur-prev)/prev*100,"open":openp,
                                    "high":high,"low":low,"volume":vol,"amount":amt,"quote_source":"腾讯"}
                except: pass
        except: pass
        time.sleep(.1)
    return result

def fetch_quotes(universe):
    symbols=[x["code"] for x in universe]
    sina=fetch_sina(symbols)
    missing=[c for c in symbols if c not in sina]
    tencent=fetch_tencent(missing) if missing else {}
    merged={**tencent,**sina}; name_map={x["code"]:x["name"] for x in universe}; quotes=[]
    for c,q in merged.items():
        q["code"]=c; q["bs_code"]=("sh."+c if c.startswith("6") else "sz."+c); q["name"]=q.get("name") or name_map.get(c,c); quotes.append(q)
    return quotes,{"sina_count":len(sina),"tencent_fallback_count":len(tencent),"merged_count":len(merged)}

def history(bs_code, days=220):
    fields="date,open,high,low,close,volume,amount,turn,pctChg"
    start=(datetime.now(CN)-timedelta(days=days)).strftime("%Y-%m-%d")
    rs=bs.query_history_k_data_plus(bs_code,fields,start_date=start,end_date=datetime.now(CN).strftime("%Y-%m-%d"),frequency="d",adjustflag="2")
    arr=[]
    while rs.error_code=="0" and rs.next():
        a=rs.get_row_data()
        try: arr.append({"date":a[0],"o":float(a[1]),"h":float(a[2]),"l":float(a[3]),"c":float(a[4]),"v":float(a[5]),"amount":float(a[6]),"turn":float(a[7] or 0),"pct":float(a[8] or 0)})
        except: pass
    return arr[-180:]

def enrich_today(h,q):
    today=datetime.now(CN).strftime("%Y-%m-%d")
    bar={"date":today,"o":q["open"] or q["price"],"h":q["high"] or q["price"],"l":q["low"] or q["price"],"c":q["price"],"v":q["volume"],"amount":q["amount"],"turn":0,"pct":q["pct"]}
    if h and h[-1]["date"]==today: h[-1]=bar
    else: h.append(bar)
    return h

def technical(h):
    if len(h)<20:
        return {"trend":50,"volume":50,"position":50,"trigger":None,"support":None,"vr":1,
                "ma5":None,"ma10":None,"ma20":None,"reasons":[],"warnings":["历史数据不足"]}
    c=[x["c"] for x in h]; v=[x["v"] for x in h]; last=c[-1]
    ma5=mean(c[-5:]); ma10=mean(c[-10:]); ma20=mean(c[-20:])
    trend=50+(12 if last>ma5 else -8)+(9 if ma5>ma10 else -4)+(7 if ma10>ma20 else -3)
    vr=v[-1]/max(mean(v[-6:-1]),1)
    volume=clamp(45+(vr-1)*30)
    hi=max(c[-20:]); lo=min(c[-20:]); pos=(last-lo)/max(hi-lo,1e-9)
    position=clamp(100-abs(pos-.50)*110)
    trigger=max(max(x["h"] for x in h[-3:-1]),ma5)
    support=min(min(x["l"] for x in h[-5:]),ma10)
    reasons=[]; warnings=[]
    if last>ma5: reasons.append("站上5日线")
    if 1.05<=vr<=2.3: reasons.append(f"量能温和增强 {vr:.1f}x")
    if .25<=pos<=.68: reasons.append("位置仍偏早")
    if pos>.82: warnings.append("20日位置偏高")
    if vr>3: warnings.append("成交量过度放大")
    return {"trend":clamp(trend),"volume":volume,"position":position,"trigger":trigger,
            "support":support,"vr":vr,"ma5":ma5,"ma10":ma10,"ma20":ma20,
            "reasons":reasons,"warnings":warnings}

def _ret(c, days):
    if len(c)<=days or not c[-days-1]:
        return 0
    return (c[-1]/c[-days-1]-1)*100

def early_stage_features(h):
    """
    识别“还没有明显涨起来”的早期机会。
    主要找：
    - 平台首破
    - 底部转强
    - 回踩确认
    - 首次站回均线

    同时硬过滤：
    - 近5日涨幅 > 8%
    - 近10日涨幅 > 13%
    - 连涨 >= 3天
    - 距5日线 > 4.5%
    - 距10日线 > 7.5%
    - 高位且20日波动区间已经明显扩张
    """
    if len(h)<25:
        return {
            "early_score":0,"stage":"数据不足","extended":True,"chase_risk":"高",
            "ret3":0,"ret5":0,"ret10":0,"up_streak":0,
            "dist_ma5":0,"dist_ma10":0,"position20":1,"range10":0,"range20":0,
            "breakout_level":None,"reasons":[],"warnings":["历史数据不足"]
        }

    c=[x["c"] for x in h]
    v=[x["v"] for x in h]
    highs=[x["h"] for x in h]
    lows=[x["l"] for x in h]
    last=c[-1]
    ma5=mean(c[-5:]); ma10=mean(c[-10:]); ma20=mean(c[-20:])
    prev_ma5=mean(c[-6:-1])

    ret3=_ret(c,3); ret5=_ret(c,5); ret10=_ret(c,10)
    dist_ma5=(last/ma5-1)*100 if ma5 else 0
    dist_ma10=(last/ma10-1)*100 if ma10 else 0

    up_streak=0
    for bar in reversed(h):
        if bar.get("pct",0)>0.15:
            up_streak+=1
        else:
            break

    hi20=max(highs[-20:]); lo20=min(lows[-20:])
    position20=(last-lo20)/max(hi20-lo20,1e-9)
    range10=(max(highs[-10:])-min(lows[-10:]))/max(mean(c[-10:]),1e-9)*100
    range20=(hi20-lo20)/max(mean(c[-20:]),1e-9)*100

    avg_prev5_v=max(mean(v[-6:-1]),1)
    vr=v[-1]/avg_prev5_v
    prior5_high=max(highs[-6:-1])
    prior10_high=max(highs[-11:-1])

    # 形态识别
    cross_ma5 = c[-2] <= mean(c[-6:-1])*1.003 and last > ma5 and h[-1].get("pct",0)>0
    first_break = last >= prior5_high*0.998 and c[-2] < prior5_high and ret5<=6.5
    platform_break = range10<=11.5 and first_break and 1.05<=vr<=2.6
    pullback_confirm = (
        ma5>=ma10*0.995 and
        min(c[-3:-1]) <= ma5*1.015 and
        c[-1] > c[-2] and
        h[-1].get("pct",0) >= 0 and
        ret5<=6.5 and
        v[-2] <= max(mean(v[-7:-2]),1)*1.05
    )
    bottom_turn = (
        position20<=0.62 and
        ret10<=5.5 and
        last>ma5 and
        ma5>=prev_ma5 and
        h[-1].get("pct",0)>0 and
        vr>=0.9
    )

    if platform_break:
        stage="平台首破"
        pattern_score=28
    elif pullback_confirm:
        stage="回踩确认"
        pattern_score=26
    elif bottom_turn:
        stage="底部转强"
        pattern_score=24
    elif cross_ma5 and ret5<=5.5:
        stage="首次站回均线"
        pattern_score=20
    else:
        stage="无明确早期形态"
        pattern_score=5

    # “新鲜度”评分：越没有涨起来越高
    if ret5<=2:
        freshness5=22
    elif ret5<=5:
        freshness5=18
    elif ret5<=8:
        freshness5=9
    else:
        freshness5=0

    if ret10<=4:
        freshness10=12
    elif ret10<=8:
        freshness10=8
    elif ret10<=13:
        freshness10=4
    else:
        freshness10=0

    if up_streak<=1:
        streak_score=10
    elif up_streak==2:
        streak_score=4
    else:
        streak_score=0

    if -1.5<=dist_ma5<=2.5:
        distance_score=12
    elif -2.5<=dist_ma5<=4.0:
        distance_score=8
    else:
        distance_score=0

    if .22<=position20<=.62:
        location_score=10
    elif position20<.22:
        location_score=7
    elif position20<=.78:
        location_score=4
    else:
        location_score=0

    if .9<=vr<=2.2:
        volume_score=10
    elif .7<=vr<=2.8:
        volume_score=6
    else:
        volume_score=2

    early_score=clamp(pattern_score+freshness5+freshness10+streak_score+distance_score+location_score+volume_score)

    extended = (
        ret5>8.0 or
        ret10>13.0 or
        up_streak>=3 or
        dist_ma5>4.5 or
        dist_ma10>7.5 or
        (position20>.86 and range20>18) or
        h[-1].get("pct",0)>4.8
    )

    if extended:
        chase_risk="高"
    elif ret5>5 or up_streak==2 or dist_ma5>3:
        chase_risk="中"
    else:
        chase_risk="低"

    reasons=[]
    warnings=[]
    if stage!="无明确早期形态": reasons.append(stage)
    if ret5<=3: reasons.append(f"近5日仅{ret5:+.1f}%")
    if up_streak<=1: reasons.append("尚未连续拉升")
    if -1.5<=dist_ma5<=2.5: reasons.append("贴近5日线")
    if 1.05<=vr<=2.3: reasons.append("首次/温和放量")
    if ret5>6: warnings.append(f"近5日已涨{ret5:.1f}%")
    if up_streak>=2: warnings.append(f"已连涨{up_streak}天")
    if dist_ma5>3: warnings.append(f"高于5日线{dist_ma5:.1f}%")
    if extended: warnings.append("触发已涨过滤器")

    return {
        "early_score":round(early_score,1),
        "stage":stage,
        "extended":extended,
        "chase_risk":chase_risk,
        "ret3":round(ret3,2),"ret5":round(ret5,2),"ret10":round(ret10,2),
        "up_streak":up_streak,
        "dist_ma5":round(dist_ma5,2),"dist_ma10":round(dist_ma10,2),
        "position20":round(position20*100,1),
        "range10":round(range10,2),"range20":round(range20,2),
        "breakout_level":round(prior5_high,2),
        "reasons":reasons[:5],"warnings":warnings[:5]
    }

def backtest_stats(h, current_stage=None):
    """
    只回测“早期形态”，避免用已经涨了几天的趋势股样本来计算胜率。
    如果同形态样本 >= 6，优先采用同形态；否则退回全部早期形态样本。
    """
    empty = {
        "sample_size":0,"match_type":"无足够样本",
        "up_rate_1d":None,"up_rate_3d":None,"up_rate_5d":None,
        "win_rate_1d":None,"win_rate_3d":None,"win_rate_5d":None,
        "avg_1d_return":None,"avg_3d_return":None,"avg_5d_return":None,
        "avg_max_up_5d":None,"avg_max_drawdown_5d":None,
        "confidence":"样本不足"
    }
    if len(h)<45:
        return empty

    all_samples=[]
    same_stage=[]

    for i in range(25,len(h)-5):
        prefix=h[:i+1]
        f=early_stage_features(prefix)

        if f["extended"]:
            continue
        if f["early_score"]<58:
            continue
        if f["stage"]=="无明确早期形态":
            continue

        entry=h[i]["c"]
        target=entry*1.035
        stop=entry*0.975

        target_results={}
        for horizon in (1,3,5):
            outcome=False
            for j in range(i+1,min(i+1+horizon,len(h))):
                bar=h[j]
                hit_stop=bar["l"]<=stop
                hit_target=bar["h"]>=target
                if hit_stop:
                    outcome=False
                    break
                if hit_target:
                    outcome=True
                    break
            target_results[horizon]=outcome

        def close_ret(k):
            close=h[min(i+k,len(h)-1)]["c"]
            return (close-entry)/entry*100

        future=h[i+1:min(i+6,len(h))]
        sample={
            "stage":f["stage"],
            "target":target_results,
            "r1":close_ret(1),"r3":close_ret(3),"r5":close_ret(5),
            "max_up":(max(x["h"] for x in future)-entry)/entry*100 if future else 0,
            "max_dd":(min(x["l"] for x in future)-entry)/entry*100 if future else 0
        }
        all_samples.append(sample)
        if current_stage and f["stage"]==current_stage:
            same_stage.append(sample)

    samples=same_stage if len(same_stage)>=6 else all_samples
    match_type=("同形态："+current_stage) if len(same_stage)>=6 else "全部早期形态"
    n=len(samples)

    if n==0:
        return empty

    pct=lambda num: round(num/n*100,1)
    target_rate=lambda k: pct(sum(1 for x in samples if x["target"][k]))
    up_rate=lambda k: pct(sum(1 for x in samples if x[f"r{k}"]>0))
    avg=lambda key: round(sum(x[key] for x in samples)/n,2)
    conf="较高" if n>=20 else ("中等" if n>=10 else ("较低" if n>=6 else "样本不足"))

    return {
        "sample_size":n,"match_type":match_type,
        "up_rate_1d":up_rate(1),"up_rate_3d":up_rate(3),"up_rate_5d":up_rate(5),
        "win_rate_1d":target_rate(1),"win_rate_3d":target_rate(3),"win_rate_5d":target_rate(5),
        "avg_1d_return":avg("r1"),"avg_3d_return":avg("r3"),"avg_5d_return":avg("r5"),
        "avg_max_up_5d":avg("max_up"),"avg_max_drawdown_5d":avg("max_dd"),
        "confidence":conf
    }

def make_rise_signal(score, bt, market_score, flow_score, buy_state):
    """
    当前“待涨指数”不是承诺概率，而是把：
    当前技术评分 + 历史上涨率 + 历史目标胜率 + 市场环境 + 资金评分
    合成一个 0~100 的强弱指示。

    历史样本会做收缩：样本越少，越向50%中性值靠拢，防止小样本虚高。
    """
    n=bt.get("sample_size",0) or 0
    confidence=min(n/20,1)

    raw_up=bt.get("up_rate_5d")
    raw_win=bt.get("win_rate_5d")
    raw_up=50 if raw_up is None else raw_up
    raw_win=50 if raw_win is None else raw_win

    shrunk_up=50+(raw_up-50)*confidence
    shrunk_win=50+(raw_win-50)*confidence

    idx = (
        score*0.35 +
        shrunk_up*0.27 +
        shrunk_win*0.13 +
        market_score*0.18 +
        flow_score*0.07
    )

    if buy_state=="进入买点区":
        idx += 2
    idx=round(clamp(idx),1)

    if idx>=72:
        level="待涨强"
        tone="strong"
    elif idx>=64:
        level="偏强"
        tone="good"
    elif idx>=56:
        level="中性偏多"
        tone="neutral"
    elif idx>=48:
        level="一般"
        tone="weak"
    else:
        level="偏弱"
        tone="bad"

    # “待涨估计”只基于历史5日上涨率做小样本收缩，不把当前评分硬伪装成概率。
    estimated_up=round(shrunk_up,1)

    if buy_state=="进入买点区" and idx>=72:
        conclusion="买点已到，且历史/当前结构共振较强"
    elif buy_state=="进入买点区" and idx>=64:
        conclusion="买点已到，但上涨优势属于中等"
    elif idx>=72:
        conclusion="待涨结构较强，但价格尚未进入理想买点"
    elif idx>=64:
        conclusion="偏多观察，等待更好的价格确认"
    elif idx>=56:
        conclusion="有上涨倾向，但优势不够明显"
    else:
        conclusion="上涨优势不足，不宜因为出现买点就强行介入"

    return {
        "index":idx,
        "level":level,
        "tone":tone,
        "estimated_up_5d":estimated_up,
        "target_win_5d":bt.get("win_rate_5d"),
        "avg_5d_return":bt.get("avg_5d_return"),
        "avg_max_up_5d":bt.get("avg_max_up_5d"),
        "avg_max_drawdown_5d":bt.get("avg_max_drawdown_5d"),
        "sample_size":n,
        "confidence":bt.get("confidence","样本不足"),
        "conclusion":conclusion
    }

def make_buy_plan(q,t,early,trig):
    """
    买入价从“向上突破触发价”改成“早期结构的可接受成交区”。
    目标是尽量靠近支撑/突破回踩位，而不是价格已经涨开后再追。
    """
    px=q["price"]
    ma5=t.get("ma5") or px
    ma10=t.get("ma10") or px
    breakout=early.get("breakout_level") or trig

    stage=early.get("stage")
    if stage=="平台首破":
        ideal=min(px, breakout*1.002)
        low=breakout*0.993
        high=breakout*1.008
        plan_type="突破位回踩 / 首破确认"
    elif stage=="回踩确认":
        ideal=max(ma5, min(px, ma5*1.005))
        low=ma5*0.993
        high=ma5*1.010
        plan_type="5日线附近回踩确认"
    elif stage=="底部转强":
        anchor=max(ma5,ma10)
        ideal=min(px,anchor*1.006)
        low=anchor*0.992
        high=anchor*1.012
        plan_type="底部转强首个承接区"
    elif stage=="首次站回均线":
        ideal=min(px,ma5*1.005)
        low=ma5*0.992
        high=ma5*1.010
        plan_type="首次站回5日线确认"
    else:
        ideal=min(px,ma5*1.003)
        low=ma5*0.990
        high=ma5*1.008
        plan_type="观察，不主动追价"

    no_chase=high*1.015
    support=min(t.get("support") or ideal*0.975, ma10)
    stop=min(ideal*0.975,support)

    if early.get("extended"):
        state="已涨过多，过滤"
    elif low<=px<=high:
        state="进入买点区"
    elif px<low:
        state="等待确认"
    elif px<=no_chase:
        state="高于理想区，等回踩"
    else:
        state="超过追价线，不追"

    return {
        "buy_low":round(low,2),"buy_high":round(high,2),"ideal_buy":round(ideal,2),
        "no_chase":round(no_chase,2),"stop":round(stop,2),"state":state,
        "type":plan_type
    }

def try_eastmoney_flow(code):
    try:
        market="1" if code.startswith("6") else "0"; url="https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
        params={"lmt":"5","klt":"101","secid":f"{market}.{code}","fields1":"f1,f2,f3,f7","fields2":"f51,f52,f53,f54,f55,f56"}
        j=S.get(url,params=params,timeout=8).json(); kl=(j.get("data") or {}).get("klines") or []; vals=[]
        for s in kl:
            a=s.split(",")
            if len(a)>=6:
                try: vals.append({"date":a[0],"main":float(a[1]),"small":float(a[2]),"medium":float(a[3]),"large":float(a[4]),"super":float(a[5])})
                except: pass
        if vals:
            last=vals[-1]; last2=vals[-2:] if len(vals)>=2 else vals
            return {"available":True,"main_yi":round(last["main"]/1e8,2),"large_yi":round(last["large"]/1e8,2),"super_yi":round(last["super"]/1e8,2),"positive_2":sum(1 for x in last2 if x["main"]>0)}
    except: pass
    return {"available":False,"main_yi":None,"large_yi":None,"super_yi":None,"positive_2":None}

def analyze(q,market_score=50,include_flow=False):
    h=enrich_today(history(q["bs_code"]),q)
    t=technical(h)
    early=early_stage_features(h)

    liquidity=clamp(45+math.log10(max(q["amount"]/1e8,1))*28)
    anti_chase=clamp(100-max(early["ret5"],0)*8-max(early["up_streak"]-1,0)*12)
    flow=try_eastmoney_flow(q["code"]) if include_flow else {
        "available":False,"main_yi":None,"large_yi":None,"super_yi":None,"positive_2":None
    }
    flow_score=50
    if flow["available"]:
        flow_score=clamp(50+(14 if flow["main_yi"]>0 else -8)+(8 if flow["positive_2"]==2 else 0))

    # 核心从“趋势强”切换为“早期机会强”
    score=(
        early["early_score"]*.54 +
        t["trend"]*.08 +
        t["volume"]*.08 +
        liquidity*.10 +
        anti_chase*.08 +
        market_score*.07 +
        flow_score*.05
    )

    trig=t["trigger"] if t["trigger"] else q["price"]*1.005
    buy_plan=make_buy_plan(q,t,early,trig)
    stop=buy_plan["stop"]

    bt=backtest_stats(h,current_stage=early["stage"])
    rise=make_rise_signal(score,bt,market_score,flow_score,buy_plan["state"])

    # 已涨过滤器会同步压低待涨指数，避免“历史胜率高但位置太晚”
    if early["extended"]:
        rise["index"]=min(rise["index"],45)
        rise["level"]="偏弱"
        rise["tone"]="bad"
        rise["conclusion"]="历史形态可能不错，但当前已经涨多，禁止作为新买点"

    ideal=buy_plan["ideal_buy"]
    target1=ideal*1.035
    target2=ideal*1.060
    rr1=(target1-ideal)/max(ideal-stop,.01)

    reasons=list(early["reasons"])+list(t["reasons"])
    warnings=list(early["warnings"])+list(t["warnings"])
    if flow["available"] and flow["main_yi"]>0: reasons.append("主力资金净流入")
    if flow["available"] and flow["positive_2"]==2: reasons.append("连续2日资金回流")

    if early["extended"]:
        status="已涨过滤"
    elif early["early_score"]>=68 and rise["index"]>=60 and buy_plan["state"]=="进入买点区":
        status="早期买点"
    elif early["early_score"]>=60 and rise["index"]>=56:
        status="早期观察"
    else:
        status="放弃"

    return {
        "code":q["code"],"name":q["name"],"price":round(q["price"],2),"pct":round(q["pct"],2),
        "amount_yi":round(q["amount"]/1e8,2),"quote_source":q["quote_source"],
        "score":round(score,1),
        "early_signal":early,
        "flow_score":round(flow_score),"trend_score":round(t["trend"]),
        "volume_score":round(t["volume"]),"position_score":round(t["position"]),
        "liquidity_score":round(liquidity),"volume_ratio":round(t["vr"],2),
        "trigger":round(trig,2),
        "buy_plan":buy_plan,
        "backtest":bt,
        "rise_signal":rise,
        "stop":round(stop,2),
        "target1":round(target1,2),"target2":round(target2,2),
        "rr1":round(rr1,2),
        "status":status,
        "reasons":reasons[:7],
        "warnings":warnings[:6],
        "fund_flow":flow
    }

def main():
    lg=bs.login()
    if lg.error_code!="0": raise RuntimeError("BaoStock 登录失败: "+lg.error_msg)
    try:
        universe=get_universe(); quotes,health=fetch_quotes(universe)
        if len(quotes)<2000: raise RuntimeError(f"实时行情股票数异常：{len(quotes)}，拒绝覆盖旧数据")
        by_code={x["code"]:x for x in quotes}; pcts=[x["pct"] for x in quotes]; up=sum(1 for p in pcts if p>0)/len(pcts)*100; med=median(pcts)
        market_score=round(clamp(45+(up-50)*.8+med*5)); market_state="偏强" if market_score>=65 else ("中性" if market_score>=45 else "偏弱")
        pre=[x for x in quotes if 5<=x["price"]<=30 and x["amount"]>=2e8 and -4.0<=x["pct"]<=4.5]
        for x in pre:
            liq=clamp(40+math.log10(max(x["amount"]/1e8,1))*28); calm=clamp(100-abs(x["pct"]-1.0)*10); x["_pre"]=liq*.60+calm*.40
        pre=sorted(pre,key=lambda z:z["_pre"],reverse=True)[:50]; candidates=[]
        for x in pre: candidates.append(analyze(x,market_score=market_score,include_flow=(len(candidates)<8)))
        candidates=sorted(candidates,key=lambda z:(0 if z.get("early_signal",{}).get("extended") else 1,z.get("early_signal",{}).get("early_score",0),z.get("rise_signal",{}).get("index",0),z["score"]),reverse=True)
        watch=[analyze(by_code[c],market_score=market_score,include_flow=True) for c in WATCHLIST if c in by_code]
        source_health={"baostock":{"ok":len(universe)>2000,"count":len(universe),"role":"股票池/历史日K"},"quotes":{"ok":len(quotes)>2000,"count":len(quotes),"role":"实时行情","detail":health},"eastmoney_flow":{"ok":any(x["fund_flow"]["available"] for x in watch+candidates[:5]),"role":"资金流（可选增强）"}}
        now=datetime.now(CN).strftime("%Y-%m-%d %H:%M:%S")
        # 轻量股票索引：用于网页端“代码/名称搜索添加自选”
        symbols=[{"code":x["code"],"name":x["name"]} for x in quotes]
        quote_snapshot={x["code"]:{
            "code":x["code"],"name":x["name"],"price":round(x["price"],2),
            "pct":round(x["pct"],2),"amount_yi":round(x["amount"]/1e8,2)
        } for x in quotes}

        data={"version":"1.7","updated_at":now,"market":{"score":market_score,"state":market_state,"up_ratio":round(up,1),"median_pct":round(med,2),"universe":len(quotes)},"opportunities":[x for x in candidates if x["status"] in ("早期买点","早期观察") and not x.get("early_signal",{}).get("extended") and x.get("early_signal",{}).get("early_score",0)>=60][:5],"watchlist":watch,"candidates":candidates[:20],"source_health":source_health,"quote_snapshot":quote_snapshot,"rules":{"price":"5-30元","amount":"≥2亿元","day_pct":"-4%~+4.5%","excluded":"科创/创业/北交/ST/退市","holding":"1-5个交易日","anti_chase":"近5日>8% / 近10日>13% / 连涨≥3天 / 距MA5>4.5% 直接过滤"}}
        Path("data").mkdir(exist_ok=True)
        Path("data/latest.json").write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        Path("data/symbols.json").write_text(json.dumps(symbols,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        print("OK",now,"quotes",len(quotes),"opps",len(data["opportunities"]),"watch",len(watch))
    finally: bs.logout()

if __name__=="__main__": main()
