from .base import Adapter, NormalizedBatch
from .tabular import TabularAdapter
from .manual import ManualAdapter
# Later-feature stubs (importable so the UI can list them as "coming soon"):
from .ocr_printed import PrintedBillOCRAdapter
from .ocr_handwritten import HandwrittenRegisterOCRAdapter
from .supplier_price import SupplierPriceSource, StaticPriceBook
