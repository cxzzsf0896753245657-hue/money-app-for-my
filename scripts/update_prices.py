#!/usr/bin/env python3
"""讀取 symbols.txt，抓最新股價，寫入 prices.json（只用 Python 標準函式庫）。
prices.json 會另外存每檔近半年的每日收盤價（h），供 app 的定期定額依扣款日換算。
symbols.txt 每行一檔：tw:2330（台股，含上櫃）、us:AAPL（美股）、sg:D05（新加坡股，不用加 .SI）或 fund:A36004（基金，鉅亨網代碼），# 開頭是註解。
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


def _d(ts, off=0):
    return datetime.datetime.fromtimestamp(ts + off, datetime.timezone.utc).date()


def history(mk, sym, today):
    """用 Yahoo 抓近 5 年每日資料（含還原股價與配息），算出：
    h     近 6 個月每日收盤價（定期定額依扣款日換算股數用）
    perf  近 1／3／5 年年化報酬（%，已含配息再投入）
    div   最近一次除息、近 12 個月配息與殖利率、預估下次除息日
    抓不到回傳 None。"""
    cands = {"tw": [sym + ".TW", sym + ".TWO"], "us": [sym], "sg": [sym if "." in sym else sym + ".SI"]}.get(mk, [])
    for y in cands:
        try:
            j = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{y}?range=5y&interval=1d&events=div")
            r = j["chart"]["result"][0]
            off = (r.get("meta") or {}).get("gmtoffset") or 0
            ts = r["timestamp"]
            close = r["indicators"]["quote"][0]["close"]
            adj = ((r["indicators"].get("adjclose") or [{}])[0] or {}).get("adjclose") or close
            rows = [(_d(t, off), c, a) for t, c, a in zip(ts, close, adj) if c and a]
            if not rows:
                continue
            td = datetime.date.fromisoformat(today)
            h = {d.isoformat(): round(c, 4) for d, c, _ in rows if (td - d).days <= 190}
            perf = {}
            last_d, _, last_a = rows[-1]
            for n in (1, 3, 5):
                cut = td - datetime.timedelta(days=round(365.25 * n))
                first = next(((d, a) for d, _, a in rows if d >= cut), None)
                if first and (first[0] - cut).days <= 10 and first[1] > 0 and last_d > first[0]:
                    perf[str(n)] = round(((last_a / first[1]) ** (1 / n) - 1) * 100, 2)
            divs = sorted(
                ((_d(v["date"], off), float(v["amount"])) for v in ((r.get("events") or {}).get("dividends") or {}).values() if v.get("amount")),
            )
            dv = None
            if divs:
                ttm = sum(a for d, a in divs if (td - d).days <= 365)
                price = rows[-1][1]
                dv = {"last": {"d": divs[-1][0].isoformat(), "a": round(divs[-1][1], 4)}, "ttm": round(ttm, 4),
                      "yld": round(ttm / price * 100, 2) if price else None}
                # 預估下次：把一年內的除息日各加一年，取最近的未來日期
                fut = sorted(d.replace(year=d.year + 1) if not (d.month == 2 and d.day == 29) else d.replace(year=d.year + 1, day=28)
                             for d, _ in divs if 0 <= (td - d).days <= 365)
                fut = [d for d in fut if d > td]
                if fut:
                    dv["next"] = {"d": fut[0].isoformat(), "est": True}
            return {"h": h, "perf": perf or None, "div": dv}
        except Exception as e:  # noqa: BLE001
            print(f"{mk}:{sym} 歷史資料失敗（{y}）：", e)
    return None


def fund_nav(code, pages=13):
    """鉅亨網基金淨值（非官方公開介面，可能改版失效）。回傳 {p, pv, d, h}，抓不到回傳 None。
    每頁 10 個交易日，預設抓 13 頁約半年，供定期定額換算。"""
    rows = []
    for pg in range(1, pages + 1):
        try:
            j = get(f"https://fund.api.cnyes.com/fund/api/v1/funds/{code}/nav?format=table&page={pg}")
        except Exception as e:  # noqa: BLE001
            if pg == 1:
                raise
            print(f"fund:{code} 第 {pg} 頁失敗：", e)
            break
        data = (j.get("items") or {}).get("data") or []
        for x in data:
            nav = num(x.get("nav"))
            if nav:
                d = datetime.datetime.fromtimestamp(int(x["tradeDate"]), TZ).date().isoformat()
                rows.append((d, nav))
        if len(data) < 10:
            break
    if not rows:
        return None
    rows.sort()
    d, p = rows[-1]
    pv = rows[-2][1] if len(rows) > 1 else None
    return {"p": p, "pv": pv, "d": d, "h": {a: b for a, b in rows}}


def roc_date(s):
    """民國日期 '1150120' 或 '115/01/20' → '2026-01-20'"""
    import re
    m = re.match(r"^(\d{2,3})\D?(\d{2})\D?(\d{2})$", str(s).strip())
    if not m:
        return None
    return f"{int(m.group(1)) + 1911:04d}-{m.group(2)}-{m.group(3)}"


def twt48u():
    """證交所除權除息預告表：回傳 {股票代號: (日期, 每股現金股利)}。抓不到回傳空。"""
    out = {}
    try:
        for x in get("https://openapi.twse.com.tw/v1/exchangeReport/TWT48U"):
            code = x.get("Code") or x.get("股票代號")
            d = roc_date(x.get("Date") or x.get("資料日期") or "")
            amt = num(x.get("CashDividend") or x.get("權值+息值") or x.get("Exdividend"))
            kind = str(x.get("權/息") or x.get("Exrights/Exdividend") or "")
            if code and d and (not kind or "息" in kind):
                out[code] = (d, amt)
    except Exception as e:  # noqa: BLE001
        print("證交所除權息預告表抓取失敗：", e)
    return out


def cpi():
    """台灣通膨率（近一年平均）。IMF DataMapper 公開 API，數據來源是主計總處，只有年度值。
    取已經結束的最近一年（今年以前）的年平均 CPI 年增率。"""
    j = get("https://www.imf.org/external/datamapper/api/v1/PCPIPCH/TWN")
    vals = j["values"]["PCPIPCH"]["TWN"]
    this_year = datetime.datetime.now(TZ).year
    years = sorted(int(y) for y in vals if int(y) < this_year and vals[y] is not None)
    y = years[-1]
    return {"v": round(float(vals[str(y)]), 2), "y": y, "src": "IMF／主計總處數據"}


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
        mk, sym = mk.strip().lower(), sym.strip().upper()
        if mk == "sg" and sym.endswith(".SI"):
            sym = sym[:-3]
        elif mk == "tw" and (sym.endswith(".TW") or sym.endswith(".TWO")):
            sym = sym.rsplit(".", 1)[0]
        wants.append((mk, sym))
    tw = tw_table() if any(m == "tw" for m, _ in wants) else {}
    tw_ex = twt48u() if any(m == "tw" for m, _ in wants) else {}
    got = 0
    for mk, sym in wants:
        q = None
        try:
            if mk == "tw":
                q = tw.get(sym)
            elif mk == "us":
                q = us_quote(sym)
            elif mk == "sg":
                q = us_quote(sym if "." in sym else sym + ".SI")
            elif mk == "fund":
                q = fund_nav(sym)
        except Exception as e:  # noqa: BLE001
            print(f"{mk}:{sym} 失敗：", e)
        if q and q.get("p"):
            old = prices.get(sym) or {}
            old_h = old.get("h") or {}
            info = (history(mk, sym, today) if mk != "fund" else {"h": q.pop("h", None)}) or {}
            old_h.update(info.get("h") or {})
            old_h[q.get("d") or today] = q["p"]
            keep = sorted(old_h)[-260:]
            prices[sym] = {k: v for k, v in {**q, "d": q.get("d") or today}.items() if v is not None}
            prices[sym]["h"] = {d: old_h[d] for d in keep}
            perf = info.get("perf") or old.get("perf")
            dv = info.get("div") or old.get("div")
            if mk == "tw" and sym in tw_ex:
                d, amt = tw_ex[sym]
                dv = dict(dv or {})
                dv["next"] = {k: v for k, v in {"d": d, "a": amt, "est": False}.items() if v is not None}
            if perf:
                prices[sym]["perf"] = perf
            if dv:
                prices[sym]["div"] = dv
            got += 1
        else:
            print(f"{mk}:{sym} 沒有抓到，保留舊價格")
    out = {"updated": today, "prices": prices}
    old_cpi = None
    if os.path.exists(out_file):
        try:
            old_cpi = json.load(open(out_file, encoding="utf-8")).get("cpi")
        except Exception:  # noqa: BLE001
            old_cpi = None
    try:
        out["cpi"] = {**cpi(), "d": today}
        print("通膨率：", out["cpi"])
    except Exception as e:  # noqa: BLE001
        print("通膨率抓取失敗，保留舊值：", e)
        if old_cpi:
            out["cpi"] = old_cpi
    json.dump(out, open(out_file, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"完成：更新 {got}/{len(wants)} 檔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
