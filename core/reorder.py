"""Reorder engine.

reorder_point = lead_time_demand + safety_stock
order_qty     = bring position up to an optimal max level (covers lead time +
                a review period), never negative.
Human-approve before any order — v1 only SUGGESTS. (Auto-buy = feature F stub.)
"""
import math

# z-scores for service-level safety stock
Z = {0.90: 1.2816, 0.95: 1.6449, 0.975: 1.9600, 0.99: 2.3263}


def _z(service_level):
    best = min(Z, key=lambda k: abs(k - service_level))
    return Z[best]


def reorder_for_sku(fc, on_hand, lead_time_days=7, reliability=0.95,
                    service_level=0.95, review_period_days=7, on_order=0.0):
    """fc = forecast_sku() output. Returns a reorder suggestion dict."""
    rate = fc["daily_rate"]
    std = fc["daily_std"]

    # unreliable suppliers -> pad effective lead time
    eff_lead = lead_time_days * (1 + (1 - reliability))
    lead_time_demand = rate * eff_lead

    z = _z(service_level)
    # safety stock over lead time (demand-variability driven)
    safety_stock = z * std * math.sqrt(max(eff_lead, 0.0))
    reorder_point = lead_time_demand + safety_stock

    # order-up-to level: cover lead time + review period + safety
    max_level = rate * (eff_lead + review_period_days) + safety_stock
    position = on_hand + on_order
    order_qty = max(math.ceil(max_level - position), 0)

    needs = position <= reorder_point
    # days of cover left at current rate
    cover_days = (position / rate) if rate > 0 else float("inf")
    stockout_risk = ("high" if cover_days < eff_lead else
                     "medium" if cover_days < eff_lead + review_period_days else "low")

    return {
        "daily_rate": round(rate, 3),
        "reorder_point": round(reorder_point, 2),
        "safety_stock": round(safety_stock, 2),
        "lead_time_demand": round(lead_time_demand, 2),
        "max_level": round(max_level, 2),
        "on_hand": on_hand,
        "on_order": on_order,
        "needs_reorder": needs,
        "suggested_qty": order_qty if needs else 0,
        "cover_days": round(cover_days, 1) if cover_days != float("inf") else None,
        "stockout_risk": stockout_risk,
        "eff_lead_days": round(eff_lead, 1),
    }
