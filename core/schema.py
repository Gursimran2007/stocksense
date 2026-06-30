"""Single normalized schema. Every adapter must output rows matching these shapes.

Canonical tables:
  products(sku, name, unit_cost)
  sales(sku, date, qty)
  inventory(sku, on_hand, updated_at)
  suppliers(sku, lead_time_days, reliability)
  outcomes(...)  <- flywheel: forecast-vs-actual, stockouts, spoilage, lead-time actuals
"""
from dataclasses import dataclass, field
from datetime import date as _date, datetime
from typing import Optional

# Canonical field names the whole system speaks.
CANONICAL = ["sku", "name", "date", "qty", "stock", "unit_cost",
             "lead_time_days", "reliability"]


@dataclass
class Product:
    sku: str
    name: str = ""
    unit_cost: float = 0.0


@dataclass
class Sale:
    sku: str
    date: str          # ISO yyyy-mm-dd
    qty: float = 0.0


@dataclass
class Inventory:
    sku: str
    on_hand: float = 0.0
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Supplier:
    sku: str
    lead_time_days: float = 7.0
    reliability: float = 0.95   # 0..1, fraction of POs delivered on time


@dataclass
class Outcome:
    """One row per SKU per period: the compounding moat dataset."""
    sku: str
    date: str
    forecast_qty: float = 0.0
    actual_qty: float = 0.0
    stockout: bool = False
    spoilage: float = 0.0
    lead_time_actual: Optional[float] = None
