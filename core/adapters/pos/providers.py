"""Feature C — POS connectors.

  inbox  -> WORKS TODAY (folder export auto-import, see inbox.py)
  tally  -> REAL connector to Tally's local XML/HTTP gateway (needs Tally running)
  vyapar -> stub: needs partner API key (no public API)
  marg / busy -> stubs

Registry at bottom lets the UI / sync job list providers.
"""
import re
import urllib.request
import xml.etree.ElementTree as ET

from .base import POSIntegration
from .inbox import InboxIntegration
from ..base import NormalizedBatch


def _num(s, default=0.0):
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(s)) or 0)
    except ValueError:
        return default


# Tally request: current Stock Summary (closing balance per item).
_TALLY_STOCK_XML = """<ENVELOPE>
 <HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>
 <BODY><EXPORTDATA><REQUESTDESC>
   <REPORTNAME>Stock Summary</REPORTNAME>
   <STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES>
 </REQUESTDESC></EXPORTDATA></BODY>
</ENVELOPE>"""


class TallyIntegration(POSIntegration):
    """Real connector. Tally Prime/ERP9 must have the gateway on (default
    http://localhost:9000). Pulls current stock per item -> inventory rows."""
    provider = "tally"
    has_api = True

    def __init__(self, credentials=None):
        super().__init__(credentials)
        self.url = self.credentials.get("url", "http://localhost:9000")

    def test_connection(self) -> bool:
        try:
            urllib.request.urlopen(self.url, timeout=3)
            return True
        except Exception:
            return False

    def _post(self, xml, timeout=15):
        req = urllib.request.Request(
            self.url, data=xml.encode("utf-8"),
            headers={"Content-Type": "text/xml"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "ignore")

    def sync(self, since=None) -> NormalizedBatch:
        b = NormalizedBatch()
        try:
            raw = self._post(_TALLY_STOCK_XML)
        except Exception as e:
            b.warnings.append(
                f"Tally gateway not reachable at {self.url} ({e}). "
                "Open Tally and enable: F1 > Connectivity > 'Act as Server'.")
            return b
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            b.warnings.append(f"Could not parse Tally response: {e}")
            return b
        # Tally Stock Summary nests STOCKITEM-like rows; pull name + closing qty.
        for item in root.iter():
            tag = item.tag.upper()
            if "STOCKITEM" in tag or tag.endswith("DSPACCNAME"):
                name = (item.findtext("DSPDISPNAME")
                        or item.findtext(".//DSPDISPNAME") or "").strip()
                qty = item.findtext(".//DSPCLQTY") or item.findtext(".//CLOSINGQTY")
                if name:
                    b.products.append({"sku": name, "name": name, "unit_cost": 0})
                    b.inventory.append({"sku": name, "stock": _num(qty)})
        if not b.products:
            b.warnings.append("Connected to Tally but found no stock items.")
        b.meta["provider"] = "tally"
        return b


class VyaparIntegration(POSIntegration):
    provider = "vyapar"
    has_api = True   # priority target, but API access needs a partner key

    def sync(self, since=None) -> NormalizedBatch:
        # TODO(C-vyapar): with an API key, GET sales + items and map to schema.
        # No public/free API -> until creds exist, route Vyapar exports via inbox.
        raise NotImplementedError(
            "Vyapar API needs a partner key. For now export from Vyapar to the "
            "inbox folder and use the 'inbox' connector.")


class MargIntegration(POSIntegration):
    provider = "marg"

    def sync(self, since=None) -> NormalizedBatch:
        # TODO(C-marg): integrate Marg ERP export/API.
        raise NotImplementedError("Marg sync not implemented in v1.")


class BusyIntegration(POSIntegration):
    provider = "busy"

    def sync(self, since=None) -> NormalizedBatch:
        # TODO(C-busy): integrate Busy accounting export/API.
        raise NotImplementedError("Busy sync not implemented in v1.")


REGISTRY = {p.provider: p for p in
            (InboxIntegration, TallyIntegration, VyaparIntegration,
             MargIntegration, BusyIntegration)}
