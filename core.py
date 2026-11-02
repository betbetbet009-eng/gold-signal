# ส่วนกลาง: ดึงข้อมูลทอง, สร้างแท่ง 4H ให้ตรงกับ OANDA บน TradingView, คำนวณอินดิเคเตอร์, backtest, ส่งแจ้งเตือน
import base64, json, os, urllib.request
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
PARAMS_FILE = os.path.join(ROOT, "params.json")
FEE = 0.0006


def get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0", **(headers or {})})
    return urllib.request.urlopen(req, timeout=30).read()


def load_params():
    return json.load(open(PARAMS_FILE, encoding="utf-8"))


def save_params(p):
    json.dump(p, open(PARAMS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def to_4h(df):
    # แท่ง 4H ของ OANDA บน TradingView เริ่ม 17:00 เวลานิวยอร์ก (17, 21, 01, 05, 09, 13)
    # จัดกลุ่มตามเวลานาฬิกานิวยอร์ก (รองรับการเปลี่ยน Daylight Saving)
    s = df.set_index("t")
    s.index = s.index.tz_localize("UTC").tz_convert("America/New_York").tz_localize(None)
    s = s.resample("4h", offset="1h").agg(dict(o="first", h="max", l="min", c="last")).dropna()
    s.index = s.index.tz_localize("America/New_York", ambiguous=True, nonexistent="shift_forward").tz_convert("UTC").tz_localize(None)
    return s.reset_index()


def gold_1h(days=60):
    r = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1h&range={days}d"))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    return pd.DataFrame(dict(t=pd.to_datetime(r["timestamp"], unit="s"), o=q["open"], h=q["high"], l=q["low"], c=q["close"])).dropna()


def paxg_4h(start="2020-09-01"):
    out, t = [], int(pd.Timestamp(start).timestamp() * 1000)
    while True:
        d = json.loads(get(f"https://data-api.binance.vision/api/v3/klines?symbol=PAXGUSDT&interval=1h&startTime={t}&limit=1000"))
        if not d:
            break
        out += d
        t = d[-1][0] + 1
        if len(d) < 1000:
            break
    df = pd.DataFrame(out).iloc[:, :5].astype(float)
    df.columns = ["t", "o", "h", "l", "c"]
    df["t"] = pd.to_datetime(df["t"], unit="ms")
    return to_4h(df)


def ema(x, n): return pd.Series(x).ewm(span=n, adjust=False).mean().values
def rma(x, n): return pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().values


def atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    return rma(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc))), n)


def adx(h, l, c, n=14):
    up = np.diff(h, prepend=h[0]); dn = -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0); ndm = np.where((dn > up) & (dn > 0), dn, 0)
    a = atr(h, l, c, n); pdi = 100 * rma(pdm, n) / a; ndi = 100 * rma(ndm, n) / a
    return rma(100 * abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-12), n)


def signals(df, p):
    h, l, c = df.h.values, df.l.values, df.c.values
    hh = pd.Series(h).rolling(p["n"]).max().shift(1).values
    ll = pd.Series(l).rolling(p["n"]).min().shift(1).values
    e200, e20, e50 = ema(c, 200), ema(c, 20), ema(c, 50)
    ax = adx(h, l, c)
    up = (c > e200) & (e20 > e50) & (ax > p["adx"])
    dn = (c < e200) & (e20 < e50) & (ax > p["adx"])
    long = up & (c > hh)
    short = dn & (c < ll) & bool(p.get("allow_short"))
    return long, short, atr(h, l, c), hh, ll


def backtest(df, p, start=None, end=None):
    o, h, l, c, t = df.o.values, df.h.values, df.l.values, df.c.values, df.t.values
    long, short, a, _, _ = signals(df, p)
    i0 = max(250, np.searchsorted(t, np.datetime64(start)) if start else 0)
    i1 = np.searchsorted(t, np.datetime64(end)) if end else len(c)
    Rs, i = [], i0
    while i < i1 - 1:
        if long[i] or short[i]:
            d = 1 if long[i] else -1
            ent = o[i + 1]; sd = p["sl"] * a[i]
            sl, tp = ent - d * sd, ent + d * sd * p["rr"]
            j, R = i + 1, None
            while j < i1:
                if (l[j] <= sl) if d == 1 else (h[j] >= sl): R = -1; break
                if (h[j] >= tp) if d == 1 else (l[j] <= tp): R = p["rr"]; break
                j += 1
            if R is None:
                R = d * (c[i1 - 1] - ent) / sd; j = i1 - 1
            Rs.append(R - 2 * FEE * ent / sd); i = j + 1; continue
        i += 1
    Rs = np.array(Rs)
    return dict(n=len(Rs), wr=float((Rs > 0).mean()) if len(Rs) else 0.0, exp=float(Rs.mean()) if len(Rs) else 0.0)


def lot_for(p, sl_dist):
    usd_per_lot = sl_dist * 100 / (100 if p.get("account") == "Cent" else 1)
    return np.floor(p["balance"] * p["risk_pct"] / 100 / usd_per_lot * 100) / 100, usd_per_lot * 0.01


def notify(title, msg, tags="chart_with_upwards_trend", priority="high"):
    topic = os.environ.get("NTFY_TOPIC")
    print(f"--- notify: {title}\n{msg}")
    if not topic:
        return
    enc_title = "=?UTF-8?B?" + base64.b64encode(title.encode("utf-8")).decode() + "?="
    get(f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"),
        headers={"Title": enc_title, "Tags": tags, "Priority": priority})
