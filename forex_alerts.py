#!/usr/bin/env python3
"""Meridian Signal alerts (same rules as the Meridian Signal app).

Sends a Telegram message when a pair BECOMES ready to trade. A pair is ready when:
  1. signal strength is at least MIN_CONF
  2. EMA trend and MACD momentum both point the same way as the trade
  3. ADX is 20 or more (the market is trending)
  4. the higher timeframe trend agrees (H1 looks at H4, H4 looks at D1)
  5. price is not overextended (RSI under 72 for buys, over 28 for sells)
  6. the stop is at least 8 pips, wider than a normal spread
  7. on H1 only: it is London or New York hours (07:00 to 17:00 UTC)

Standard library only.

Environment variables:
  TWELVEDATA_KEY     free key from twelvedata.com
  TELEGRAM_TOKEN     bot token from @BotFather
  TELEGRAM_CHAT_ID   your chat id
  INTERVAL           1h (default), 4h or 1day
  MIN_CONF           default 65
  ACCOUNT_BALANCE    default 5000
  RISK_PCT           default 1

Usage:
  python forex_alerts.py          run once, send alerts, skip when the market is closed
  python forex_alerts.py --test   send a test message
  python forex_alerts.py --demo   fake candles, print alerts, no keys needed
"""
import datetime
import json
import math
import os
import random
import sys
import time
import urllib.parse
import urllib.request

PAIRS = [  # symbol, pip size, approx. USD per pip per standard lot, decimals, demo bias
    ("EUR/USD", 0.0001, 10.0, 5, 1.0),
    ("GBP/USD", 0.0001, 10.0, 5, -1.0),
    ("USD/JPY", 0.01, 6.5, 3, 1.0),
    ("AUD/USD", 0.0001, 10.0, 5, 0.0),
    ("USD/CAD", 0.0001, 7.15, 5, 0.4),
    ("GBP/JPY", 0.01, 6.5, 3, -0.3),
]

# Approximate USD value of one unit of each currency (same table as the app). Used for lot sizes only.
CCY = {"USD": 1, "EUR": 1.10, "GBP": 1.27, "AUD": 0.65, "NZD": 0.60, "CAD": 0.72, "CHF": 1.12, "JPY": 0.0065,
       "SEK": 0.095, "NOK": 0.093, "DKK": 0.147, "SGD": 0.75, "HKD": 0.128, "MXN": 0.055, "ZAR": 0.055, "TRY": 0.03,
       "CNH": 0.14, "PLN": 0.25, "CZK": 0.043, "HUF": 0.0028, "THB": 0.028, "INR": 0.012, "ILS": 0.27, "KRW": 0.00072,
       "NGN": 0.00066, "CNY": 0.14, "BRL": 0.18, "RUB": 0.011, "AED": 0.272, "SAR": 0.267, "TWD": 0.031}


def make_pair(sym):
    """Same rules as the app. Returns (symbol, pip, pip value, decimals, bias) or None."""
    sym = sym.strip().upper().replace(" ", "")
    if len(sym) == 6 and "/" not in sym:
        sym = sym[:3] + "/" + sym[3:]
    for p in PAIRS:
        if p[0] == sym:
            return p
    a, _, b = sym.partition("/")
    if len(a) != 3 or len(b) != 3 or a == b or a not in CCY or b not in CCY:
        return None
    base = CCY[a] / CCY[b]
    pip = 0.01 if base >= 20 else 0.0001
    return (sym, pip, round(100000 * pip * CCY[b], 2), 3 if pip == 0.01 else 5, 0.0)


def watchlist():
    raw = os.environ.get("PAIRS", "").strip()
    if not raw:
        return PAIRS
    out = []
    for part in raw.replace(";", ",").split(","):
        pr = make_pair(part)
        if pr:
            out.append(pr)
        elif part.strip():
            print(f"Ignoring unknown pair: {part.strip()}")
    return out or PAIRS
HTF = {"1min": "5min", "5min": "15min", "15min": "30min", "30min": "1h", "1h": "4h", "4h": "1day", "1day": None, "1week": None}
HTF_LABEL = {"5min": "M5", "15min": "M15", "30min": "M30", "1h": "H1", "4h": "H4", "1day": "D1"}
TF_LABEL = {"1min": "M1", "5min": "M5", "15min": "M15", "30min": "M30", "1h": "H1", "4h": "H4", "1day": "D1", "1week": "W1"}
TF_MS = {"1min": 60000, "5min": 300000, "15min": 900000, "30min": 1800000, "1h": 3600000, "4h": 14400000, "1day": 86400000, "1week": 604800000}
INTRADAY = {"1min", "5min", "15min", "30min", "1h"}      # these also require London / New York hours
MIN_STOP = {"1min": 4, "5min": 6, "15min": 8, "30min": 8}  # pips, everything else uses 8
SL_ATR, TP1_ATR, TP2_ATR = 1.5, 2.25, 3.75


def market_open(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    day, hour = now.weekday(), now.hour  # Monday is 0
    if day == 5:
        return False
    if day == 4 and hour >= 21:
        return False
    if day == 6 and hour < 22:
        return False
    return True


# ---------- indicators ----------

def ema(values, n):
    k = 2 / (n + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(closes, n=14):
    gain = loss = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gain += d
        else:
            loss -= d
    gain /= n
    loss /= n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        gain = (gain * (n - 1) + max(d, 0)) / n
        loss = (loss * (n - 1) + max(-d, 0)) / n
    return 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)


def true_ranges(c):
    return [max(c[i]["h"] - c[i]["l"], abs(c[i]["h"] - c[i - 1]["c"]), abs(c[i]["l"] - c[i - 1]["c"]))
            for i in range(1, len(c))]


def atr(candles, n=14):
    tr = true_ranges(candles)
    a = sum(tr[:n]) / n
    for t in tr[n:]:
        a = (a * (n - 1) + t) / n
    return a


def adx(candles, n=14):
    tr = true_ranges(candles)
    pdm, mdm = [], []
    for i in range(1, len(candles)):
        up = candles[i]["h"] - candles[i - 1]["h"]
        down = candles[i - 1]["l"] - candles[i]["l"]
        pdm.append(up if up > down and up > 0 else 0)
        mdm.append(down if down > up and down > 0 else 0)
    s_tr, s_p, s_m = sum(tr[:n]), sum(pdm[:n]), sum(mdm[:n])

    def dx():
        pi = 100 * s_p / (s_tr or 1e-12)
        mi = 100 * s_m / (s_tr or 1e-12)
        return 100 * abs(pi - mi) / ((pi + mi) or 1e-12)

    dxs = [dx()]
    for i in range(n, len(tr)):
        s_tr = s_tr - s_tr / n + tr[i]
        s_p = s_p - s_p / n + pdm[i]
        s_m = s_m - s_m / n + mdm[i]
        dxs.append(dx())
    if len(dxs) < n:
        return dxs[-1]
    a = sum(dxs[:n]) / n
    for d in dxs[n:]:
        a = (a * (n - 1) + d) / n
    return a


def analyse(candles):
    closes = [c["c"] for c in candles]
    e20, e50 = ema(closes, 20), ema(closes, 50)
    m12, m26 = ema(closes, 12), ema(closes, 26)
    macd = [a - b for a, b in zip(m12, m26)]
    hist = macd[-1] - ema(macd, 9)[-1]
    r = rsi(closes)
    window = closes[-20:]
    mean = sum(window) / len(window)
    sd = math.sqrt(sum((x - mean) ** 2 for x in window) / len(window))
    upper, lower = mean + 2 * sd, mean - 2 * sd
    last = closes[-1]
    pb = (last - lower) / ((upper - lower) or 1e-9)
    trend = 1 if e20[-1] > e50[-1] else -1
    mom = 1 if hist > 0 else -1
    rs = 1.0 if r < 30 else -1.0 if r > 70 else max(-0.8, min(0.8, (r - 50) / 25))
    bs = 0.5 if pb < 0.1 else -0.5 if pb > 0.9 else 0.0
    score = (trend + mom + rs + bs) / 3.5
    return {
        "signal": "BUY" if score >= 0.4 else "SELL" if score <= -0.4 else "WAIT",
        "conf": round(abs(score) * 100), "last": last, "atr": atr(candles),
        "adx": adx(candles), "rsi": r, "trend": trend, "mom": mom,
    }


def readiness(res, pip, htf_res, min_conf, session=False, now=None, min_stop=8):
    """Returns (ready, reason). htf_res is None when no higher timeframe applies."""
    if res["signal"] == "WAIT":
        return False, "no clear direction"
    d = 1 if res["signal"] == "BUY" else -1
    sl_pips = SL_ATR * res["atr"] / pip
    if res["conf"] < min_conf:
        return False, f"signal strength {res['conf']}%"
    if res["trend"] != d or res["mom"] != d:
        return False, "trend and momentum disagree"
    if res["adx"] < 20:
        return False, f"weak trend (ADX {res['adx']:.0f})"
    if htf_res is not None and htf_res["trend"] != d:
        return False, "higher timeframe disagrees"
    if (d > 0 and res["rsi"] >= 72) or (d < 0 and res["rsi"] <= 28):
        return False, f"overextended (RSI {res['rsi']:.0f})"
    if sl_pips < min_stop:
        return False, f"stop only {sl_pips:.1f} pips"
    if session:
        now = now or datetime.datetime.now(datetime.timezone.utc)
        hh = now.hour + now.minute / 60
        if not (7 <= hh < 17):
            return False, "outside London and New York hours"
    return True, "ready"


# ---------- data ----------

def fetch_candles(symbol, interval, key):
    qs = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "outputsize": 120, "apikey": key})
    with urllib.request.urlopen("https://api.twelvedata.com/time_series?" + qs, timeout=30) as resp:
        data = json.load(resp)
    if data.get("status") != "ok" or "values" not in data:
        raise RuntimeError(data.get("message", "unexpected response"))
    rows = list(reversed(data["values"]))
    candles = [{"t": v["datetime"], "o": float(v["open"]), "h": float(v["high"]), "l": float(v["low"]), "c": float(v["close"])}
               for v in rows]
    return candles[:-1]  # drop the candle that is still forming


DEMO_SEED = 8


def demo_candles(symbol, bias, interval):
    mult = {"1min": 0.14, "5min": 0.30, "15min": 0.55, "30min": 0.75, "1h": 1.0, "4h": 1.9, "1day": 3.6, "1week": 6.5}[interval]
    rnd = random.Random(f"{symbol}{interval}{DEMO_SEED}")
    base = 150.0 if symbol.endswith("JPY") else 1.1
    vol = base * 0.0006 * mult
    out, c = [], base
    for i in range(121):
        o = c
        c = o + (rnd.uniform(-1, 1) + bias * 0.2) * vol
        out.append({"o": o, "c": c, "h": max(o, c) + rnd.random() * vol, "l": min(o, c) - rnd.random() * vol})
    return out


# ---------- messaging ----------

def build_message(symbol, pip, pip_value, dec, res, interval, balance, risk_pct, htf_res):
    d = 1 if res["signal"] == "BUY" else -1
    entry = res["last"]
    sl = entry - d * SL_ATR * res["atr"]
    tp1 = entry + d * TP1_ATR * res["atr"]
    tp2 = entry + d * TP2_ATR * res["atr"]
    sl_pips = abs(entry - sl) / pip
    risk_usd = balance * risk_pct / 100
    lots = max(0.01, math.floor(risk_usd / (sl_pips * pip_value) * 100) / 100)
    f = lambda v: f"{v:.{dec}f}"
    htf_line = ""
    if htf_res is not None:
        htf_line = f"{HTF_LABEL[HTF[interval]]} trend agrees\n"
    return (
        f"MERIDIAN READY: {res['signal']} {symbol} ({TF_LABEL[interval]})\n"
        f"Strength {res['conf']}%, ADX {res['adx']:.0f}, RSI {res['rsi']:.0f}\n"
        f"{htf_line}"
        f"Entry {f(entry)}\n"
        f"Stop loss {f(sl)} ({sl_pips:.1f} pips)\n"
        f"Take profit 1 {f(tp1)} (1.5R)\n"
        f"Take profit 2 {f(tp2)} (2.5R)\n"
        f"Size about {lots:.2f} lots for ${risk_usd:,.2f} risk\n"
        f"Not financial advice."
    )


def send_telegram(token, chat_id, text):
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body)
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def send_ntfy(topic, text):
    """Push to the free ntfy app. No account needed: the topic name is the password."""
    title = text.split("\n", 1)[0].encode("ascii", "ignore").decode() or "Meridian Signal"
    req = urllib.request.Request(
        "https://ntfy.sh/" + urllib.parse.quote(topic, safe=""),
        data=text.encode("utf-8"),
        headers={"Title": title, "Priority": "high", "Tags": "chart_with_upwards_trend"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def push(token, chat_id, topic, text):
    """Send to every channel that is set up."""
    if topic:
        send_ntfy(topic, text)
    if token and chat_id:
        send_telegram(token, chat_id, text)


# ---------- main ----------

def main():
    args = set(sys.argv[1:])
    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    key = os.environ.get("TWELVEDATA_KEY", "")
    interval = os.environ.get("INTERVAL", "1h")
    min_conf = float(os.environ.get("MIN_CONF", "65"))
    balance = float(os.environ.get("ACCOUNT_BALANCE", "5000"))
    risk_pct = float(os.environ.get("RISK_PCT", "1"))
    demo = "--demo" in args
    if interval not in HTF:
        sys.exit("INTERVAL must be 1min, 5min, 15min, 30min, 1h, 4h, 1day or 1week")

    if "--test" in args:
        push(token, chat_id, topic, "Meridian Signal is connected\nYou will get a message when a trade is ready.")
        print("Test message sent.")
        return
    if not demo and not (key and (topic or (token and chat_id))):
        sys.exit("Set TWELVEDATA_KEY and NTFY_TOPIC (or TELEGRAM_TOKEN and TELEGRAM_CHAT_ID), or run with --demo.")
    if not demo and not market_open():
        print("Market closed, nothing to do.")
        return

    htf_interval = HTF[interval]
    sent = 0
    state_path = os.environ.get("STATE_FILE", "state/alerts.json")
    try:
        with open(state_path) as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        state = {}
    now_ms = int(time.time() * 1000)
    ms = TF_MS[interval]
    if not demo:
        # Nothing new to look at unless a candle has closed since the last real run.
        boundary = ((now_ms - 60000) // ms) * ms
        if state.get("_last_run", {}).get(interval, 0) >= boundary + 60000:
            print("No new candle yet, nothing to do.")
            return
    pause = 0 if demo else 8.7   # free Twelve Data keys allow 8 calls a minute
    for symbol, pip, pip_value, dec, bias in watchlist():
        try:
            if demo:
                now_c = demo_candles(symbol, bias, interval)
                prev_c = now_c[:-1]
            else:
                now_c = fetch_candles(symbol, interval, key)
                prev_c = now_c[:-1]
                time.sleep(pause)
            now = analyse(now_c)
            prev = analyse(prev_c)
            htf_res = None
            if htf_interval and (now["signal"] != "WAIT"):
                htf_c = demo_candles(symbol, bias, htf_interval) if demo else fetch_candles(symbol, htf_interval, key)
                htf_res = analyse(htf_c)
                time.sleep(pause)
            session = interval in INTRADAY and not demo
            min_stop = MIN_STOP.get(interval, 8)
            ready_now, why = readiness(now, pip, htf_res, min_conf, session, None, min_stop)
            # was it ready one candle ago? (uses the same higher timeframe read)
            ready_before, _ = readiness(prev, pip, htf_res, min_conf, False, None, min_stop)
        except Exception as exc:  # keep going if one pair fails
            print(f"{symbol}: skipped ({exc})")
            continue
        print(f"{symbol}: {now['signal']} {now['conf']}%  {'READY' if ready_now else 'waiting: ' + why}")
        skey = f"{symbol}|{interval}"
        last_alert = state.get(skey, {})
        candle_t = now_c[-1].get("t", len(now_c))
        repeat = (last_alert.get("t") == candle_t) or (
            last_alert.get("sig") == now["signal"] and now_ms - last_alert.get("at", 0) < 4 * ms)
        if ready_now and not (ready_before and prev["signal"] == now["signal"]) and not repeat:
            state[skey] = {"t": candle_t, "sig": now["signal"], "at": now_ms}
            msg = build_message(symbol, pip, pip_value, dec, now, interval, balance, risk_pct, htf_res)
            if demo:
                print("\n" + msg + "\n")
            else:
                push(token, chat_id, topic, msg)
            sent += 1
    if not demo:
        state.setdefault("_last_run", {})[interval] = now_ms
        os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
        with open(state_path, "w") as fh:
            json.dump(state, fh)
    print(f"Done. {sent} alert(s).")


if __name__ == "__main__":
    main()
