"""Feature F — AUTO-REORDER (post-trust).  [STUB — interface only]

Once a SKU is "trusted" (good forecast track record in the outcomes table),
allow automatic PO placement, gated behind a per-SKU toggle. v1 only SUGGESTS;
nothing here places real orders.

Plug-in point: implement `place_order()` against a real PO channel (POS API,
email PO, supplier portal) once trust gating is in place.
"""
from dataclasses import dataclass


@dataclass
class AutoReorderPolicy:
    sku: str
    enabled: bool = False        # per-SKU toggle, default OFF
    max_order_value: float = 0   # spend ceiling per auto-PO
    min_trust: float = 0.8       # required forecast-accuracy score to auto-fire


def is_trusted(sku: str, outcomes: list, min_trust=0.8) -> float:
    """Trust score from forecast-vs-actual accuracy in the outcomes table."""
    rows = [o for o in outcomes if o["sku"] == sku and o.get("actual_qty")]
    if len(rows) < 3:
        return 0.0
    errs = []
    for o in rows:
        a, f = float(o["actual_qty"]), float(o.get("forecast_qty", 0))
        if a > 0:
            errs.append(min(abs(a - f) / a, 1.0))
    if not errs:
        return 0.0
    return round(1 - sum(errs) / len(errs), 3)


def place_order(policy: AutoReorderPolicy, qty: float, unit_cost: float):
    # TODO(F): gate on is_trusted() >= policy.min_trust AND policy.enabled,
    # then submit PO through a real channel. v1 must never auto-buy.
    raise NotImplementedError("Auto-reorder disabled in v1 — suggestions only.")
