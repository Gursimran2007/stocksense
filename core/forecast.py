"""Per-SKU, explainable demand forecasting.

Methods (auto-selected per SKU):
  * moving_average + linear trend   -> smooth, regular demand
  * croston                         -> intermittent / lumpy (spare parts)
Returns a daily demand rate + std, plus a human-readable explanation.
"""
import math
from datetime import datetime
from collections import defaultdict


def _to_daily_series(sales_rows):
    """Aggregate sales rows -> ordered (date, qty) list bucketed per day."""
    by_day = defaultdict(float)
    for r in sales_rows:
        try:
            d = datetime.fromisoformat(str(r["date"])[:10]).date()
        except ValueError:
            continue
        by_day[d] += float(r.get("qty", 0) or 0)
    days = sorted(by_day)
    return days, [by_day[d] for d in days]


def _span_days(days):
    return (days[-1] - days[0]).days + 1 if days else 0


def _intermittent(qtys):
    """Lumpy if >=40% of periods are zero and there are enough periods."""
    if len(qtys) < 6:
        return False
    zeros = sum(1 for q in qtys if q <= 0)
    return zeros / len(qtys) >= 0.4


def _linreg_slope(y):
    n = len(y)
    if n < 2:
        return 0.0
    xm = (n - 1) / 2
    ym = sum(y) / n
    num = sum((i - xm) * (y[i] - ym) for i in range(n))
    den = sum((i - xm) ** 2 for i in range(n))
    return num / den if den else 0.0


def _std(y, mean):
    if len(y) < 2:
        return 0.0
    return math.sqrt(sum((v - mean) ** 2 for v in y) / (len(y) - 1))


def croston(qtys, alpha=0.1):
    """Croston's method for intermittent demand. Returns per-period demand rate."""
    demand_sizes, intervals, last_gap = [], [], 1
    z = p = None
    for q in qtys:
        if q > 0:
            if z is None:
                z, p = q, max(last_gap, 1)
            else:
                z = z + alpha * (q - z)
                p = p + alpha * (last_gap - p)
            last_gap = 1
        else:
            last_gap += 1
    if z is None or not p:
        return 0.0
    return z / p


def forecast_sku(sales_rows, horizon_days=30):
    """Return a dict describing expected demand for one SKU."""
    days, qtys = _to_daily_series(sales_rows)
    total = sum(qtys)
    span = _span_days(days)

    if not days or span == 0:
        return {"method": "none", "daily_rate": 0.0, "daily_std": 0.0,
                "horizon_qty": 0.0, "explanation": "No sales history.",
                "n_points": 0, "intermittent": False}

    # Build a per-day vector across the full span (fill gaps with 0).
    full = [0.0] * span
    base = days[0]
    for d, q in zip(days, qtys):
        full[(d - base).days] += q

    intermittent = _intermittent(full)     # judge lumpiness over the full span
    if intermittent:
        rate = croston(full)               # per-day demand rate
        std = _std([q for q in full], rate)
        method = "croston"
        expl = (f"Lumpy demand: only {sum(1 for q in full if q>0)} active days of "
                f"{len(full)}. Croston rate ≈ {rate:.2f}/day.")
    else:
        rate = total / span                # avg daily demand
        slope = _linreg_slope(full)        # per-day trend
        rate = max(rate + slope * (span / 2), 0)  # project trend to mid-horizon
        std = _std(full, total / span)
        method = "moving_avg_trend"
        trend_txt = ("rising" if slope > 1e-6 else
                     "falling" if slope < -1e-6 else "flat")
        expl = (f"Avg {total/span:.2f}/day over {span} days, trend {trend_txt} "
                f"({slope:+.3f}/day). Projected rate ≈ {rate:.2f}/day.")

    return {
        "method": method,
        "daily_rate": round(rate, 3),
        "daily_std": round(std, 3),
        "horizon_qty": round(rate * horizon_days, 2),
        "horizon_days": horizon_days,
        "explanation": expl,
        "n_points": len(days),
        "span_days": span,
        "intermittent": intermittent,
    }
