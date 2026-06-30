"""Folder-inbox auto-sync connector (WORKS TODAY — no external API).

How it works: your billing software exports an Excel/CSV (most Indian POS tools
can auto-export on a schedule, or you drop the file manually) into a watched
`inbox/` folder. On each scheduled run this connector ingests every new file via
the same auto column-mapping, then moves it to `inbox/archive/` so it's never
imported twice. This is the realistic, free auto-sync path for an SMB.
"""
import shutil
from pathlib import Path

from .base import POSIntegration
from ..base import NormalizedBatch
from ..tabular import TabularAdapter

EXTS = (".xlsx", ".xls", ".xlsm", ".csv")


class InboxIntegration(POSIntegration):
    provider = "inbox"
    has_api = True   # functional today

    def __init__(self, credentials=None):
        super().__init__(credentials)
        self.folder = Path(self.credentials.get("folder", "inbox")).expanduser()

    def test_connection(self) -> bool:
        return self.folder.exists()

    def sync(self, since=None) -> NormalizedBatch:
        batch = NormalizedBatch()
        self.folder.mkdir(parents=True, exist_ok=True)
        archive = self.folder / "archive"
        archive.mkdir(exist_ok=True)

        ad = TabularAdapter()
        files = sorted(p for p in self.folder.iterdir()
                       if p.is_file() and p.suffix.lower() in EXTS)
        if not files:
            batch.meta["files"] = 0
            return batch

        processed = 0
        for fp in files:
            try:
                df = ad.read(str(fp))
                b = ad.normalize(df)              # auto-mapping, no human step
                batch.extend(b)
                shutil.move(str(fp), str(archive / fp.name))
                processed += 1
            except Exception as e:               # bad file -> quarantine, keep going
                bad = self.folder / "errors"
                bad.mkdir(exist_ok=True)
                shutil.move(str(fp), str(bad / fp.name))
                batch.warnings.append(f"Skipped {fp.name}: {e}")

        batch.meta["files"] = processed
        return batch
