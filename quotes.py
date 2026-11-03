"""
quotes.py - fetch fresh NSE prices and write them where a static dashboard can read them.

Why it works this way: a browser opening a local HTML file cannot call NSE or
Yahoo directly. Both block cross-origin requests, and NSE additionally sits
behind Akamai bot detection that rejects non-browser TLS fingerprints. So the
fetch happens server-side (here, or in GitHub Actions), and the result is written
as a plain JS file that the dashboard loads with a <script> tag - no CORS, no
fetch(), works from file:// and from GitHub Pages alike.

Sources, in the order they are tried, all verified working:
  1. NSE NextApi GetQuoteApi  - NSE's own live route (lastPrice, previousClose)
  2. Yahoo Finance v8 chart   - fallback (regularMarketPrice, chartPreviousClose)
Index regime: NSE /api/allIndices for the NIFTY 50 level, Yahoo ^NSEI for its
200-day average.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

SYMBOLS = ["TRENT", "BEL", "DIXON", "BHARTIARTL",
           "PERSISTENT", "HAL", "CHOLAFIN", "FEDERALBNK"]

NSE_QUOTE = ("https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi"
             "?functionName=getSymbolData&marketType=N&series=EQ&symbol={sym}")
YAHOO_CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}.NS"
               "?interval=1d&range=5d")


def _get(url, referer=None, timeout=20):
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def from_nse(sym):
    """NSE's own live quote route."""
    d = _get(NSE_QUOTE.format(sym=sym),
             referer=f"https://www.nseindia.com/get-quotes/equity")
    row = d["equityResponse"][0]
    price = row.get("orderBook", {}).get("lastPrice")
    prev = row.get("metaData", {}).get("previousClose")
    if not price:
        raise ValueError("no lastPrice in NSE response")
    return {"price": float(price),
            "prevClose": float(prev) if prev else None,
            "source": "NSE"}


def from_yahoo(sym):
    d = _get(YAHOO_CHART.format(sym=sym))
    m = d["chart"]["result"][0]["meta"]
    price = m.get("regularMarketPrice")
    prev = m.get("chartPreviousClose") or m.get("previousClose")
    if not price:
        raise ValueError("no regularMarketPrice in Yahoo response")
    return {"price": float(price),
            "prevClose": float(prev) if prev else None,
            "source": "Yahoo"}


def quote(sym):
    for fn in (from_nse, from_yahoo):
        try:
            q = fn(sym)
            q["symbol"] = sym
            if q["prevClose"]:
                q["pctChange"] = round((q["price"] / q["prevClose"] - 1) * 100, 2)
            return q
        except Exception as e:
            print(f"[warn] {sym} via {fn.__name__}: {type(e).__name__}: {e}",
                  file=sys.stderr)
        time.sleep(0.4)
    return None


def nifty_regime():
    """NIFTY 50 level from NSE, and whether it sits above its 200-day average."""
    level = None
    try:
        d = _get("https://www.nseindia.com/api/allIndices")
        for row in d.get("data", []):
            if row.get("index") == "NIFTY 50":
                level = float(row["last"])
                break
    except Exception as e:
        print(f"[warn] NSE allIndices: {e}", file=sys.stderr)

    sma200 = None
    try:
        d = _get("https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI"
                 "?interval=1d&range=2y")
        closes = [c for c in d["chart"]["result"][0]["indicators"]["quote"][0]["close"]
                  if c is not None]
        if len(closes) >= 200:
            sma200 = round(sum(closes[-200:]) / 200, 2)
            if level is None:
                level = round(closes[-1], 2)
    except Exception as e:
        print(f"[warn] Yahoo ^NSEI: {e}", file=sys.stderr)

    bull = None if (level is None or sma200 is None) else bool(level > sma200)
    return level, sma200, bull


def main():
    now = datetime.now(IST)
    quotes, failures = {}, []

    for sym in SYMBOLS:
        q = quote(sym)
        if q:
            quotes[sym] = q
            print(f"[ok]   {sym:12s} {q['price']:>10,.2f}  "
                  f"({q.get('pctChange', 0):+.2f}%)  {q['source']}")
        else:
            failures.append(sym)
            print(f"[FAIL] {sym}")

    level, sma200, bull = nifty_regime()
    print(f"[ok]   NIFTY 50 {level} vs 200DMA {sma200} -> "
          f"{'bullish' if bull else 'bearish' if bull is False else 'unknown'}")

    payload = {
        "asOfIST": now.strftime("%d %b %Y %H:%M"),
        "generatedISO": now.isoformat(),
        "source": "NSE NextApi + Yahoo fallback",
        "quotes": quotes,
        "failed": failures,
        "nifty": {"level": level, "sma200": sma200, "regimeBull": bull},
        "regimeBull": bull,
    }

    os.makedirs("data", exist_ok=True)
    with open("data/quotes.json", "w") as f:
        json.dump(payload, f, indent=2)
    # JS wrapper so a local file:// dashboard can load it with a <script> tag.
    with open("data/quotes.js", "w") as f:
        f.write("window.MARKET_QUOTES = ")
        json.dump(payload, f, indent=2)
        f.write(";\n")

    print(f"[done] {len(quotes)}/{len(SYMBOLS)} quotes -> data/quotes.js")
    if failures:
        print(f"[done] failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
