"""Orchestration: pull data from db -> forecast -> reorder -> cash optimize.
Thin layer the UI calls so all business logic stays out of the frontend.
"""
from . import db
from .forecast import _linreg_slope, _to_daily_series
from .ai_forecast import AIForecaster
from .reorder import reorder_for_sku
from .cashflow import ReorderLine, optimize, crisis_guard
from .outcomes import accuracy_summary


def _trend(sales_rows):
    days, qtys = _to_daily_series(sales_rows)
    return _linreg_slope(qtys) if len(qtys) >= 2 else 0.0


def build_report(service_level=0.95, horizon_days=30,
                 critical_skus=None, db_path=None):
    critical_skus = set(critical_skus or [])
    products = {p["sku"]: p for p in db.get_products(db_path)}
    inv = {i["sku"]: i for i in db.get_inventory(db_path)}
    sup = {s["sku"]: s for s in db.get_suppliers(db_path)}
    psup = db.get_product_supplier_map(db_path)   # sku -> named supplier
    acc = accuracy_summary(db_path)

    # Train the AI forecaster once on the whole shop (cross-SKU pooling),
    # then ask it per SKU below. Cold-start SKUs fall back internally.
    sales_by_sku = {sku: db.sales_for(sku, db_path) for sku in products}
    ai = AIForecaster(horizon_days=horizon_days).fit(sales_by_sku)

    rows = []
    for sku, p in products.items():
        sales = sales_by_sku[sku]
        fc = ai.forecast_sku(sku, horizon_days)
        on_hand = float(inv.get(sku, {}).get("on_hand", 0) or 0)
        s = sup.get(sku, {})
        ro = reorder_for_sku(
            fc, on_hand,
            lead_time_days=float(s.get("lead_time_days", 7) or 7),
            reliability=float(s.get("reliability", 0.95) or 0.95),
            service_level=service_level)
        rows.append({
            "sku": sku, "name": p.get("name", ""),
            "unit_cost": float(p.get("unit_cost", 0) or 0),
            "on_hand": on_hand,
            "forecast": fc, "reorder": ro,
            "trend": _trend(sales),
            "critical": sku in critical_skus,
            "accuracy": acc.get(sku),
            "supplier": psup.get(sku),   # assigned named supplier, or None
        })
    return rows


def to_reorder_lines(report):
    return [ReorderLine(
        sku=r["sku"], name=r["name"], qty=r["reorder"]["suggested_qty"],
        unit_cost=r["unit_cost"], daily_rate=r["reorder"]["daily_rate"],
        stockout_risk=r["reorder"]["stockout_risk"],
        trend=r["trend"], critical=r["critical"],
        supplier_name=(r.get("supplier") or {}).get("name", ""),
        supplier_phone=(r.get("supplier") or {}).get("phone", "")) for r in report]


def cash_view(report, cash_cap=None, cash_on_hand=None):
    lines = to_reorder_lines(report)
    plan = optimize(lines, cash_cap)
    guard = crisis_guard(lines, cash_on_hand) if cash_on_hand is not None else \
        {"triggered": False, "hold": [], "reason": ""}
    return plan, guard
