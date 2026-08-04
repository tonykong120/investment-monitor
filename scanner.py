
import json, math, time, random, statistics
from pathlib import Path
from datetime import datetime, timezone, timedelta
import requests

CN = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"
S = requests.Session()
S.headers.update({
    "User-Agent": UA,
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "*/*",
})

def get_json(url, params=None, retries=4):
    last = None
    for i in range(retries):
        try:
            r = S.get(url, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(1.0 * (i+1) + random.random())
    raise RuntimeError(f"request failed: {last}")

def get_spot():
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn":"1","pz":"6000","po":"1","np":"1",
        "ut":"bd1d9ddb04089700cf9c27f6f7426281",
        "fltt":"2","invt":"2","fid":"f3",
        "fs":"m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields":"f2,f3,f6,f8,f10,f12,f14,f15,f16,f17,f18,f62,f184",
        "wbp2u":"|0|0|0|web"
    }
    j = get_json(url, params)
    return (j.get("data") or {}).get("diff") or []

def get_kline(code):
    secid = ("1." if str(code).startswith("6") else "0.") + str(code)
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid, "klt":"101","fqt":"1","beg":"0","end":"20500101","lmt":"45",
        "ut":"fa5fd1943c7b386f172d6893dbfba10b",
        "fields1":"f1,f2,f3,f4,f5,f6",
        "fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
    }
    j = get_json(url, params)
    ks = (j.get("data") or {}).get("klines") or []
    out=[]
    for s in ks:
        a=s.split(",")
        if len(a)>=11:
            out.append({"d":a[0],"o":float(a[1]),"c":float(a[2]),"h":float(a[3]),"l":float(a[4]),
                        "v":float(a[5]),"amt":float(a[6]),"pct":float(a[8]),"turn":float(a[10])})
    return out

def mean(xs):
    xs=[x for x in xs if x is not None and math.isfinite(x)]
    return sum(xs)/len(xs) if xs else None

def clamp(x,a=0,b=100): return max(a,min(b,x))

def allowed(code,name):
    code=str(code).zfill(6)
    if code.startswith(("688","300","301","8","4")): return False
    if "ST" in str(name) or "退" in str(name): return False
    return True

def hist_score(h):
    if len(h)<20:
        return {"trend":50,"volume":50,"position":50,"trigger":None,"support":None}
    c=[x["c"] for x in h]; v=[x["v"] for x in h]
    last=c[-1]; ma5=mean(c[-5:]); ma10=mean(c[-10:]); ma20=mean(c[-20:])
    trend=50+(15 if last>ma5 else -8)+(12 if ma5>ma10 else -6)+(10 if ma10>ma20 else -5)
    vr=v[-1]/max(mean(v[-6:-1]) or 1,1)
    volume=clamp(45+(vr-1)*35)
    hi=max(c[-20:]); lo=min(c[-20:]); p=(last-lo)/max(hi-lo,1e-9)
    position=clamp(100-abs(p-.55)*120)
    trigger=max(max(x["h"] for x in h[-3:-1]), ma5)
    support=min(min(x["l"] for x in h[-5:]), ma10)
    return {"trend":clamp(trend),"volume":volume,"position":position,"trigger":trigger,"support":support}

def med(xs):
    xs=sorted([x for x in xs if x is not None and math.isfinite(x)])
    return statistics.median(xs) if xs else 0

def scan():
    raw=get_spot()
    all_rows=[]
    for x in raw:
        try:
            code=str(x.get("f12","")).zfill(6); name=x.get("f14","")
            p=float(x.get("f2")); pct=float(x.get("f3")); amt=float(x.get("f6"))
            turn=float(x.get("f8") or 0); vr=float(x.get("f10") or 1)
            main=float(x.get("f62") or 0); main_pct=float(x.get("f184") or 0)
            if allowed(code,name):
                all_rows.append(dict(code=code,name=name,price=p,pct=pct,amt=amt,turn=turn,vr=vr,main=main,main_pct=main_pct))
        except Exception:
            pass

    pcts=[x["pct"] for x in all_rows]
    up=100*sum(1 for p in pcts if p>0)/max(len(pcts),1)
    md=med(pcts)
    market_score=round(clamp(45+(up-50)*.8+md*5))

    pre=[x for x in all_rows if 5<=x["price"]<=30 and x["amt"]>=5e8 and x["turn"]>=1 and -7.5<=x["pct"]<=5]
    for x in pre:
        liq=min(100,35+math.log10(max(x["amt"]/1e8,1))*22+min(x["turn"],12)*2.3)
        flow=50+(18 if x["main"]>0 else -10)+max(-15,min(15,x["main_pct"]*2.5))
        chase=max(0,100-max(x["pct"],0)*12)
        active=clamp(45+(x["vr"]-1)*30)
        x["pre"]=.30*liq+.30*flow+.20*chase+.20*active
    pre=sorted(pre,key=lambda z:z["pre"],reverse=True)[:30]

    out=[]
    for i,x in enumerate(pre):
        try:
            h=get_kline(x["code"]); hs=hist_score(h)
        except Exception:
            hs={"trend":50,"volume":50,"position":50,"trigger":None,"support":None}
        flow=clamp(50+(18 if x["main"]>0 else -10)+max(-15,min(15,x["main_pct"]*2.5)))
        liq=min(100,35+math.log10(max(x["amt"]/1e8,1))*22+min(x["turn"],12)*2.3)
        chase=max(0,100-max(x["pct"],0)*12)
        score=flow*.28+hs["trend"]*.22+hs["volume"]*.15+hs["position"]*.15+liq*.10+chase*.10
        trig=hs["trigger"] if hs["trigger"] is not None else x["price"]*1.01
        trig=min(max(trig,x["price"]*.998),x["price"]*1.035)
        support=hs["support"] if hs["support"] is not None else trig*.975
        stop=min(trig*.975,support)
        status="可买触发" if score>=82 and x["price"]>=trig*.995 else ("重点观察" if score>=72 else "放弃")
        out.append({
            "code":x["code"],"name":x["name"],"price":round(x["price"],2),"pct":round(x["pct"],2),
            "amount_yi":round(x["amt"]/1e8,2),"turn":round(x["turn"],2),"main_yi":round(x["main"]/1e8,2),
            "score":round(score,1),"flow_score":round(flow),"trend_score":round(hs["trend"]),
            "volume_score":round(hs["volume"]),"position_score":round(hs["position"]),
            "trigger":round(trig,2),"stop":round(stop,2),
            "target1":round(trig*1.03,2),"target2":round(trig*1.05,2),"status":status
        })
        time.sleep(.08)

    out=sorted(out,key=lambda z:z["score"],reverse=True)
    now=datetime.now(CN)
    return {
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "market":{"score":market_score,"up_ratio":round(up,1),"median_pct":round(md,2),"universe":len(all_rows)},
        "opportunities":[x for x in out if x["status"]!="放弃"][:3],
        "candidates":out[:20],
        "rules":{"price":"5-30元","amount":"≥5亿元","turnover":"≥1%","day_pct":"-7.5%~+5%","excluded":"科创/创业/北交/ST/退市"}
    }

if __name__=="__main__":
    result=scan()
    p=Path("data/latest.json")
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("saved",p,result["updated_at"],len(result["opportunities"]))
