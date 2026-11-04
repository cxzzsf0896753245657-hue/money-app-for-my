#!/usr/bin/env python3
"""讀取 symbols.txt，抓最新股價，寫入 prices.json（只用 Python 標準函式庫）。
symbols.txt 每行一檔：tw:2330（台股，含上櫃）或 us:AAPL（美股），# 開頭是註解。
抓不到的代號會保留 prices.json 裡上一次的價格。"""
import json, os, sys, urllib.request, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZ = datetime.timezone(datetime.timedelta(hours=8))


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def tw_table():
    out = {}
    try:
        for x in get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"):
            code, p, ch = x.get("Code"), num(x.get("ClosingPrice")), num(x.get("Change"))
            if code and p:
                out[code] = {"p": p, "pv": round(p - ch, 4) if ch is not None else None}
    except Exception as e:  # noqa: BLE001
        print("證交所抓取失敗：", e)
    try:
        for x in get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"):
            code = x.get("SecuritiesCompanyCode") or x.get("Code")
            p, ch = num(x.get("Close") or x.get("ClosingPrice")), num(x.get("Change"))
            if code and p and code not in out:
                out[code] = {"p": p, "pv": round(p - ch, 4) if ch is not None else None}
    except Exception as e:  # noqa: BLE001
        print("櫃買中心抓取失敗：", e)
    return out


def us_quote(sym):
    j = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=1d")
    m = j["chart"]["result"][0]["meta"]
    p = num(m.get("regularMarketPrice"))
    pv = num(m.get("chartPreviousClose") or m.get("previousClose"))
    return {"p": p, "pv": pv} if p else None


def main():
    today = datetime.datetime.now(TZ).date().isoformat()
    sym_file = os.path.join(ROOT, "symbols.txt")
    out_file = os.path.join(ROOT, "prices.json")
    prices = {}
    if os.path.exists(out_file):
        try:
            prices = json.load(open(out_file, encoding="utf-8")).get("prices", {})
        except Exception:  # noqa: BLE001
            prices = {}
    wants = []
    for line in open(sym_file, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        mk, sym = line.split(":", 1)
        wants.append((mk.strip().lower(), sym.strip().upper()))
    tw = tw_table() if any(m == "tw" for m, _ in wants) else {}
    got = 0
    for mk, sym in wants:
        q = None
        try:
            q = tw.get(sym) if mk == "tw" else us_quote(sym) if mk == "us" else None
        except Exception as e:  # noqa: BLE001
            print(f"{mk}:{sym} 失敗：", e)
        if q and q.get("p"):
            prices[sym] = {k: v for k, v in {**q, "d": today}.items() if v is not None}
            got += 1
        else:
            print(f"{mk}:{sym} 沒有抓到，保留舊價格")
    json.dump({"updated": today, "prices": prices}, open(out_file, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"完成：更新 {got}/{len(wants)} 檔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
