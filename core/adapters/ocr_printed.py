"""Feature A — PRINTED-BILL / PO OCR adapter.  [STUB — interface only]

Plan: photo/PDF of a printed bill or purchase order -> OCR (reliable path,
e.g. Tesseract / PaddleOCR / a cloud OCR) -> line-item parser -> canonical schema.
Printed text is high-trust, so needs_confirmation stays False, but we still
surface a parse confidence in meta for review.

Plug-in point: implement `normalize(image_or_pdf_bytes)` and return a
NormalizedBatch of products + (optionally) sales/inventory rows.
"""
from .base import Adapter, NormalizedBatch


class PrintedBillOCRAdapter(Adapter):
    name = "ocr_printed"
    needs_confirmation = False

    def normalize(self, raw, **kwargs) -> NormalizedBatch:
        # TODO(A): run OCR -> detect line-item table -> parse sku/name/qty/rate.
        raise NotImplementedError(
            "Printed-bill OCR not implemented in v1. "
            "Wire an OCR engine here and emit canonical rows.")
