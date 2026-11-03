# ส่วนกลาง: ดึงข้อมูลทอง, สร้างแท่งให้ตรงกับ OANDA บน TradingView, คำนวณอินดิเคเตอร์, backtest, ส่งแจ้งเตือน
import base64, json, os, urllib.request
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
PARAMS_FILE = os.path.join(ROOT, "params.json")
COST = 0.30  # สเปรด+slippage ไป-กลับ (ดอลลาร์ต่อออนซ์)


def get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0", **(headers or {})})
    return urllib.request.urlopen(req, timeout=30).read()


def load_params():
    return json.load(open(PARAMS_FILE, encoding="utf-8"))


def save_params(p):
    json.dump(p, open(PARAMS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def resample(df, minutes):
    # แท่ง 30 นาทีของ OANDA บน TradingView เริ่มที่นาที :00 และ :30 (เวลา UTC)
    s = df.set_index("t").resample(f"{minutes}min").agg(dict(o="first", h="max", l="min", c="last")).dropna()
    return s.reset_index()


def gold_live(minutes, days=30):
    # ทองฟิวเจอร์ส GC=F จาก Yahoo (แท่ง 15 นาทีรวมแท่งที่กำลังวิ่ง) -> แท่งตาม timeframe ระบบ
    r = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=15m&range={days}d"))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    df = pd.DataFrame(dict(t=pd.to_datetime(r["timestamp"], unit="s"), o=q["open"], h=q["high"], l=q["low"], c=q["close"])).dropna()
    df["t"] = df.t.dt.floor("15min")
    return resample(df, minutes)


def paxg_hist(minutes, start="2022-01-01"):
    # ทอง PAXG จาก Binance ย้อนหลังหลายปี (ใช้ทดสอบระบบ) ตัดช่วงตลาดทองปิดวันเสาร์-อาทิตย์
    out, t = [], int(pd.Timestamp(start).timestamp() * 1000)
    while True:
        d = json.loads(get(f"https://data-api.binance.vision/api/v3/klines?symbol=PAXGUSDT&interval={minutes}m&startTime={t}&limit=1000"))
        if not d:
            break
        out += d
        t = d[-1][0] + 1
        if len(d) < 1000:
            break
    df = pd.DataFrame(out).iloc[:, :5].astype(float)
    df.columns = ["t", "o", "h", "l", "c"]
    df["t"] = pd.to_datetime(df["t"], unit="ms")
    wd, hr = df.t.dt.weekday, df.t.dt.hour
    return df[~((wd == 5) | ((wd == 6) & (hr < 23)) | ((wd == 4) & (hr >= 21)))].reset_index(drop=True)


def market_closed(t):
    # ตลาดทองปิด: ศุกร์ 21:00 UTC ถึง อาทิตย์ 23:00 UTC
    wd, hr = t.weekday(), t.hour
    return wd == 5 or (wd == 6 and hr < 23) or (wd == 4 and hr >= 21)


def paxg_recent(minutes, limit=1000, start=None):
    # ราคาทองแบบเรียลไทม์ (PAXG บน Binance ใกล้เคียงราคาทอง spot) รวมแท่งที่กำลังวิ่ง
    url = f"https://data-api.binance.vision/api/v3/klines?symbol=PAXGUSDT&interval={minutes}m&limit={limit}"
    if start is not None:
        url += f"&startTime={int(pd.Timestamp(start).timestamp() * 1000)}"
    df = pd.DataFrame(json.loads(get(url))).iloc[:, :5].astype(float)
    df.columns = ["t", "o", "h", "l", "c"]
    df["t"] = pd.to_datetime(df["t"], unit="ms")
    return df[~df.t.apply(market_closed)].reset_index(drop=True)


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
            Rs.append(R - COST / sd); i = j + 1; continue
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
