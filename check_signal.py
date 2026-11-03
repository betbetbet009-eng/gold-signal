# เช็กสัญญาณทอง: เตือนล่วงหน้าก่อนแท่งปิด, ยืนยันหลังแท่งปิด และให้พอร์ตเดโมเทรดตาม (เรียกจาก runner.py ทุก 2 นาที)
import json, os, sys
import pandas as pd
from core import ROOT, paxg_recent, market_closed, signals, load_params, lot_for, notify
import paper
import broker

STATE = os.path.join(ROOT, "state.json")
PRE_WINDOW_MIN = 6       # เตือนล่วงหน้าเมื่อเหลือเวลาก่อนแท่งปิดไม่เกินกี่นาที
CONFIRM_WINDOW_MIN = 25  # ยืนยันได้ภายในกี่นาทีหลังแท่งปิด


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {"sent": []}


def describe(kind, side, entry, sl_dist, rr, p, minutes=None):
    tp_dist = sl_dist * rr
    lot, loss001 = lot_for(p, sl_dist)
    sgn = 1 if side == "BUY" else -1
    lot_txt = (f"{lot:.2f} lot (ถ้าโดน SL เสีย ~${lot * 100 * loss001:.2f})" if lot >= 0.01
               else f"0.01 lot เสีย ~${loss001:.2f} ถ้าโดน SL (เกินที่ตั้งไว้ {p['risk_pct']:.0f}%)")
    head = (f"⏳ อีก ~{minutes} นาที อาจมีสัญญาณ {side} ทอง" if kind == "pre"
            else f"{'🟢' if side == 'BUY' else '🔴'} {side} ทอง XAUUSD ตอนนี้")
    body = (f"เข้า ~{entry:.2f}\n"
            f"SL ~{entry - sgn * sl_dist:.2f} (ห่าง {sl_dist:.1f})\n"
            f"TP ~{entry + sgn * tp_dist:.2f} (ห่าง {tp_dist:.1f})\n"
            f"Lot ({p['account']} ${p['balance']:.0f}): {lot_txt}\n"
            "ราคาใน MT5 อาจต่างไม่กี่ดอลลาร์ ให้ตั้ง SL/TP ตาม 'ห่าง' จากราคาที่เข้าได้จริง")
    if kind == "pre":
        body += "\nรอยืนยันตอนแท่งปิด"
    return head, body


def main():
    p = load_params()
    state = load_state()
    sent = set(state["sent"])
    now = pd.Timestamp.now("UTC").tz_localize(None)
    pst = paper.load()
    paper.update(pst)
    paper.daily_summary(pst, now)
    paper.save(pst)
    if market_closed(now):
        print(f"now {now} | market closed")
        return
    bar = pd.Timedelta(minutes=p["tf"])
    df = paxg_recent(p["tf"])
    df["end"] = df.t + bar

    # 1) เตือนล่วงหน้า: แท่งที่กำลังวิ่ง ถ้าปิดตอนนี้จะเป็นสัญญาณไหม
    last = df.iloc[-1]
    mins_left = int((last.end - now).total_seconds() // 60)
    if 0 < mins_left <= PRE_WINDOW_MIN:
        L, S, a, _, _ = signals(df, p)
        side = "BUY" if L[-1] else ("SELL" if S[-1] else None)
        key = f"pre:{last.t}"
        if side and key not in sent:
            notify(*describe("pre", side, last.c, p["sl"] * a[-1], p["rr"], p, mins_left), tags="hourglass")
            sent.add(key)

    # 2) ยืนยันแท่งที่เพิ่งปิด
    closed = df[df.end <= now].reset_index(drop=True)
    L, S, a, _, _ = signals(closed, p)
    bar = closed.iloc[-1]
    age = (now - bar.end).total_seconds() / 60
    if age <= CONFIRM_WINDOW_MIN:
        side = "BUY" if L[-1] else ("SELL" if S[-1] else None)
        if side and f"confirm:{bar.t}" not in sent:
            notify(*describe("confirm", side, bar.c, p["sl"] * a[-1], p["rr"], p))
            sent.add(f"confirm:{bar.t}")
            paper.open_trade(pst, side, bar.c, p["sl"] * a[-1], p["rr"], bar.end)
            paper.save(pst)
            broker.place(side, p["sl"] * a[-1], p["rr"], p)
        elif not side and f"pre:{bar.t}" in sent and f"cancel:{bar.t}" not in sent:
            notify("❌ ยกเลิกสัญญาณทอง", "แท่งปิดแล้วไม่เข้าเงื่อนไข ไม่ต้องเข้าออเดอร์", tags="x", priority="default")
            sent.add(f"cancel:{bar.t}")

    print(f"now {now} | forming bar {last.t} ends in {mins_left} min | last closed {bar.t} close {bar.c:.2f} "
          f"| long {bool(L[-1])} short {bool(S[-1])}")
    state["sent"] = sorted(sent)[-60:]
    json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
