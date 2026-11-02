# gold-signal

ระบบแจ้งเตือนสัญญาณทองคำ XAUUSD 4H (Trend Breakout) ฟรีบน GitHub Actions ส่งเข้ามือถือผ่าน ntfy

- `check_signal.py` เตือนล่วงหน้าก่อนแท่ง 4H ปิด และยืนยันหลังแท่งปิด (ราคาเข้า, SL, TP, Lot)
- `improve.py` ทุกวัน ทดสอบค่าหลายชุดแบบ walk-forward ถ้าดีกว่าชัดเจนจะอัปเดต `params.json` และแจ้งให้แก้ค่าใน TradingView
- `params.json` ค่าระบบปัจจุบัน และเงินในบัญชีสำหรับคำนวณ Lot (แก้ `balance` / `account` ได้)
- Secret ที่ต้องมี: `NTFY_TOPIC`

ไม่ใช่คำแนะนำการลงทุน ผลย้อนหลังไม่รับประกันอนาคต
