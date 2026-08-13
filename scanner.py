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

    compression = (range10<=8.5 and ret10<=4.5 and abs(dist_ma5)<=2.5 and position20<=0.68 and 0.72<=vr<=1.55 and up_streak<=1)

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
    elif compression:
        stage="潜伏蓄势"
        pattern_score=18
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

def elasticity_features(h):
    """价格弹性：只描述波动能力，不代表方向。"""
    if len(h)<20:
        return {"score":0,"level":"数据不足","tone":"bad","atr14_pct":None,"avg_amp10":None,"avg_abs_pct10":None,"swing_fit":"数据不足","explain":"历史数据不足"}
    trs=[]; amps=[]; abs_pcts=[]
    for i in range(1,len(h)):
        prev=h[i-1]["c"]
        if prev<=0: continue
        hi=h[i]["h"]; lo=h[i]["l"]
        trs.append(max(hi-lo,abs(hi-prev),abs(lo-prev))/prev*100)
        amps.append((hi-lo)/prev*100)
        abs_pcts.append(abs(h[i].get("pct",0)))
    atr14=mean(trs[-14:]); amp10=mean(amps[-10:]); abs10=mean(abs_pcts[-10:])
    atr_s=clamp((atr14-1.2)*22); amp_s=clamp((amp10-1.8)*18); abs_s=clamp((abs10-0.7)*26)
    score=round(clamp(atr_s*.52+amp_s*.31+abs_s*.17),1)
    if score>=68 or (atr14>=3.8 and amp10>=4.5):
        level="高弹性"; tone="strong"; fit="适合1~2日快进快出"; explain="历史日波动较大，短时间容易拉开幅度，但回撤也更快"
    elif score>=48:
        level="中弹性"; tone="neutral"; fit="适合2~5日短波段"; explain="有一定波动空间，但爆发速度通常弱于高弹性票"
    else:
        level="低弹性"; tone="weak"; fit="短线效率偏低"; explain="历史波动较小，1~2日内拉开收益空间的能力偏弱"
    return {"score":score,"level":level,"tone":tone,"atr14_pct":round(atr14,2),"avg_amp10":round(amp10,2),"avg_abs_pct10":round(abs10,2),"swing_fit":fit,"explain":explain}

def quick_elasticity(q):
    px=q.get("price") or 0; pct=q.get("pct") or 0
    prev=px/(1+pct/100) if px and abs(1+pct/100)>1e-9 else px
    hi=q.get("high") or px; lo=q.get("low") or px
    amp=(hi-lo)/prev*100 if prev else 0
    score=round(clamp(amp*13+abs(pct)*6),1)
    level="日内高弹性" if score>=68 else ("日内中弹性" if score>=45 else "日内低弹性")
    return {"score":score,"level":level,"amplitude_pct":round(amp,2)}


def turnover_features(h):
    """换手活跃度：高弹性短线票不能太冷。今天盘中没有完整换手时，用最近有效日K换手做代理。"""
    turns=[x.get("turn",0) for x in h[-12:] if isinstance(x.get("turn",0),(int,float)) and x.get("turn",0)>0]
    last=turns[-1] if turns else 0
    avg5=mean(turns[-5:]) if turns else 0
    avg10=mean(turns[-10:]) if turns else 0
    score=round(clamp((avg5-1.0)*24 + (last-1.0)*10),1)
    ok=avg5>=2.0 or last>=2.0
    if avg5>=5 or last>=6:
        level="活跃"
    elif ok:
        level="正常"
    else:
        level="偏低"
    return {"last_turn":round(last,2),"avg5_turn":round(avg5,2),"avg10_turn":round(avg10,2),"score":score,"ok":ok,"level":level}

def expected_upside_model(bt, elastic):
    """5日弹性空间估计：用历史同类最大上冲 + 近期ATR/振幅合成，只用于筛选，不承诺未来收益。"""
    hist=bt.get("avg_max_up_5d")
    atr=elastic.get("atr14_pct") or 0
    amp=elastic.get("avg_amp10") or 0
    vol_space=max(atr*2.15, amp*1.55, 0)
    if isinstance(hist,(int,float)) and hist>0:
        est=hist*0.58 + vol_space*0.42
        basis="历史同类最大上冲 + 近期波动"
    else:
        est=vol_space
        basis="近期波动估计"
    return {"expected_upside_5d":round(est,2),"basis":basis,"hist_max_up_5d":hist,"vol_space_5d":round(vol_space,2)}

def make_high_elastic_wait_signal(q, early, elastic, rise, upside, turnover, buy_plan, market_score):
    """高弹性待涨池：只找买点区内、还没涨飞、短线弹性够、上涨空间够的票。"""
    est_prob=rise.get("estimated_up_5d") or 0
    exp_up=upside.get("expected_upside_5d") or 0
    checks={
        "待涨概率≥60%": est_prob>=60,
        "5日空间≥8%": exp_up>=8,
        "已进入买点区": buy_plan.get("state")=="进入买点区",
        "近5日未涨多": (not early.get("extended")) and early.get("ret5",99)<=6.5 and early.get("up_streak",9)<=2,
        "换手不低": bool(turnover.get("ok")),
        "股价5~30元": 5<=q.get("price",0)<=30,
        "主板优先": str(q.get("code","")).startswith(("600","601","603","605","000","001","002","003")),
        "环境不弱": market_score>=45,
        "高弹性": elastic.get("score",0)>=60,
    }
    pullback_like = early.get("stage") in ("回踩确认","底部转强","潜伏蓄势") or (early.get("ret3",0)<=2.0 and abs(early.get("dist_ma5",9))<=2.5)
    base_score=(
        est_prob*0.22 +
        clamp(exp_up*8)*0.24 +
        elastic.get("score",0)*0.20 +
        early.get("early_score",0)*0.14 +
        turnover.get("score",0)*0.10 +
        market_score*0.10
    )
    if pullback_like: base_score+=4
    if early.get("stage")=="回踩确认": base_score+=3
    if early.get("ret5",0)>5: base_score-=5
    score=round(clamp(base_score),1)
    failed=[k for k,v in checks.items() if not v]
    qualified=not failed
    if qualified and pullback_like:
        label="高弹性待涨｜回踩优先"
    elif qualified:
        label="高弹性待涨｜买点区"
    elif len(failed)<=2 and est_prob>=57 and exp_up>=7:
        label="接近入池｜等确认"
    else:
        label="未入池"
    return {"qualified":qualified,"score":score,"label":label,"checks":checks,"failed":failed[:5],"pullback_like":pullback_like}

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
    elif stage=="潜伏蓄势":
        anchor=max(ma5,ma10*0.998)
        ideal=min(px,anchor*1.004)
        low=anchor*0.990
        high=anchor*1.010
        plan_type="横盘蓄势承接区"
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

def fetch_sector_flow():
    """行业板块主力资金流，可选增强；失败不影响主扫描。"""
    hosts=["https://82.push2.eastmoney.com/api/qt/clist/get","https://push2.eastmoney.com/api/qt/clist/get"]
    params={"pn":"1","pz":"200","po":"1","np":"1","ut":"bd1d9ddb04089700cf9c27f6f7426281","fltt":"2","invt":"2","fid":"f62","fs":"m:90 t:2 f:!50","fields":"f12,f14,f2,f3,f6,f62,f184"}
    for url in hosts:
        try:
            r=S.get(url,params=params,timeout=10); r.raise_for_status()
            j=r.json(); diff=(j.get("data") or {}).get("diff") or []
            rows=[]
            for x in diff:
                try:
                    main=float(x.get("f62") or 0)
                    rows.append({
                        "code":str(x.get("f12") or ""),"name":str(x.get("f14") or ""),
                        "pct":round(float(x.get("f3") or 0),2),
                        "amount_yi":round(float(x.get("f6") or 0)/1e8,2),
                        "main_yi":round(main/1e8,2),
                        "main_pct":round(float(x.get("f184") or 0),2)
                    })
                except:
                    pass
            if len(rows)>=20:
                return {
                    "available":True,"stale":False,
                    "updated_at":datetime.now(CN).strftime("%Y-%m-%d %H:%M:%S"),
                    "inflow":sorted(rows,key=lambda z:z["main_yi"],reverse=True)[:10],
                    "outflow":sorted(rows,key=lambda z:z["main_yi"])[:8]
                }
        except:
            continue
    return {"available":False,"stale":False,"updated_at":None,"inflow":[],"outflow":[]}

def analyze(q,market_score=50,include_flow=False):
    h=enrich_today(history(q["bs_code"]),q)
    t=technical(h)
    early=early_stage_features(h)
    elastic=elasticity_features(h)
    turnover=turnover_features(h)

    liquidity=clamp(45+math.log10(max(q["amount"]/1e8,1))*28)
    anti_chase=clamp(100-max(early["ret5"],0)*8-max(early["up_streak"]-1,0)*12)
    flow=try_eastmoney_flow(q["code"]) if include_flow else {
        "available":False,"main_yi":None,"large_yi":None,"super_yi":None,"positive_2":None
    }
    flow_score=50
    if flow["available"]:
        flow_score=clamp(50+(14 if flow["main_yi"]>0 else -8)+(8 if flow["positive_2"]==2 else 0))

    # 短波段核心：早期位置 + 弹性。高弹性本身不代表上涨方向。
    score=(
        early["early_score"]*.38 +
        elastic["score"]*.30 +
        t["trend"]*.06 +
        t["volume"]*.06 +
        liquidity*.08 +
        anti_chase*.05 +
        market_score*.04 +
        flow_score*.03
    )

    trig=t["trigger"] if t["trigger"] else q["price"]*1.005
    buy_plan=make_buy_plan(q,t,early,trig)
    stop=buy_plan["stop"]

    bt=backtest_stats(h,current_stage=early["stage"])
    rise=make_rise_signal(score,bt,market_score,flow_score,buy_plan["state"])
    upside=expected_upside_model(bt,elastic)
    wait_signal=make_high_elastic_wait_signal(q,early,elastic,rise,upside,turnover,buy_plan,market_score)

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
    elif wait_signal.get("qualified"):
        status="高弹性待涨"
    elif elastic["score"]>=68 and early["early_score"]>=56 and rise["index"]>=56 and buy_plan["state"]=="进入买点区":
        status="高弹性买点"
    elif elastic["score"]>=62 and early["early_score"]>=52 and rise["index"]>=52:
        status="高弹性观察"
    elif elastic["score"]>=48 and early["early_score"]>=58 and rise["index"]>=56:
        status="中弹性备选"
    elif elastic["score"]<48:
        status="低弹性/不优先"
    else:
        status="放弃"

    return {
        "code":q["code"],"name":q["name"],"price":round(q["price"],2),"pct":round(q["pct"],2),
        "amount_yi":round(q["amount"]/1e8,2),"quote_source":q["quote_source"],
        "score":round(score,1),
        "early_signal":early,
        "elasticity":elastic,
        "turnover":turnover,
        "upside_model":upside,
        "wait_pool_signal":wait_signal,
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
        pre=[x for x in quotes if 5<=x["price"]<=30 and x["amount"]>=1.5e8 and -4.5<=x["pct"]<=4.8]
        for x in pre:
            liq=clamp(40+math.log10(max(x["amount"]/1e8,1))*28); calm=clamp(100-abs(x["pct"]-1.0)*10); x["_pre"]=liq*.60+calm*.40
        pre=sorted(pre,key=lambda z:z["_pre"],reverse=True)[:60]; candidates=[]
        for x in pre: candidates.append(analyze(x,market_score=market_score,include_flow=(len(candidates)<8)))
        candidates=sorted(candidates,key=lambda z:(0 if z.get("early_signal",{}).get("extended") else 1,z.get("wait_pool_signal",{}).get("score",0),z.get("wait_pool_signal",{}).get("qualified",False),z.get("elasticity",{}).get("score",0),z.get("rise_signal",{}).get("estimated_up_5d") or 0),reverse=True)
        watch=[analyze(by_code[c],market_score=market_score,include_flow=True) for c in WATCHLIST if c in by_code]

        sector_flow=fetch_sector_flow()
        old_latest={}
        try:
            if Path("data/latest.json").exists():
                old_latest=json.loads(Path("data/latest.json").read_text(encoding="utf-8"))
        except:
            old_latest={}
        if not sector_flow["available"]:
            old_sector=old_latest.get("sector_flow") or {}
            if old_sector.get("inflow"):
                sector_flow=old_sector
                sector_flow["stale"]=True

        source_health={
            "baostock":{"ok":len(universe)>2000,"count":len(universe),"role":"股票池/历史日K"},
            "quotes":{"ok":len(quotes)>2000,"count":len(quotes),"role":"实时行情","detail":health},
            "eastmoney_flow":{"ok":any(x["fund_flow"]["available"] for x in watch+candidates[:5]),"role":"个股资金流（可选）"},
            "sector_flow":{"ok":bool(sector_flow.get("inflow")),"role":"板块资金流（可选）","stale":sector_flow.get("stale",False)}
        }
        now=datetime.now(CN).strftime("%Y-%m-%d %H:%M:%S")
        # 轻量股票索引：用于网页端“代码/名称搜索添加自选”
        symbols=[{"code":x["code"],"name":x["name"]} for x in quotes]
        quote_snapshot={}
        for x in quotes:
            qe=quick_elasticity(x)
            quote_snapshot[x["code"]]={
                "code":x["code"],"name":x["name"],"price":round(x["price"],2),"pct":round(x["pct"],2),
                "amount_yi":round(x["amount"]/1e8,2),
                "open":round(x.get("open") or 0,2),"high":round(x.get("high") or 0,2),"low":round(x.get("low") or 0,2),
                "amplitude_pct":qe["amplitude_pct"],
                "quick_elasticity_score":qe["score"],
                "quick_elasticity_level":qe["level"],
                "quote_source":x.get("quote_source")
            }

        # 风险池：告诉用户哪些票“看起来活跃但不适合新买点”
        avoid_pool=[]
        for x in candidates:
            es=x.get("early_signal",{}) or {}
            el=x.get("elasticity",{}) or {}
            warnings=list(x.get("warnings") or [])
            reason=None
            if es.get("extended"):
                reason="已涨过滤 / 不追"
            elif el.get("score",0)<48 and x.get("score",0)>=50:
                reason="弹性偏小 / 短线效率低"
            elif es.get("chase_risk")=="高":
                reason="追高风险高"
            elif x.get("status") in ("低弹性/不优先","已涨过滤"):
                reason=x.get("status")
            if reason:
                avoid_pool.append({
                    "code":x.get("code"),"name":x.get("name"),"price":x.get("price"),"pct":x.get("pct"),
                    "reason":reason,
                    "elasticity":el,
                    "early_signal":es,
                    "fund_flow":x.get("fund_flow"),
                    "warnings":warnings[:5],
                    "suggestion":"等待回踩/重新蓄势，不作为当前新买点"
                })
        avoid_pool=avoid_pool[:8]

        market_guidance="正常观察，优先高弹性+启动初期" if market_score>=55 else ("环境偏弱，降低仓位，只做最强1-2只" if market_score>=42 else "环境弱，少做或不做")

        high_elastic_wait_pool=[x for x in candidates if x.get("wait_pool_signal",{}).get("qualified") and x.get("rise_signal",{}).get("estimated_up_5d",0)>=60 and x.get("upside_model",{}).get("expected_upside_5d",0)>=8]
        high_elastic_wait_pool=sorted(high_elastic_wait_pool,key=lambda z:z.get("wait_pool_signal",{}).get("score",0),reverse=True)[:8]
        base_opportunities=[x for x in candidates if x["status"] in ("高弹性待涨","高弹性买点","高弹性观察","中弹性备选") and not x.get("early_signal",{}).get("extended") and x.get("elasticity",{}).get("score",0)>=48][:5]
        final_opportunities=(high_elastic_wait_pool[:5] if high_elastic_wait_pool else base_opportunities)

        data={
            "version":"2.6","updated_at":now,
            "data_mode":"高弹性待涨池 + 前端实时行情层 + 资金异动反推雷达 + 定时模型层",
            "refresh_note":"前端行情约10秒；模型依赖后台扫描任务，存在任务排队延迟",
            "market":{"score":market_score,"state":market_state,"guidance":market_guidance,"up_ratio":round(up,1),"median_pct":round(med,2),"universe":len(quotes)},
            "opportunities":final_opportunities,
            "high_elastic_wait_pool":high_elastic_wait_pool,
            "watchlist":watch,
            "candidates":candidates[:25],
            "avoid_list":avoid_pool,
            "sector_flow":sector_flow,
            "source_health":source_health,
            "quote_snapshot":quote_snapshot,
            "rules":{"price":"5-30元","amount":"≥1.5亿元","day_pct":"-4.5%~+4.8%","excluded":"科创/创业/北交/ST/退市","holding":"1-5个交易日","focus":"高弹性待涨池：待涨≥60% / 5日空间≥8% / 买点区 / 换手不低 / 板块环境不弱","anti_chase":"近5日>8% / 近10日>13% / 连涨≥3天 / 距MA5>4.5% 直接过滤"}
        }
        Path("data").mkdir(exist_ok=True)
        Path("data/latest.json").write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        Path("data/symbols.json").write_text(json.dumps(symbols,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        print("OK",now,"quotes",len(quotes),"opps",len(data["opportunities"]),"watch",len(watch))
    finally: bs.logout()

if __name__=="__main__": main()
