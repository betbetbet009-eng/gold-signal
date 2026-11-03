# พอร์ตเดโม (เงินปลอม) ที่เทรดตามสัญญาณเองอัตโนมัติ บัญชี Cent: 0.01 lot = $0.01 ต่อราคาทองขยับ $1
import json, os
import pandas as pd
from core import ROOT, COST, paxg_recent, notify

PAPER = os.path.join(ROOT, "paper.json")
START_BALANCE = 20.0
RISK_PCT = 2.0


def load():
    try:
        return json.load(open(PAPER, encoding="utf-8"))
    except Exception:
        return {"start": START_BALANCE, "balance": START_BALANCE, "open": None, "history": [], "summary_sent": ""}


def save(st):
    json.dump(st, open(PAPER, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def stats(st):
    h = st["history"]
    wins = sum(1 for x in h if x["pnl"] > 0)
    return f"ยอดเดโม ${st['balance']:.2f} (เริ่ม ${st['start']:.0f}, {st['balance'] - st['start']:+.2f}) | ชนะ {wins}/{len(h)} ไม้"


def open_trade(st, side, entry, sl_dist, rr, t):
    if st["open"]:
        return
    lot = max(0.01, int(st["balance"] * RISK_PCT / 100 / sl_dist * 100) / 100)
    d = 1 if side == "BUY" else -1
    st["open"] = dict(side=side, entry=round(entry, 2), sl=round(entry - d * sl_dist, 2), tp=round(entry + d * sl_dist * rr, 2),
                      lot=lot, time=str(t))
    o = st["open"]
    notify(f"📒 เดโมเปิด {side} {lot:.2f} lot",
           f"เข้า {o['entry']:.2f} | SL {o['sl']:.2f} | TP {o['tp']:.2f}\n"
           f"ถ้าโดน SL เสีย ~${sl_dist * lot:.2f} | ถึง TP ได้ ~${sl_dist * rr * lot:.2f}\n{stats(st)}",
           tags="notebook", priority="default")


def update(st):
    # เช็กว่าไม้ที่เปิดอยู่ชน SL/TP หรือยัง (ใช้แท่ง 5 นาทีหลังเวลาเข้า ถ้าชนทั้งคู่ในแท่งเดียวนับเป็น SL)
    o = st["open"]
    if not o:
        return
    bars = paxg_recent(5, start=o["time"])
    d = 1 if o["side"] == "BUY" else -1
    for _, b in bars.iterrows():
        hit_sl = b.l <= o["sl"] if d == 1 else b.h >= o["sl"]
        hit_tp = b.h >= o["tp"] if d == 1 else b.l <= o["tp"]
        if hit_sl or hit_tp:
            exit_px = o["sl"] if hit_sl else o["tp"]
            pnl = round(d * (exit_px - o["entry"]) * o["lot"] - COST * o["lot"], 2)
            st["balance"] = round(st["balance"] + pnl, 2)
            st["history"].append(dict(**o, exit=exit_px, exit_time=str(b.t), pnl=pnl))
            st["open"] = None
            notify(f"📒 เดโมปิด {o['side']} {'TP ✅' if hit_tp and not hit_sl else 'SL ❌'} {pnl:+.2f}$",
                   f"เข้า {o['entry']:.2f} → ออก {exit_px:.2f}\n{stats(st)}",
                   tags="white_check_mark" if pnl > 0 else "x", priority="default")
            return


def daily_summary(st, now):
    # สรุปวันละครั้งหลัง 16:00 UTC (23:00 เวลาไทย) วันจันทร์-ศุกร์ ให้รู้ว่าระบบยังทำงาน
    day = str(now.date())
    if now.weekday() > 4 or now.hour < 16 or st.get("summary_sent") == day:
        return
    today = [x for x in st["history"] if x["exit_time"][:10] == day]
    pnl = sum(x["pnl"] for x in today)
    o = st["open"]
    open_txt = f"ถืออยู่: {o['side']} @ {o['entry']:.2f} (SL {o['sl']:.2f} / TP {o['tp']:.2f})" if o else "ไม่มีไม้ค้าง"
    notify("📊 สรุปวันนี้ (ระบบทองยังทำงาน)",
           f"วันนี้ปิด {len(today)} ไม้ รวม {pnl:+.2f}$\n{open_txt}\n{stats(st)}",
           tags="bar_chart", priority="low")
    st["summary_sent"] = day
