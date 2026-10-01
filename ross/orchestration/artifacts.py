"""Local artifact store for large tool output: content-addressed, redacted, private, bounded, prunable.
Sensitive operations are never persisted, even redacted."""
import hashlib
import os
import re
from pathlib import Path

from ..core.redact import redact

CAP_BYTES = 64 * 1024 * 1024


class Artifacts:
    def __init__(self, root, cap=CAP_BYTES):
        self.dir = Path(root) / ".ross" / "artifacts"
        self.cap = cap

    def put(self, text, persist=True):
        """Store text; returns an id, or None when the operation is sensitive (output then exists only in this call)."""
        if not persist:
            return None
        data = redact(text).encode("utf-8", "replace")
        aid = hashlib.sha256(data).hexdigest()[:12]
        self.dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        p = self.dir / f"{aid}.txt"
        if not p.exists():
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            self.prune()
        return aid

    def get(self, aid, grep=None, lines=None, max_chars=8000):
        if not re.fullmatch(r"[0-9a-f]{12}", aid or ""):
            return "invalid artifact id"
        p = self.dir / f"{aid}.txt"
        if not p.exists():
            return f"artifact {aid} not found (pruned or deleted)"
        rows = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if grep:
            try:
                rx = re.compile(grep)
            except re.error as e:
                return f"bad pattern: {e}"
            out = "\n".join(f"{i}: {l}" for i, l in enumerate(rows, 1) if rx.search(l))
        elif lines:
            a, _, b = str(lines).partition("-")
            out = "\n".join(f"{i}: {l}" for i, l in enumerate(rows[int(a) - 1:int(b or a)], int(a)))
        else:
            out = "\n".join(rows)
        return out if len(out) <= max_chars else out[:max_chars] + f"\n[... {len(out) - max_chars:,} more chars; narrow with grep or lines]"

    def prune(self, cap=None):
        cap = self.cap if cap is None else cap
        if not self.dir.exists():
            return 0
        files = sorted(self.dir.glob("*.txt"), key=lambda p: p.stat().st_mtime)
        total, removed = sum(p.stat().st_size for p in files), 0
        while files and total > cap:
            p = files.pop(0)
            total -= p.stat().st_size
            p.unlink()
            removed += 1
        return removed
