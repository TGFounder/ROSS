"""Versioned SQLite state at <project>/.ross/ross.db. Large content lives in .ross/artifacts, never in the database."""
import os
import sqlite3
import time
from pathlib import Path

from ..core.models import FpKind, MemoryItem, Provenance
from ..core.redact import live_credentials, redact
from .base import StateStore

SCHEMA_VERSION = 1
MAX_VALUE = 2000  # characters; results of history, not transcripts
MIGRATIONS = {
    1: [
        """CREATE TABLE memory(id INTEGER PRIMARY KEY, scope_kind TEXT NOT NULL, scope_id TEXT NOT NULL, type TEXT NOT NULL,
           key TEXT NOT NULL DEFAULT '', value TEXT NOT NULL, provenance TEXT NOT NULL, fp_kind TEXT, fp_subject TEXT NOT NULL DEFAULT '',
           fp_value TEXT NOT NULL DEFAULT '', artifact_ref TEXT, created REAL NOT NULL, verified REAL NOT NULL, expires REAL,
           superseded INTEGER NOT NULL DEFAULT 0)""",
        "CREATE INDEX ix_memory_active ON memory(scope_kind, scope_id, type, key, superseded)",
        """CREATE TABLE usage(id INTEGER PRIMARY KEY, run_id TEXT, session_id TEXT, profile TEXT, provider TEXT, model TEXT,
           call_index INTEGER, uncached INTEGER, cache_write INTEGER, cache_write_1h INTEGER, cache_read INTEGER, output INTEGER,
           cost REAL, cost_class TEXT, price_version TEXT, ts REAL)""",
        "CREATE TABLE metrics(id INTEGER PRIMARY KEY, ts REAL, kind TEXT, value REAL, cls TEXT, session_id TEXT, detail TEXT)",
    ],
}
TRANSCRIPT_MARKERS = ("\nHuman:", "\nAssistant:", "\nuser:", "\nassistant:", '"role": "user"', '"role": "assistant"')


class SQLiteStateStore(StateStore):
    def __init__(self, root):
        self.root = Path(root)
        self.dir = self.root / ".ross"
        self.path = self.dir / "ross.db"
        self._fts = None
        self.dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        gi = self.dir / ".gitignore"
        if not gi.exists():
            gi.write_text("*\n")
        new = not self.path.exists()
        self.db = sqlite3.connect(str(self.path))
        if new and os.name == "posix":
            os.chmod(self.path, 0o600)
        self._migrate()

    def _migrate(self):
        ver = self.db.execute("PRAGMA user_version").fetchone()[0]
        if ver > SCHEMA_VERSION:
            raise RuntimeError(f"ross.db schema {ver} is newer than this ROSS ({SCHEMA_VERSION}); upgrade ROSS")
        with self.db:
            for v in range(ver + 1, SCHEMA_VERSION + 1):
                for stmt in MIGRATIONS[v]:
                    self.db.execute(stmt)
                self.db.execute(f"PRAGMA user_version = {v}")
        try:
            with self.db:
                self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(value, content='memory', content_rowid='id')")
            self._fts = True
        except sqlite3.OperationalError:
            self._fts = False  # FTS5 unavailable: LIKE fallback

    @property
    def fts(self):
        return self._fts

    @staticmethod
    def _clean(value):
        value = redact(str(value))
        for cred in live_credentials():
            if cred in value:
                raise ValueError("refusing to store a credential")
        if any(m in value for m in TRANSCRIPT_MARKERS):
            raise ValueError("refusing to store transcript text; store the result of history instead")
        if len(value) > MAX_VALUE:
            raise ValueError(f"memory values are capped at {MAX_VALUE} characters; keep large content in artifacts")
        return value

    def put(self, item):
        value = self._clean(item.value)
        now = time.time()
        with self.db:
            self.db.execute("UPDATE memory SET superseded=1 WHERE scope_kind=? AND scope_id=? AND type=? AND key=? AND superseded=0",
                            (item.scope_kind, item.scope_id, item.type, item.key))
            cur = self.db.execute(
                "INSERT INTO memory(scope_kind,scope_id,type,key,value,provenance,fp_kind,fp_subject,fp_value,artifact_ref,created,verified,expires)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (item.scope_kind, item.scope_id, item.type, item.key, value, Provenance(item.provenance).value,
                 FpKind(item.fp_kind).value if item.fp_kind else None, item.fp_subject, item.fp_value or "", item.artifact_ref,
                 item.created or now, item.verified or now, item.expires))
            if self._fts:
                self.db.execute("INSERT INTO memory_fts(rowid, value) VALUES(?, ?)", (cur.lastrowid, value))
        return cur.lastrowid

    def _row(self, r):
        return MemoryItem(id=r[0], scope_kind=r[1], scope_id=r[2], type=r[3], key=r[4], value=r[5], provenance=Provenance(r[6]),
                          fp_kind=FpKind(r[7]) if r[7] else None, fp_subject=r[8], fp_value=r[9], artifact_ref=r[10],
                          created=r[11], verified=r[12], expires=r[13], superseded=bool(r[14]))

    def active(self, scope_kind=None, scope_id=None, types=None):
        q, args = "SELECT * FROM memory WHERE superseded=0 AND (expires IS NULL OR expires > ?)", [time.time()]
        if scope_kind:
            q += " AND scope_kind=?"
            args.append(scope_kind)
        if scope_id:
            q += " AND scope_id=?"
            args.append(scope_id)
        if types:
            q += f" AND type IN ({','.join('?' * len(types))})"
            args += list(types)
        return [self._row(r) for r in self.db.execute(q + " ORDER BY verified DESC", args)]

    def search(self, terms, limit=50):
        terms = [t for t in terms if t.isalnum() and len(t) > 2][:12]
        if not terms:
            return []
        if self._fts:
            q = " OR ".join(f'"{t}"' for t in terms)
            rows = self.db.execute("SELECT m.* FROM memory_fts f JOIN memory m ON m.id=f.rowid WHERE memory_fts MATCH ? AND m.superseded=0 "
                                   "ORDER BY rank LIMIT ?", (q, limit)).fetchall()
        else:
            like = " OR ".join("value LIKE ?" for _ in terms)
            rows = self.db.execute(f"SELECT * FROM memory WHERE superseded=0 AND ({like}) LIMIT ?", [f"%{t}%" for t in terms] + [limit]).fetchall()
        return [self._row(r) for r in rows]

    def supersede(self, item_id):
        with self.db:
            self.db.execute("UPDATE memory SET superseded=1 WHERE id=?", (item_id,))

    def touch(self, item_id):
        with self.db:
            self.db.execute("UPDATE memory SET verified=? WHERE id=?", (time.time(), item_id))

    def record_usage(self, row):
        cols = ("run_id", "session_id", "profile", "provider", "model", "call_index", "uncached", "cache_write", "cache_write_1h",
                "cache_read", "output", "cost", "cost_class", "price_version")
        with self.db:
            self.db.execute(f"INSERT INTO usage({','.join(cols)}, ts) VALUES({','.join('?' * len(cols))}, ?)",
                            [row.get(c) for c in cols] + [time.time()])

    def usage(self, run_id=None):
        cur = self.db.execute("SELECT * FROM usage" + (" WHERE run_id=?" if run_id else ""), (run_id,) if run_id else ())
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    def metric(self, kind, value, cls, session_id=None, detail=None):
        assert cls in ("MEASURED", "COUNTED", "ESTIMATED", "INFERRED")
        with self.db:
            self.db.execute("INSERT INTO metrics(ts,kind,value,cls,session_id,detail) VALUES(?,?,?,?,?,?)",
                            (time.time(), kind, value, cls, session_id, redact(detail) if detail else None))

    def metrics(self):
        return self.db.execute("SELECT kind, cls, SUM(value) FROM metrics GROUP BY kind, cls").fetchall()

    def close(self):
        self.db.close()
