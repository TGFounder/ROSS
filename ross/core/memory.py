"""Durable operational memory: the result of history, with provenance and invalidation. Retrieval is deterministic."""
import re

from . import evidence
from .models import TRUST, FpKind, MemoryItem, Provenance

# what each memory type is, by default, valid against
SINGLE_TYPES = ("goal", "next", "last_result")
LABELS = [("goal", "Goal"), ("next", "Next"), ("blocker", "Blocker"), ("constraint", "Constraint"), ("decision", "Decision"),
          ("changed", "Changed")]


class Memory:
    def __init__(self, store, root):
        self.store, self.root = store, root
        self._fp = {}

    def _current(self, kind, subject):
        k = (kind, subject)
        if k not in self._fp:
            self._fp[k] = evidence.current(self.root, kind, subject)
        return self._fp[k]

    def remember(self, scope_kind, scope_id, type, value, provenance, key="", fp_kind=None, fp_subject="", artifact_ref=None,
                 expires=None):
        fp_value = ""
        if fp_kind:
            fp_value = self._current(FpKind(fp_kind), fp_subject) or ""
            if not fp_value:
                return None  # cannot establish what this fact is valid against: do not store it as evidence
        self._fp.clear()
        return self.store.put(MemoryItem(scope_kind=scope_kind, scope_id=scope_id, type=type, key=key, value=value,
                                         provenance=Provenance(provenance), fp_kind=FpKind(fp_kind) if fp_kind else None,
                                         fp_subject=fp_subject, fp_value=fp_value, artifact_ref=artifact_ref, expires=expires))

    def is_current(self, item):
        if not item.fp_kind:
            return True  # user decisions and constraints stay durable until replaced or withdrawn
        return bool(item.fp_value) and self._current(item.fp_kind, item.fp_subject) == item.fp_value

    def recall(self, scopes, types=None, terms=None, limit=40):
        """Valid items for the given (kind, id) scopes, most trustworthy and relevant first, plus stale ones separately."""
        items = []
        for kind, sid in scopes:
            items += self.store.active(kind, sid, types)
        if terms:
            hits = {i.id for i in self.store.search(terms, limit=200)}
        else:
            hits = set()
        current, stale = [], []
        for i in items:
            (current if self.is_current(i) else stale).append(i)
        key = lambda i: (-(i.id in hits), -TRUST[i.provenance], -i.verified)
        return sorted(current, key=key)[:limit], sorted(stale, key=key)[:limit]

    def state_block(self, scopes, terms=None, budget_chars=1600, include_git=True):
        """Compact continuation state. Model summaries are labelled; stale evidence is reported as stale, never as current."""
        current, stale = self.recall(scopes, terms=terms)
        by = {}
        for i in current:
            by.setdefault(i.type, []).append(i)
        if not current and not stale:
            return ""
        lines = ["ROSS state (derived from earlier sessions; re-verify only what you change):"]
        for t, label in LABELS:
            for i in by.get(t, [])[: 1 if t in SINGLE_TYPES else 4]:
                tag = " (model summary)" if i.provenance is Provenance.MODEL_SUMMARY else ""
                lines.append(f"{label}{tag}: {i.value}")
        for i in by.get("test_result", [])[:4]:
            lines.append(f"Verified, still valid (inputs unchanged): {i.value}")
        for i in by.get("last_result", [])[:1]:
            lines.append("Last session ended with (model summary): " + i.value.replace("\n", " ")[-480:])
        for i in [s for s in stale if s.type == "test_result"][:3]:
            lines.append(f"Stale, rerun before relying on it (files changed since): {i.value}")
        g = evidence.git_identity(self.root) if include_git else {}
        if g:
            d = g["dirty"]
            lines.append(f"Git: {g['branch']} @ {g['sha']}" + (f"; uncommitted: {', '.join(d[:12])}" if d else "; clean"))
        out = ""
        for l in lines:
            if len(out) + len(l) + 1 > budget_chars:
                break
            out += l + "\n"
        return out.strip()


def terms_of(text):
    return [t.lower() for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text or "")][:40]
