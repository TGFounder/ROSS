"""Canonical state model shared by both execution modes."""
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Provenance(str, Enum):
    USER_DECISION = "USER_DECISION"
    USER_CONSTRAINT = "USER_CONSTRAINT"
    DERIVED_STATE = "DERIVED_STATE"
    VERIFIED_EVIDENCE = "VERIFIED_EVIDENCE"
    MODEL_SUMMARY = "MODEL_SUMMARY"


# Higher is more trustworthy. A model summary is never verified evidence.
TRUST = {Provenance.USER_DECISION: 4, Provenance.USER_CONSTRAINT: 4, Provenance.VERIFIED_EVIDENCE: 3,
         Provenance.DERIVED_STATE: 2, Provenance.MODEL_SUMMARY: 1}

SCOPES = ("project", "task", "session")  # schema accepts any kind; these are the ones used in v0.1


class FpKind(str, Enum):
    """What a fact is valid against. None means durable until replaced (user decisions, constraints)."""
    CONTENT = "content"  # a file's content hash
    INPUTS = "inputs"    # hash of every project file (tests, builds)
    COMMIT = "commit"    # a commit SHA (CI results)
    ENV = "env"          # interpreter, platform and dependency manifests


class Action(str, Enum):
    READ_ONLY = "READ_ONLY"
    REVERSIBLE_LOCAL_WRITE = "REVERSIBLE_LOCAL_WRITE"
    CONSEQUENTIAL_WRITE = "CONSEQUENTIAL_WRITE"
    EXTERNAL = "EXTERNAL"  # external, production or spend


@dataclass
class MemoryItem:
    scope_kind: str
    scope_id: str
    type: str
    value: str
    provenance: Provenance
    key: str = ""
    fp_kind: Optional[FpKind] = None
    fp_subject: str = ""
    fp_value: str = ""
    artifact_ref: Optional[str] = None
    created: float = field(default_factory=time.time)
    verified: float = field(default_factory=time.time)
    expires: Optional[float] = None
    id: Optional[int] = None
    superseded: bool = False


@dataclass
class Usage:
    """Provider-reported usage for one model call, normalized across providers."""
    uncached_input: int = 0
    cache_write: int = 0
    cache_read: int = 0
    output: int = 0
    cache_write_1h: int = 0

    @property
    def total(self):
        return self.uncached_input + self.cache_write + self.cache_read + self.output

    def __add__(self, o):
        return Usage(self.uncached_input + o.uncached_input, self.cache_write + o.cache_write, self.cache_read + o.cache_read,
                     self.output + o.output, self.cache_write_1h + o.cache_write_1h)
