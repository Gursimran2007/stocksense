"""Feature C — BILLING/POS INTEGRATION interface (stickiness / lock-in moat).

Auto-sync sales + inventory from Indian SMB billing software. One interface,
one impl per provider. Target order: Vyapar (has API) -> Tally -> Marg -> Busy.

Each provider implements `sync()` -> NormalizedBatch so the rest of the system
treats POS data identically to an Excel import.
"""
from abc import ABC, abstractmethod
from ..base import NormalizedBatch


class POSIntegration(ABC):
    provider = "base"
    has_api = False

    def __init__(self, credentials: dict = None):
        self.credentials = credentials or {}

    @abstractmethod
    def sync(self, since: str = None) -> NormalizedBatch:
        """Pull sales + inventory changes since ISO date `since`."""
        ...

    def test_connection(self) -> bool:
        # TODO: ping provider auth endpoint.
        return False
