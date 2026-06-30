"""Feature D — MARKET RATE / SUPPLIER-PRICE linking.  [STUB — interface only]

Plan: per-SKU best supplier price across vendors to optimize reorder cost.
Real price feeds rarely have clean APIs, so this is an INTERFACE only — do NOT
build scraping now. Future impls: a vendor catalogue upload, a distributor API,
or a manually-maintained price book.

Plug-in point: implement `best_price(sku)` and `quotes(sku)`.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class PriceQuote:
    sku: str
    vendor: str
    price: float
    min_order_qty: float = 1
    lead_time_days: float = 7


class SupplierPriceSource(ABC):
    name = "supplier_price_base"

    @abstractmethod
    def quotes(self, sku: str) -> List[PriceQuote]:
        ...

    def best_price(self, sku: str) -> Optional[PriceQuote]:
        qs = self.quotes(sku)
        return min(qs, key=lambda q: q.price) if qs else None


class StaticPriceBook(SupplierPriceSource):
    """TODO(D): replace with real vendor feed. For now reads an in-memory book."""
    name = "static_pricebook"

    def __init__(self, book=None):
        self.book = book or {}  # {sku: [PriceQuote,...]}

    def quotes(self, sku: str):
        return self.book.get(sku, [])
