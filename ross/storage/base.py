"""Storage interface. The orchestrator uses SQLite; the plugin champion keeps its JSON files until migrated."""
from abc import ABC, abstractmethod


class StateStore(ABC):
    @abstractmethod
    def put(self, item):
        """Insert an item; an active item with the same scope, type and key is superseded. Returns the id."""

    @abstractmethod
    def active(self, scope_kind=None, scope_id=None, types=None):
        """Active (not superseded, not expired) items; validity against fingerprints is checked by the memory layer."""

    @abstractmethod
    def search(self, terms, limit=50):
        """Lexical search over active values (FTS when available)."""

    @abstractmethod
    def supersede(self, item_id):
        """Mark an item superseded (withdrawn or replaced)."""

    @abstractmethod
    def record_usage(self, row):
        """Append one model call's usage row."""

    @abstractmethod
    def usage(self, run_id=None):
        """Usage rows, optionally for one run."""

    @abstractmethod
    def metric(self, kind, value, cls, session_id=None, detail=None):
        """Append a telemetry row (cls: MEASURED, COUNTED, ESTIMATED or INFERRED)."""
