"""Flexible Excel/CSV adapter with AUTO column-mapping (V1 priority #1).

Usage:
    ad = TabularAdapter()
    df = ad.read(file)                  # excel or csv -> dataframe
    mapping = ad.suggest_mapping(df)    # auto-detected, show + let user correct
    batch = ad.normalize(df, mapping)   # apply (possibly corrected) mapping
"""
import io
from datetime import datetime
import pandas as pd
from .base import Adapter, NormalizedBatch
from ..mapping import detect_mapping, _DATE_FMTS


def _to_float(v, default=0.0):
    try:
        return float(str(v).replace(",", "").replace("₹", "").strip())
    except (ValueError, AttributeError):
        return default


def _to_iso(v):
    s = str(v).strip()
    for f in _DATE_FMTS:
        try:
            return datetime.strptime(s, f).date().isoformat()
        except ValueError:
            continue
    try:
        return pd.to_datetime(s).date().isoformat()
    except Exception:
        return s  # leave as-is; surfaced as warning upstream


class TabularAdapter(Adapter):
    name = "tabular"

    def read(self, file_or_path) -> pd.DataFrame:
        """Accepts path, bytes, or file-like. Sniffs csv vs excel."""
        if isinstance(file_or_path, (bytes, bytearray)):
            buf = io.BytesIO(file_or_path)
            try:
                return pd.read_excel(buf)
            except Exception:
                buf.seek(0)
                return pd.read_csv(buf)
        name = getattr(file_or_path, "name", str(file_or_path)).lower()
        if name.endswith((".xlsx", ".xls", ".xlsm")):
            return pd.read_excel(file_or_path)
        return pd.read_csv(file_or_path)

    def suggest_mapping(self, df, fields=None):
        return detect_mapping(df, fields)

    def normalize(self, df: pd.DataFrame, mapping: dict = None, **kwargs) -> NormalizedBatch:
        mapping = mapping or self.suggest_mapping(df)
        col = {f: m["column"] for f, m in mapping.items() if m.get("column")}
        b = NormalizedBatch(meta={"mapping": mapping, "rows": len(df)})

        if "sku" not in col:
            b.warnings.append("No SKU column detected — cannot import without a key.")
            return b

        prod_seen = {}
        for _, row in df.iterrows():
            sku = str(row[col["sku"]]).strip()
            if not sku or sku.lower() == "nan":
                continue
            name = str(row[col["name"]]).strip() if "name" in col else ""
            cost = _to_float(row[col["unit_cost"]]) if "unit_cost" in col else 0.0
            if sku not in prod_seen:
                prod_seen[sku] = True
                b.products.append({"sku": sku, "name": name, "unit_cost": cost})

            if "date" in col and "qty" in col:
                iso = _to_iso(row[col["date"]])
                qty = _to_float(row[col["qty"]])
                b.sales.append({"sku": sku, "date": iso, "qty": qty})

            if "stock" in col:
                b.inventory.append({"sku": sku, "stock": _to_float(row[col["stock"]])})

            if "lead_time_days" in col:
                b.suppliers.append({
                    "sku": sku,
                    "lead_time_days": _to_float(row[col["lead_time_days"]], 7),
                    "reliability": _to_float(row[col["reliability"]], 0.95)
                    if "reliability" in col else 0.95})

        if "date" not in col or "qty" not in col:
            b.warnings.append("No date+qty pair detected — imported as catalog/stock "
                              "only, no sales history for forecasting.")
        return b
