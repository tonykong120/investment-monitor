import json, math, time, statistics, re
from pathlib import Path
from datetime import datetime, timedelta, timezone
import requests
import baostock as bs

CN = timezone(timedelta(hours=8))
WATCHLIST = ["600105", "000021"]
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

def history(bs_code, days=260):
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
    if len(h)<20: return {"trend":50,"volume":50,"position":50,"trigger":None,"support":None,"vr":1,"ma5":None,"ma10":None,"ma20":None,"reasons":[],"warnings":["历史数据不足"]}
    c=[x["c"] for x in h]; v=[x["v"] for x in h]; last=c[-1]
    ma5=mean(c[-5:]); ma10=mean(c[-10:]); ma20=mean(c[-20:])
    trend=50+(15 if last>ma5 else -8)+(12 if ma5>ma10 else -6)+(10 if ma10>ma20 else -5)
    vr=v[-1]/max(mean(v[-6:-1]),1); volume=clamp(45+(vr-1)*35)
    hi=max(c[-20:]); lo=min(c[-20:]); pos=(last-lo)/max(hi-lo,1e-9); position=clamp(100-abs(pos-.55)*120)
    trigger=max(max(x["h"] for x in h[-3:-1]),ma5); support=min(min(x["l"] for x in h[-5:]),ma10)
    reasons=[]; warnings=[]
    if last>ma5: reasons.append("站上5日线")
    if ma5>ma10: reasons.append("5日线强于10日线")
    if ma10>ma20: reasons.append("中短趋势向上")
    if 1.1<=vr<=2.5: reasons.append(f"量能增强 {vr:.1f}x")
    if .3<=pos<=.7: reasons.append("处于20日中位区")
    if pos>.85: warnings.append("接近20日高位")
    if vr>3: warnings.append("成交量过度放大")
    return {"trend":clamp(trend),"volume":volume,"position":position,"trigger":trigger,"support":support,"vr":vr,"ma5":ma5,"ma10":ma10,"ma20":ma20,"reasons":reasons,"warnings":warnings}



def backtest_stats(h):
    """
    历史同类技术结构回测。
    胜：信号出现后 1/3/5 个交易日内，+3.5% 目标先于 -2.5% 止损触发。
    若同一天同时触发目标和止损，按止损处理（保守口径）。
    这不是未来概率，只是同一只股票历史上的相似结构统计。
    """
    if len(h)<40:
        return {"sample_size":0,"win_rate_1d":None,"win_rate_3d":None,"win_rate_5d":None,"avg_5d_return":None,"confidence":"样本不足"}
    samples=[]
    # 最后5根留给未来窗口，不拿当前未完成日作为历史样本
    for i in range(20, len(h)-5):
        prefix=h[:i+1]
        t=technical(prefix)
        day=h[i]
        # 与当前工作台筛选方向一致：趋势偏强、量能不过度、位置不过高、当日不追涨
        if t["trend"] < 65: continue
        if not (30 <= t["volume"] <= 100): continue
        if not (20 <= t["position"] <= 88): continue
        if not (-5 <= day.get("pct",0) <= 5): continue
        entry=day["c"]; target=entry*1.035; stop=entry*0.975
        results={}
        for horizon in (1,3,5):
            outcome=False
            for j in range(i+1, min(i+1+horizon, len(h))):
                bar=h[j]
                hit_stop=bar["l"] <= stop
                hit_target=bar["h"] >= target
                if hit_stop: outcome=False; break
                if hit_target: outcome=True; break
            results[horizon]=outcome
        ret5=(h[min(i+5,len(h)-1)]["c"]-entry)/entry*100
        samples.append((results,ret5))
    n=len(samples)
    if n==0:
        return {"sample_size":0,"win_rate_1d":None,"win_rate_3d":None,"win_rate_5d":None,"avg_5d_return":None,"confidence":"样本不足"}
    rate=lambda k: round(sum(1 for r,_ in samples if r[k])/n*100,1)
    conf="较高" if n>=20 else ("中等" if n>=10 else ("较低" if n>=6 else "样本不足"))
    return {"sample_size":n,"win_rate_1d":rate(1),"win_rate_3d":rate(3),"win_rate_5d":rate(5),
            "avg_5d_return":round(sum(x for _,x in samples)/n,2),"confidence":conf}

def make_buy_plan(q,t,trig,stop):
    # 把技术触发价翻译成更直观的“可下单价格区间”
    ideal=trig
    low=ideal*0.995
    high=ideal*1.008
    no_chase=ideal*1.025
    # 如果5日线就在触发位附近，允许买入区下沿靠近5日线，但不放宽超过1.2%
    if t.get("ma5"):
        low=max(ideal*0.988, min(low, t["ma5"]*0.998))
    px=q["price"]
    if low <= px <= high:
        state="进入买点区"
    elif px < low:
        state="等待到价"
    elif px <= no_chase:
        state="价格偏高，等回踩"
    else:
        state="超过追价线，不追"
    return {"buy_low":round(low,2),"buy_high":round(high,2),"ideal_buy":round(ideal,2),
            "no_chase":round(no_chase,2),"stop":round(stop,2),"state":state,
            "type":"突破确认 / 回踩承接"}

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

def analyze(q,include_flow=False):
    h=enrich_today(history(q["bs_code"]),q)
    t=technical(h)
    liquidity=clamp(45+math.log10(max(q["amount"]/1e8,1))*28)
    chase=max(0,100-max(q["pct"],0)*12)
    flow=try_eastmoney_flow(q["code"]) if include_flow else {"available":False,"main_yi":None,"large_yi":None,"super_yi":None,"positive_2":None}
    flow_score=50
    if flow["available"]:
        flow_score=clamp(50+(16 if flow["main_yi"]>0 else -10)+(10 if flow["positive_2"]==2 else 0))
    score=t["trend"]*.28+t["volume"]*.18+t["position"]*.18+liquidity*.16+chase*.10+flow_score*.10
    trig=t["trigger"] if t["trigger"] else q["price"]*1.01
    trig=min(max(trig,q["price"]*.998),q["price"]*1.035)
    support=t["support"] if t["support"] else trig*.975
    stop=min(trig*.975,support)
    buy_plan=make_buy_plan(q,t,trig,stop)
    bt=backtest_stats(h)
    rr1=(trig*1.035-trig)/max(trig-stop,.01)
    reasons=list(t["reasons"]); warnings=list(t["warnings"])
    if q["pct"]>4: warnings.append("当日涨幅偏高，禁止追价")
    if flow["available"] and flow["main_yi"]>0: reasons.append("主力资金净流入")
    if flow["available"] and flow["positive_2"]==2: reasons.append("连续2日资金回流")
    if buy_plan["state"]=="进入买点区" and score>=76:
        status="进入买点区"
    elif score>=70:
        status="重点观察"
    else:
        status="放弃"
    return {
        "code":q["code"],"name":q["name"],"price":round(q["price"],2),"pct":round(q["pct"],2),
        "amount_yi":round(q["amount"]/1e8,2),"quote_source":q["quote_source"],
        "score":round(score,1),"flow_score":round(flow_score),"trend_score":round(t["trend"]),
        "volume_score":round(t["volume"]),"position_score":round(t["position"]),"liquidity_score":round(liquidity),
        "volume_ratio":round(t["vr"],2),
        "trigger":round(trig,2),
        "buy_plan":buy_plan,
        "backtest":bt,
        "stop":round(stop,2),"target1":round(trig*1.035,2),"target2":round(trig*1.06,2),
        "rr1":round(rr1,2),"status":status,"reasons":reasons[:5],"warnings":warnings[:4],"fund_flow":flow
    }

def main():
    lg=bs.login()
    if lg.error_code!="0": raise RuntimeError("BaoStock 登录失败: "+lg.error_msg)
    try:
        universe=get_universe(); quotes,health=fetch_quotes(universe)
        if len(quotes)<2000: raise RuntimeError(f"实时行情股票数异常：{len(quotes)}，拒绝覆盖旧数据")
        by_code={x["code"]:x for x in quotes}; pcts=[x["pct"] for x in quotes]; up=sum(1 for p in pcts if p>0)/len(pcts)*100; med=median(pcts)
        market_score=round(clamp(45+(up-50)*.8+med*5)); market_state="偏强" if market_score>=65 else ("中性" if market_score>=45 else "偏弱")
        pre=[x for x in quotes if 5<=x["price"]<=30 and x["amount"]>=3e8 and -7.5<=x["pct"]<=5]
        for x in pre:
            liq=clamp(40+math.log10(max(x["amount"]/1e8,1))*28); chase=max(0,100-max(x["pct"],0)*12); x["_pre"]=liq*.55+chase*.45
        pre=sorted(pre,key=lambda z:z["_pre"],reverse=True)[:35]; candidates=[]
        for x in pre: candidates.append(analyze(x,include_flow=(len(candidates)<12)))
        candidates=sorted(candidates,key=lambda z:z["score"],reverse=True)
        watch=[analyze(by_code[c],include_flow=True) for c in WATCHLIST if c in by_code]
        source_health={"baostock":{"ok":len(universe)>2000,"count":len(universe),"role":"股票池/历史日K"},"quotes":{"ok":len(quotes)>2000,"count":len(quotes),"role":"实时行情","detail":health},"eastmoney_flow":{"ok":any(x["fund_flow"]["available"] for x in watch+candidates[:5]),"role":"资金流（可选增强）"}}
        now=datetime.now(CN).strftime("%Y-%m-%d %H:%M:%S")
        data={"version":"1.4","updated_at":now,"market":{"score":market_score,"state":market_state,"up_ratio":round(up,1),"median_pct":round(med,2),"universe":len(quotes)},"opportunities":[x for x in candidates if x["status"]!="放弃"][:5],"watchlist":watch,"candidates":candidates[:20],"source_health":source_health,"rules":{"price":"5-30元","amount":"≥3亿元","day_pct":"-7.5%~+5%","excluded":"科创/创业/北交/ST/退市","holding":"1-5个交易日"}}
        Path("data").mkdir(exist_ok=True); Path("data/latest.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        print("OK",now,"quotes",len(quotes),"opps",len(data["opportunities"]),"watch",len(watch))
    finally: bs.logout()

if __name__=="__main__": main()
