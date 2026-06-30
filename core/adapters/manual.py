"""Manual-entry adapter (V1 fallback). Takes plain dicts/lists from a form."""
from .base import Adapter, NormalizedBatch


class ManualAdapter(Adapter):
    name = "manual"

    def normalize(self, raw: dict, **kwargs) -> NormalizedBatch:
        """raw = {products:[...], sales:[...], inventory:[...], suppliers:[...]}"""
        b = NormalizedBatch()
        b.products = [r for r in raw.get("products", []) if r.get("sku")]
        b.sales = [r for r in raw.get("sales", []) if r.get("sku")]
        b.inventory = [r for r in raw.get("inventory", []) if r.get("sku")]
        b.suppliers = [r for r in raw.get("suppliers", []) if r.get("sku")]
        return b
