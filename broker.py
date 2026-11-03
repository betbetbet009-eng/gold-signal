# ส่งออเดอร์เข้าบัญชี Exness (MT5) ผ่าน MetaApi เมื่อมีสัญญาณ
# ต้องมี GitHub secrets: METAAPI_TOKEN, METAAPI_ACCOUNT_ID ถ้าไม่มีจะข้ามไปเฉยๆ
import asyncio, math, os
from core import notify

MAGIC = 30300


def enabled():
    return bool(os.environ.get("METAAPI_TOKEN") and os.environ.get("METAAPI_ACCOUNT_ID"))


async def _connect():
    from metaapi_cloud_sdk import MetaApi
    api = MetaApi(os.environ["METAAPI_TOKEN"])
    account = await api.metatrader_account_api.get_account(os.environ["METAAPI_ACCOUNT_ID"])
    if account.state not in ("DEPLOYING", "DEPLOYED"):
        await account.deploy()
    await account.wait_connected()
    conn = account.get_rpc_connection()
    await conn.connect()
    await conn.wait_synchronized()
    return api, conn


async def _place(side, sl_dist, rr, p):
    api, conn = await _connect()
    try:
        symbol = p.get("symbol", "XAUUSDc")
        positions = await conn.get_positions()
        if any(x.get("symbol") == symbol and x.get("magic") == MAGIC for x in positions):
            return None, "มีไม้ของบอทค้างอยู่แล้ว ข้ามสัญญาณนี้"
        info = await conn.get_account_information()
        spec = await conn.get_symbol_specification(symbol)
        price = await conn.get_symbol_price(symbol)
        # Lot ให้ขาดทุนไม่เกิน risk_pct% ถ้าโดน SL (ยอดเงินและกำไรของบัญชี Cent เป็น USC อยู่แล้ว)
        loss_per_lot = sl_dist * spec.get("contractSize", 100)
        step = spec.get("volumeStep", 0.01)
        lot = math.floor(info["balance"] * p["risk_pct"] / 100 / loss_per_lot / step) * step
        lot = round(max(spec.get("minVolume", 0.01), min(spec.get("maxVolume", 100), lot)), 2)
        opts = {"comment": "GoldBreakout", "magic": MAGIC}
        if side == "BUY":
            entry = price["ask"]
            sl, tp = entry - sl_dist, entry + sl_dist * rr
            res = await conn.create_market_buy_order(symbol, lot, round(sl, 2), round(tp, 2), opts)
        else:
            entry = price["bid"]
            sl, tp = entry + sl_dist, entry - sl_dist * rr
            res = await conn.create_market_sell_order(symbol, lot, round(sl, 2), round(tp, 2), opts)
        return res, f"{side} {lot:.2f} lot @ {entry:.2f} | SL {sl:.2f} | TP {tp:.2f}\nยอดเงินในบัญชี {info['balance']:.2f} {info.get('currency', '')}"
    finally:
        await conn.close()


def place(side, sl_dist, rr, p):
    if not enabled():
        return
    try:
        res, msg = asyncio.run(_place(side, sl_dist, rr, p))
        notify("🤖 Exness เปิดออเดอร์แล้ว" if res else "🤖 Exness ไม่ได้เปิดออเดอร์", msg, tags="robot", priority="high")
    except Exception as e:
        notify("🤖 Exness เปิดออเดอร์ไม่สำเร็จ", f"{type(e).__name__}: {str(e)[:300]}", tags="warning", priority="high")


def test():
    # ทดสอบเชื่อมต่อ: แจ้งยอดเงินและราคาปัจจุบัน ไม่ส่งออเดอร์
    from core import load_params
    p = load_params()

    async def run():
        api, conn = await _connect()
        try:
            info = await conn.get_account_information()
            price = await conn.get_symbol_price(p.get("symbol", "XAUUSDc"))
            return f"บัญชี {info.get('login')} ({info.get('server')})\nยอดเงิน {info['balance']:.2f} {info.get('currency', '')}\n{p.get('symbol', 'XAUUSDc')} bid {price['bid']} ask {price['ask']}"
        finally:
            await conn.close()
    try:
        notify("🤖 เชื่อม Exness สำเร็จ", asyncio.run(run()), tags="robot", priority="default")
    except Exception as e:
        notify("🤖 เชื่อม Exness ไม่สำเร็จ", f"{type(e).__name__}: {str(e)[:300]}", tags="warning")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    test()
