# ตรวจและพัฒนาระบบทุกวัน:
# - ทดสอบค่าหลายชุดแบบ walk-forward (เลือกจากข้อมูลเก่า แล้วต้องดีบนข้อมูล 12 เดือนล่าสุดด้วย)
# - ถ้าเจอค่าที่ดีกว่าชัดเจน -> อัปเดต params.json และแจ้งให้แก้ค่าใน TradingView
# - ถ้าระบบเริ่มแย่ -> แจ้งเตือน
import itertools, sys
import pandas as pd
from core import gold_1h, paxg_4h, to_4h, backtest, load_params, save_params, notify

MARGIN = 0.10          # ต้องดีกว่าเดิมอย่างน้อยกี่ R ต่อไม้ ทั้งช่วงเก่าและช่วงใหม่
MIN_TRADES_OLD, MIN_TRADES_NEW = 30, 8


def main():
    p = load_params()
    today = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    y1 = (today - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
    px = paxg_4h()
    gc = to_4h(gold_1h(729))

    cur_old, cur_new = backtest(px, p, end=y1), backtest(px, p, start=y1)
    cur_gc = backtest(gc, p)
    print(f"current {p} | PAXG old {cur_old} new {cur_new} | GC 2y {cur_gc}")

    best = None
    for n, sl, rr, ax in itertools.product([20, 30, 55], [2.0, 2.5, 3.0], [2.0, 2.5, 3.0], [15, 20, 25]):
        q = {**p, "n": n, "sl": sl, "rr": rr, "adx": ax}
        if (n, sl, rr, ax) == (p["n"], p["sl"], p["rr"], p["adx"]):
            continue
        old, new = backtest(px, q, end=y1), backtest(px, q, start=y1)
        if old["n"] < MIN_TRADES_OLD or new["n"] < MIN_TRADES_NEW:
            continue
        if old["exp"] >= cur_old["exp"] + MARGIN and new["exp"] >= cur_new["exp"] + MARGIN:
            g = backtest(gc, q)
            if g["exp"] >= cur_gc["exp"] and (best is None or new["exp"] > best[2]["exp"]):
                best = (q, old, new, g)

    if best:
        q, old, new, g = best
        q["updated"] = str(today.date())
        save_params(q)
        notify("🔧 ระบบทองอัปเดตค่าใหม่",
               f"ค่าใหม่ดีกว่าเดิมทั้งข้อมูลเก่าและ 12 เดือนล่าสุด\n"
               f"เดิม: เฉลี่ย {cur_new['exp']:+.2f}R/ไม้ → ใหม่ {new['exp']:+.2f}R/ไม้\n"
               f"แจ้งเตือนใช้ค่าใหม่แล้ว ให้แก้ใน TradingView (ฟันเฟืองของสคริปต์):\n"
               f"Breakout {q['n']} แท่ง | ADX {q['adx']} | SL {q['sl']} x ATR | TP {q['rr']} เท่าของ SL",
               tags="wrench", priority="default")
    elif cur_new["n"] >= MIN_TRADES_NEW and cur_new["exp"] < 0 and cur_gc["exp"] < 0:
        notify("⚠️ ระบบทองช่วงนี้ไม่ดี",
               f"12 เดือนล่าสุดเฉลี่ย {cur_new['exp']:+.2f}R/ไม้ ({cur_new['n']} ไม้)\nแนะนำหยุดใช้เงินจริงชั่วคราว ใช้ Demo ไปก่อน",
               tags="warning")
    elif today.day == 1:
        notify("📊 สรุประบบทองประจำเดือน",
               f"🟢 ปกติ | 12 เดือนล่าสุด: {cur_new['n']} ไม้ ชนะ {cur_new['wr']*100:.0f}% เฉลี่ย {cur_new['exp']:+.2f}R/ไม้\n"
               f"ค่าปัจจุบัน: Breakout {p['n']} | ADX {p['adx']} | SL {p['sl']}xATR | TP {p['rr']}xSL",
               tags="bar_chart", priority="low")
    else:
        print("no change")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
