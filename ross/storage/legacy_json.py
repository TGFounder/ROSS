"""Read-only importer for the plugin champion's JSON state (.ross/state.json, commands.json). Never writes legacy files."""
import json
from pathlib import Path

from ..core.models import FpKind, MemoryItem, Provenance

KIND_MAP = {"goal": ("goal", Provenance.USER_DECISION), "constraint": ("constraint", Provenance.USER_CONSTRAINT),
            "preserve": ("constraint", Provenance.USER_CONSTRAINT), "next": ("next", Provenance.MODEL_SUMMARY),
            "blocker": ("blocker", Provenance.MODEL_SUMMARY), "decision": ("decision", Provenance.MODEL_SUMMARY),
            "fact": ("fact", Provenance.MODEL_SUMMARY), "last_result": ("last_result", Provenance.MODEL_SUMMARY)}


def read_legacy(root):
    d = Path(root) / ".ross"

    def load(name):
        try:
            return json.loads((d / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    return load("state.json"), load("commands.json")


def import_legacy(store, root, scope_id="project"):
    """Copy legacy state into SQLite with conservative provenance. Legacy test passes keep their recorded inputs hash, so
    they are only current if the files are still identical."""
    st, cmds = read_legacy(root)
    n = 0
    for kind, value in st.items():
        if kind not in KIND_MAP or not value:
            continue
        t, prov = KIND_MAP[kind]
        for i, v in enumerate(value if isinstance(value, list) else [value]):
            store.put(MemoryItem(scope_kind="project", scope_id=scope_id, type=t, key=f"legacy-{kind}-{i}" if isinstance(value, list) else "",
                                 value=str(v)[:2000], provenance=prov))
            n += 1
    if st.get("changed"):
        store.put(MemoryItem(scope_kind="project", scope_id=scope_id, type="changed", value=", ".join(st["changed"][:30]),
                             provenance=Provenance.DERIVED_STATE))
        n += 1
    for cmd, rec in cmds.items():
        if rec.get("result") == "pass" and rec.get("inputs"):
            store.put(MemoryItem(scope_kind="project", scope_id=scope_id, type="test_result", key=cmd, value=f"`{cmd}` passed",
                                 provenance=Provenance.VERIFIED_EVIDENCE, fp_kind=FpKind.INPUTS, fp_value=rec["inputs"]))
            n += 1
    return n
