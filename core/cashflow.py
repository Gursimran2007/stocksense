"""CASH-FLOW / SURVIVABILITY optimizer (key differentiator).

Given per-SKU reorder suggestions + costs, answer:
  * "reorder everything" -> how much cash is locked?
  * a LEANER plan within a cash cap that still avoids the worst stockouts.
Prioritise high-velocity / high-risk / critical SKUs; flag slow movers to skip.

Also hosts Feature E — CRISIS / DEMAND-DROP GUARD (rule-based hook).
"""
from dataclasses import dataclass
from typing import List, Dict


@dataclass
class ReorderLine:
    sku: str
    name: str
    qty: float
    unit_cost: float
    daily_rate: float
    stockout_risk: str           # low / medium / high
    trend: float = 0.0           # per-day slope (negative = declining)
    critical: bool = False       # user / rule flagged must-keep
    supplier_name: str = ""      # assigned named supplier (if any)
    supplier_phone: str = ""     # that supplier's WhatsApp/call number

    @property
    def cost(self):
        return self.qty * self.unit_cost

    @property
    def velocity_value(self):
        # cash velocity proxy: how much demand this unit cost serves per day
        return self.daily_rate * self.unit_cost


_RISK_W = {"high": 3, "medium": 2, "low": 1}


def _priority(line: ReorderLine) -> float:
    """Higher = reorder sooner. Velocity * risk, boosted if critical."""
    p = line.velocity_value * _RISK_W.get(line.stockout_risk, 1)
    if line.critical:
        p *= 5
    if line.daily_rate <= 0:        # dead stock
        p = 0
    return p


def optimize(lines: List[ReorderLine], cash_cap: float = None) -> Dict:
    """Return full-cost, a budget-constrained lean plan, and skip list."""
    total_cost = sum(l.cost for l in lines if l.qty > 0)

    ranked = sorted([l for l in lines if l.qty > 0],
                    key=_priority, reverse=True)

    if cash_cap is None:
        chosen = ranked
        skipped = []
    else:
        chosen, skipped, spent = [], [], 0.0
        for l in ranked:
            if _priority(l) <= 0:          # never spend on dead stock
                skipped.append(l); continue
            if spent + l.cost <= cash_cap:
                chosen.append(l); spent += l.cost
            else:
                # try partial fill to use remaining budget on critical/high risk
                remaining = cash_cap - spent
                if l.unit_cost > 0 and l.stockout_risk == "high" and remaining > 0:
                    part = int(remaining // l.unit_cost)
                    if part > 0:
                        pl = ReorderLine(l.sku, l.name, part, l.unit_cost,
                                         l.daily_rate, l.stockout_risk,
                                         l.trend, l.critical,
                                         l.supplier_name, l.supplier_phone)
                        chosen.append(pl); spent += pl.cost
                        if l.qty - part > 0:
                            skipped.append(ReorderLine(
                                l.sku, l.name, l.qty - part, l.unit_cost,
                                l.daily_rate, l.stockout_risk, l.trend, l.critical,
                                l.supplier_name, l.supplier_phone))
                        continue
                skipped.append(l)

    lean_cost = sum(l.cost for l in chosen)
    slow_movers = [l for l in lines if l.daily_rate <= 0 or _priority(l) == 0]

    # SKUs left exposed to a high stockout risk because we skipped them
    at_risk = [l for l in skipped if l.stockout_risk == "high"]

    return {
        "reorder_all_cost": round(total_cost, 2),
        "lean_cost": round(lean_cost, 2),
        "cash_saved": round(total_cost - lean_cost, 2),
        "cash_cap": cash_cap,
        "chosen": chosen,
        "skipped": skipped,
        "slow_movers": slow_movers,
        "high_risk_skipped": at_risk,
    }


# --- Feature E: CRISIS / DEMAND-DROP GUARD (rule hook) --------------------
def crisis_guard(lines: List[ReorderLine], cash_on_hand: float,
                 runway_floor: float = None) -> Dict:
    """Simple rule: if cash is low AND demand trending down, hold non-critical
    reorders to preserve runway; keep only critical / high-velocity items.

    TODO(E): replace heuristic with smarter signals (macro, seasonality, news).
    """
    declining = [l for l in lines if l.trend < 0]
    total = sum(l.cost for l in lines if l.qty > 0)
    low_cash = (cash_on_hand is not None and total > cash_on_hand) or \
               (runway_floor is not None and cash_on_hand < runway_floor)

    triggered = low_cash and len(declining) >= max(1, len(lines) // 3)
    if not triggered:
        return {"triggered": False, "hold": [], "reason": "Conditions normal."}

    hold = [l for l in lines
            if (l.trend < 0 and not l.critical and l.stockout_risk != "high")]
    return {
        "triggered": True,
        "hold": hold,
        "reason": (f"Cash low and demand declining on {len(declining)} SKUs — "
                   f"holding {len(hold)} non-critical reorders to protect runway."),
    }
