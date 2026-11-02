# ตรวจและพัฒนาระบบทุกวัน:
# - ทดสอบค่าหลายชุดแบบ walk-forward (เลือกจากข้อมูลเก่า แล้วต้องดีบนข้อมูล 12 เดือนล่าสุดด้วย)
# - ถ้าเจอค่าที่ดีกว่าชัดเจน -> อัปเดต params.json และแจ้งให้แก้ค่าใน TradingView
# - ถ้าระบบเริ่มแย่ -> แจ้งเตือน
import itertools, sys
import pandas as pd
from core import paxg_hist, backtest, load_params, save_params, notify

MARGIN = 0.05          # ต้องดีกว่าเดิมอย่างน้อยกี่ R ต่อไม้ ทั้งช่วงเก่าและช่วงใหม่
MIN_TRADES_OLD, MIN_TRADES_NEW = 300, 150   # ต้องมีสัญญาณถี่พอ (~0.6 ครั้ง/วันขึ้นไป)


def main():
    p = load_params()
    today = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    y1 = (today - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
    m3 = (today - pd.DateOffset(months=3)).strftime("%Y-%m-%d")
    px = paxg_hist(p["tf"])

    cur_old, cur_new, cur_3m = backtest(px, p, end=y1), backtest(px, p, start=y1), backtest(px, p, start=m3)
    print(f"current {p} | old {cur_old} | last12m {cur_new} | last3m {cur_3m}")

    best = None
    for n, sl, rr, ax in itertools.product([20, 40], [1.5, 2.0, 3.0], [2.0, 3.0], [20, 25]):
        q = {**p, "n": n, "sl": sl, "rr": rr, "adx": ax}
        if (n, sl, rr, ax) == (p["n"], p["sl"], p["rr"], p["adx"]):
            continue
        old, new = backtest(px, q, end=y1), backtest(px, q, start=y1)
        if old["n"] < MIN_TRADES_OLD or new["n"] < MIN_TRADES_NEW:
            continue
        if old["exp"] >= cur_old["exp"] + MARGIN and new["exp"] >= cur_new["exp"] + MARGIN:
            if best is None or new["exp"] > best[2]["exp"]:
                best = (q, old, new)

    if best:
        q, old, new = best
        q["updated"] = str(today.date())
        save_params(q)
        notify("🔧 ระบบทองอัปเดตค่าใหม่",
               f"ค่าใหม่ดีกว่าเดิมทั้งข้อมูลเก่าและ 12 เดือนล่าสุด\n"
               f"เดิม: เฉลี่ย {cur_new['exp']:+.2f}R/ไม้ → ใหม่ {new['exp']:+.2f}R/ไม้\n"
               f"แจ้งเตือนใช้ค่าใหม่แล้ว ให้แก้ใน TradingView (ฟันเฟืองของสคริปต์):\n"
               f"Breakout {q['n']} แท่ง | ADX {q['adx']} | SL {q['sl']} x ATR | TP {q['rr']} เท่าของ SL",
               tags="wrench", priority="default")
    elif cur_new["exp"] < 0 and cur_3m["n"] >= 20 and cur_3m["exp"] < 0:
        notify("⚠️ ระบบทองช่วงนี้ไม่ดี",
               f"12 เดือนล่าสุดเฉลี่ย {cur_new['exp']:+.2f}R/ไม้, 3 เดือนล่าสุด {cur_3m['exp']:+.2f}R/ไม้\n"
               "แนะนำหยุดใช้เงินจริงชั่วคราว ใช้ Demo ไปก่อน", tags="warning")
    elif today.day == 1:
        notify("📊 สรุประบบทองประจำเดือน",
               f"12 เดือนล่าสุด: {cur_new['n']} ไม้ ชนะ {cur_new['wr']*100:.0f}% เฉลี่ย {cur_new['exp']:+.2f}R/ไม้\n"
               f"3 เดือนล่าสุด: {cur_3m['n']} ไม้ ชนะ {cur_3m['wr']*100:.0f}% เฉลี่ย {cur_3m['exp']:+.2f}R/ไม้\n"
               f"ค่าปัจจุบัน: Breakout {p['n']} | ADX {p['adx']} | SL {p['sl']}xATR | TP {p['rr']}xSL",
               tags="bar_chart", priority="low")
    else:
        print("no change")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
