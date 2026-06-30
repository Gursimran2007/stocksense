"""Plain-language daily report generator (used by the automated sync job).

Produces the same 'Buy today' answer the app shows, but as text + CSV files so
a scheduled job can leave them somewhere the owner just opens each morning.
"""
import csv
from datetime import datetime
from pathlib import Path

from . import db
from .engine import build_report, cash_view
from .sourcing import whatsapp_link


def generate(out_dir, cash_cap=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_report()
    plan, guard = cash_view(report, cash_cap=cash_cap,
                            cash_on_hand=cash_cap)
    buy = [l for l in plan["chosen"] if l.qty > 0]
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    sup_phone = db.get_setting("supplier_phone", "")
    shop_name = db.get_setting("shop_name", "")

    # ---- human-readable text ----
    lines = [f"StockSense — Buy-today report ({stamp})", "=" * 44, ""]
    if not report:
        lines.append("No items in the shop yet.")
    else:
        lines.append(f"Buy-everything cost : ₹{plan['reorder_all_cost']:,.0f}")
        if cash_cap is not None:
            lines.append(f"Within your budget  : ₹{plan['lean_cost']:,.0f} "
                         f"(saves ₹{plan['cash_saved']:,.0f})")
        lines += ["", "BUY THESE NOW:"]
        if buy:
            for l in buy:
                why = "running out fast" if l.stockout_risk == "high" else "getting low"
                lines.append(f"  • {l.name or l.sku:<22} buy {int(l.qty):>4}  "
                             f"₹{l.cost:>8,.0f}  ({why})")
        else:
            lines.append("  Nothing urgent. 👍")

        if plan["high_risk_skipped"]:
            lines += ["", "⚠️ RUN OUT SOON BUT OVER BUDGET:"]
            for l in plan["high_risk_skipped"]:
                lines.append(f"  • {l.name or l.sku:<22} need {int(l.qty)}")

        if plan["slow_movers"]:
            lines += ["", "🛑 DON'T RESTOCK (barely selling):"]
            for l in plan["slow_movers"]:
                lines.append(f"  • {l.name or l.sku}")

        if guard["triggered"]:
            lines += ["", "💡 " + guard["reason"]]

        if buy:
            order_items = [(l.name or l.sku, l.qty) for l in buy]
            link = whatsapp_link(sup_phone, order_items, shop_name or None)
            lines += ["", "📲 ORDER IN ONE TAP (open on phone):", link]

    text = "\n".join(lines)
    (out_dir / "buy_today.txt").write_text(text, encoding="utf-8")

    # ---- CSV (for Excel / sharing) ----
    with open(out_dir / "buy_today.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item", "buy_qty", "cost", "reason"])
        for l in buy:
            w.writerow([l.name or l.sku, int(l.qty), round(l.cost),
                        "running out" if l.stockout_risk == "high" else "low"])

    return {"text": text, "buy_count": len(buy),
            "files": [str(out_dir / "buy_today.txt"),
                      str(out_dir / "buy_today.csv")]}
