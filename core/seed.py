"""Seed / demo data generator.

Produces:
  * a DB populated with realistic sales/inventory/suppliers, AND
  * a deliberately MESSY Excel file (weird headers, odd order, ₹ signs,
    mixed date formats) so the auto-mapping demo has something to chew on.
Includes a fast-mover, a slow/dead mover, and a lumpy spare-part SKU.
"""
import random
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
from . import db

random.seed(42)

CATALOG = [
    # sku, name, unit_cost, base_daily, pattern, lead, reliability, on_hand
    ("RICE-5KG",   "Basmati Rice 5kg",      420, 12, "trend_up",   5, 0.97, 60),
    ("OIL-1L",     "Sunflower Oil 1L",      140, 20, "regular",    4, 0.95, 30),
    ("SOAP-100",   "Bath Soap 100g",         28, 35, "regular",    3, 0.98, 200),
    ("TEA-250",    "Masala Tea 250g",       110,  8, "trend_down", 7, 0.90, 90),
    ("BULB-LED",   "LED Bulb 9W",            70,  2, "lumpy",     10, 0.85, 15),
    ("FILTER-AC",  "AC Filter (spare)",     350,  0.5, "lumpy",   14, 0.80, 4),
    ("PEN-BLUE",   "Blue Gel Pen",            6,  1, "dead",       5, 0.95, 500),
    ("ATTA-10KG",  "Wheat Atta 10kg",       360, 15, "regular",    5, 0.96, 25),
]

START = date.today() - timedelta(days=120)


def _series(base, pattern, days=120):
    out = []
    for i in range(days):
        d = START + timedelta(days=i)
        # Kirana footfall lifts on weekends (Sat=5, Sun=6) — gives the AI
        # forecaster a real weekly pattern to learn.
        wk = 1.45 if d.weekday() >= 5 else (0.85 if d.weekday() == 0 else 1.0)
        if pattern == "regular":
            q = max(0, round(random.gauss(base, base * 0.25) * wk))
        elif pattern == "trend_up":
            q = max(0, round(random.gauss(base + i * 0.08, base * 0.25) * wk))
        elif pattern == "trend_down":
            q = max(0, round(random.gauss(base - i * 0.05, base * 0.3) * wk))
        elif pattern == "lumpy":
            q = round(random.gauss(base * 8, base * 3)) if random.random() < 0.12 else 0
            q = max(0, q)
        elif pattern == "dead":
            q = 1 if random.random() < 0.03 else 0
        else:
            q = base
        if q > 0:
            out.append((d, q))
    return out


def seed_db(db_path=db.DB_PATH):
    db.reset_db(db_path)
    products, sales, inv, sup = [], [], [], []
    for sku, name, cost, base, pat, lead, rel, oh in CATALOG:
        products.append({"sku": sku, "name": name, "unit_cost": cost})
        inv.append({"sku": sku, "stock": oh})
        sup.append({"sku": sku, "lead_time_days": lead, "reliability": rel})
        for d, q in _series(base, pat):
            sales.append({"sku": sku, "date": d.isoformat(), "qty": q})
    db.upsert_products(products, db_path)
    db.insert_sales(sales, db_path)
    db.upsert_inventory(inv, db_path)
    db.upsert_suppliers(sup, db_path)
    return {"products": len(products), "sales": len(sales)}


def write_messy_excel(path=None):
    """Messy file: scrambled column order, non-standard headers, ₹, mixed dates."""
    path = Path(path or Path(__file__).resolve().parent.parent / "demo_messy.xlsx")
    rows = []
    fmts = ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y"]
    for sku, name, cost, base, pat, lead, rel, oh in CATALOG[:5]:
        for d, q in _series(base, pat, days=60):
            rows.append({
                "Particulars": name,            # name (odd header)
                "Pcs Out": q,                   # qty (odd header)
                "Item Code": sku,               # sku (odd header)
                "Txn Dt": d.strftime(random.choice(fmts)),  # mixed date formats
                "Closing Bal": oh,              # stock (odd header)
                "Rate (₹)": f"₹{cost}",         # unit_cost with currency symbol
            })
    # deliberately scramble column order
    df = pd.DataFrame(rows)[["Particulars", "Pcs Out", "Item Code",
                             "Txn Dt", "Closing Bal", "Rate (₹)"]]
    df.to_excel(path, index=False)
    return str(path)


if __name__ == "__main__":
    print(seed_db())
    print("messy excel:", write_messy_excel())
