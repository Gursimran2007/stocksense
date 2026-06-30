"""Adapter interface. EVERY input type implements this -> same canonical schema.

An adapter turns some raw input (Excel, CSV, photo of a bill, POS API payload,
manual form) into a NormalizedBatch of canonical rows ready for db upserts.
Keep adapters pluggable and stateless.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class NormalizedBatch:
    products: List[dict] = field(default_factory=list)   # {sku,name,unit_cost}
    sales:    List[dict] = field(default_factory=list)   # {sku,date,qty}
    inventory: List[dict] = field(default_factory=list)  # {sku,stock}
    suppliers: List[dict] = field(default_factory=list)  # {sku,lead_time_days,reliability}
    warnings: List[str] = field(default_factory=list)
    needs_confirmation: bool = False   # True for low-trust sources (handwritten)
    meta: Dict[str, Any] = field(default_factory=dict)

    def extend(self, other: "NormalizedBatch"):
        self.products += other.products
        self.sales += other.sales
        self.inventory += other.inventory
        self.suppliers += other.suppliers
        self.warnings += other.warnings
        self.needs_confirmation = self.needs_confirmation or other.needs_confirmation
        return self


class Adapter(ABC):
    name = "base"
    needs_confirmation = False  # override for low-trust inputs

    @abstractmethod
    def normalize(self, raw, **kwargs) -> NormalizedBatch:
        """Convert raw input into a NormalizedBatch of canonical rows."""
        raise NotImplementedError
