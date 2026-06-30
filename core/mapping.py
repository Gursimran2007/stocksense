"""AUTO column-mapping (priority #1).

Given an arbitrary dataframe, guess which columns map to the canonical fields
sku / name / date / qty / stock / unit_cost / lead_time_days / reliability,
regardless of header names, order, or language. Returns a mapping + confidence
so the UI can show it and let the user correct.

Two signals are combined:
  1. header-name fuzzy match against synonym lists (multi-lingual hints)
  2. value-based inference (datatypes / patterns in the actual cells)
"""
import re
from datetime import datetime
import pandas as pd

# Header synonyms (lowercased, substring match). Include hi/hinglish hints.
SYNONYMS = {
    "sku":  ["sku", "item code", "itemcode", "code", "product id", "prod id",
             "item id", "article", "barcode", "ean", "part no", "part number",
             "material", "id"],
    "name": ["name", "item name", "product", "description", "desc", "item",
             "particulars", "title", "product name", "naam"],
    "date": ["date", "day", "txn date", "sale date", "invoice date", "bill date",
             "month", "period", "dt", "tarikh", "datetime", "timestamp"],
    "qty":  ["qty", "quantity", "units sold", "sold", "sales", "units", "qnty",
             "pieces", "pcs", "nos", "out", "issued", "demand", "matra"],
    "stock": ["stock", "on hand", "onhand", "on-hand", "inventory", "balance",
              "closing", "in stock", "available", "current stock", "bal", "qoh"],
    "unit_cost": ["cost", "unit cost", "price", "rate", "mrp", "purchase price",
                  "buy price", "cp", "unit price", "amount", "value"],
    "lead_time_days": ["lead time", "leadtime", "lead", "delivery days", "lt"],
    "reliability": ["reliability", "fill rate", "otif", "on time"],
}

_DATE_FMTS = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d",
              "%d-%b-%Y", "%d %b %Y", "%b %Y", "%Y-%m", "%m-%Y", "%d.%m.%Y"]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).strip()


def _header_score(header: str, field: str) -> float:
    h = _norm(header)
    if not h:
        return 0.0
    best = 0.0
    for syn in SYNONYMS[field]:
        if h == syn:
            best = max(best, 1.0)
        elif h.startswith(syn) or h.endswith(syn):
            best = max(best, 0.85)
        elif syn in h:
            best = max(best, 0.7)
    return best


def _looks_date(series: pd.Series) -> float:
    vals = series.dropna().astype(str).head(40)
    if len(vals) == 0:
        return 0.0
    hits = 0
    for v in vals:
        v = v.strip()
        ok = False
        for f in _DATE_FMTS:
            try:
                datetime.strptime(v, f); ok = True; break
            except ValueError:
                continue
        if not ok:
            try:
                pd.to_datetime(v); ok = True
            except Exception:
                ok = False
        hits += ok
    return hits / len(vals)


def _numeric_frac(series: pd.Series) -> float:
    vals = series.dropna().astype(str).head(40)
    if len(vals) == 0:
        return 0.0
    n = 0
    for v in vals:
        try:
            float(str(v).replace(",", "").replace("₹", "").strip()); n += 1
        except ValueError:
            pass
    return n / len(vals)


def _uniqueness(series: pd.Series) -> float:
    s = series.dropna()
    return len(s.unique()) / len(s) if len(s) else 0.0


def _value_score(series: pd.Series, field: str) -> float:
    if field == "date":
        return _looks_date(series)
    if field in ("qty", "stock", "unit_cost", "lead_time_days", "reliability"):
        return _numeric_frac(series) * 0.6  # weaker signal; many numeric cols
    if field == "sku":
        # short-ish, highly unique, often alphanumeric codes
        u = _uniqueness(series)
        avg_len = series.dropna().astype(str).str.len().head(40).mean() or 0
        return u * (1.0 if avg_len <= 18 else 0.4)
    if field == "name":
        # textual, mostly non-numeric, medium length
        return (1 - _numeric_frac(series)) * 0.6
    return 0.0


def detect_mapping(df: pd.DataFrame, fields=None):
    """Return {field: {'column': col|None, 'confidence': 0..1}} greedily,
    one column per field, highest combined score first."""
    fields = fields or ["sku", "name", "date", "qty", "stock", "unit_cost"]
    cols = list(df.columns)
    scores = {}  # (field,col) -> combined
    for f in fields:
        for col in cols:
            hs = _header_score(col, f)
            vs = _value_score(df[col], f)
            scores[(f, col)] = 0.6 * hs + 0.4 * vs

    pairs = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    used_cols, used_fields, mapping = set(), set(), {}
    for (f, col), sc in pairs:
        if f in used_fields or col in used_cols or sc <= 0:
            continue
        mapping[f] = {"column": col, "confidence": round(min(sc, 1.0), 2)}
        used_fields.add(f); used_cols.add(col)
    for f in fields:
        mapping.setdefault(f, {"column": None, "confidence": 0.0})
    return mapping
