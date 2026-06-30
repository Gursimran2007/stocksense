"""Feature B — HANDWRITTEN REGISTER OCR (beta).

Photo of a handwritten monthly sales register (mixed Hindi/English numerals,
messy) -> best-effort OCR -> candidate rows of {item, qty}. ALWAYS returns
needs_confirmation=True so the UI forces a "here's what I read, correct errors"
review before anything is saved. We NEVER auto-act on handwritten data.

OCR is pluggable. EasyOCR (Hindi+English) is used if installed; otherwise the
adapter degrades to an empty grid the owner fills in (still safe, just no
pre-fill). No paid APIs.
"""
from .base import Adapter, NormalizedBatch

# Devanagari digits -> ASCII, so "१२" reads as "12".
_DEV_DIGITS = {ord(c): str(i) for i, c in enumerate("०१२३४५६७८९")}


def _to_ascii_num(text):
    return (text or "").translate(_DEV_DIGITS)


class OCRBackend:
    """Interface: read(image_bytes) -> list of tokens {text, conf, x, y, h}."""
    available = False

    def read(self, image_bytes):
        raise NotImplementedError


class EasyOCRBackend(OCRBackend):
    """Real backend. Lazy-imports easyocr so it stays an optional dependency."""
    def __init__(self, langs=("hi", "en")):
        self._reader = None
        self._langs = list(langs)
        try:
            import easyocr  # noqa
            self.available = True
        except Exception:
            self.available = False

    def _reader_obj(self):
        if self._reader is None:
            import easyocr
            self._reader = easyocr.Reader(self._langs, gpu=False)
        return self._reader

    def read(self, image_bytes):
        import numpy as np
        from PIL import Image
        import io
        img = np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
        out = []
        for box, text, conf in self._reader_obj().readtext(img):
            ys = [p[1] for p in box]
            xs = [p[0] for p in box]
            out.append({"text": text, "conf": float(conf),
                        "x": min(xs), "y": min(ys), "h": max(ys) - min(ys)})
        return out


def _group_rows(tokens, tol_factor=0.6):
    """Group tokens into register rows by vertical position."""
    if not tokens:
        return []
    toks = sorted(tokens, key=lambda t: t["y"])
    avg_h = sum(t["h"] for t in toks) / len(toks) or 10
    tol = avg_h * tol_factor
    rows, cur, cur_y = [], [], toks[0]["y"]
    for t in toks:
        if abs(t["y"] - cur_y) <= tol:
            cur.append(t)
        else:
            rows.append(cur); cur = [t]; cur_y = t["y"]
    if cur:
        rows.append(cur)
    return rows


def _split_name_qty(row_tokens):
    """In one row, left text = item name, right-most number = qty sold."""
    row = sorted(row_tokens, key=lambda t: t["x"])
    name_parts, qty, qty_conf = [], None, 0.0
    for t in row:
        ascii_t = _to_ascii_num(t["text"]).strip()
        cleaned = ascii_t.replace(",", "")
        if cleaned.replace(".", "", 1).isdigit():
            qty = float(cleaned)             # last number wins (qty column)
            qty_conf = t["conf"]
        else:
            name_parts.append(t["text"].strip())
    name = " ".join(p for p in name_parts if p)
    conf = min([t["conf"] for t in row] + [qty_conf or 1.0])
    return name, qty, round(conf, 2)


class HandwrittenRegisterOCRAdapter(Adapter):
    name = "ocr_handwritten"
    needs_confirmation = True   # mandatory human confirm, ALWAYS

    def __init__(self, backend: OCRBackend = None):
        self.backend = backend or EasyOCRBackend()

    def normalize(self, raw, **kwargs) -> NormalizedBatch:
        """raw = image bytes. Returns candidate rows in meta['rows'] for the
        confirm grid; never writes sales itself."""
        b = NormalizedBatch(needs_confirmation=True)
        if not getattr(self.backend, "available", False):
            b.warnings.append(
                "OCR engine not installed — showing a blank grid to fill in. "
                "Install EasyOCR (pip install easyocr) for auto-read.")
            b.meta["rows"] = []
            return b

        try:
            tokens = self.backend.read(raw)
        except Exception as e:
            b.warnings.append(f"Could not read image: {e}")
            b.meta["rows"] = []
            return b

        rows = []
        for grp in _group_rows(tokens):
            name, qty, conf = _split_name_qty(grp)
            if not name and qty is None:
                continue
            rows.append({"item": name, "qty": qty or 0, "confidence": conf})
        b.meta["rows"] = rows
        b.meta["token_count"] = len(tokens)
        b.warnings.append("Handwriting is read best-effort — please check every "
                          "row before saving.")
        return b
