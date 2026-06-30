"""OUTCOME-DATA FLYWHEEL helper.

Logs forecast-vs-actual, stockouts, spoilage, lead-time actuals per SKU.
This compounding dataset is the long-term moat and feeds the auto-reorder
trust score (feature F). Schema captures it from day one (see db.outcomes).
"""
from . import db


def record_period(sku, date, forecast_qty, actual_qty,
                  stockout=False, spoilage=0.0, lead_time_actual=None,
                  db_path=db.DB_PATH):
    db.log_outcomes([{
        "sku": sku, "date": date,
        "forecast_qty": forecast_qty, "actual_qty": actual_qty,
        "stockout": stockout, "spoilage": spoilage,
        "lead_time_actual": lead_time_actual,
    }], db_path)


def accuracy_summary(db_path=db.DB_PATH):
    """Aggregate MAPE-like accuracy per SKU for the dashboard."""
    rows = db.get_outcomes(db_path)
    by = {}
    for o in rows:
        a = float(o.get("actual_qty") or 0)
        f = float(o.get("forecast_qty") or 0)
        if a <= 0:
            continue
        by.setdefault(o["sku"], []).append(min(abs(a - f) / a, 1.0))
    return {sku: round(1 - sum(e) / len(e), 3) for sku, e in by.items() if e}
