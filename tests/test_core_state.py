"""ROSS core (orchestrated mode): SQLite state, scopes, provenance, invalidation, refusal of transcripts and credentials."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ross.core.memory import Memory  # noqa: E402
from ross.core.models import FpKind, MemoryItem, Provenance  # noqa: E402
from ross.storage.legacy_json import import_legacy  # noqa: E402
from ross.storage.sqlite import SCHEMA_VERSION, SQLiteStateStore  # noqa: E402


def repo():
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name).resolve()
    subprocess.run("git init -q && git config user.email t@t && git config user.name t", shell=True, cwd=root, check=True)
    (root / "a.py").write_text("x = 1\n")
    (root / "requirements.txt").write_text("pytest\n")
    subprocess.run("git add -A && git commit -qm i", shell=True, cwd=root, check=True)
    return tmp, root


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root = repo()
        self.store = SQLiteStateStore(self.root)
        self.mem = Memory(self.store, self.root)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_schema_versioned_private_and_ignored(self):
        self.assertEqual(self.store.db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
        self.assertEqual((self.root / ".ross" / ".gitignore").read_text(), "*\n")
        if os.name == "posix":
            self.assertEqual(os.stat(self.root / ".ross" / "ross.db").st_mode & 0o077, 0)
        self.store.close()
        SQLiteStateStore(self.root).close()  # reopen: no re-migration
        db = sqlite3.connect(str(self.root / ".ross" / "ross.db"))
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        db.commit()
        db.close()
        with self.assertRaises(RuntimeError):
            SQLiteStateStore(self.root)
        self.store = SQLiteStateStore.__new__(SQLiteStateStore)
        self.store.db = sqlite3.connect(":memory:")

    def test_supersede_and_scope_isolation(self):
        self.mem.remember("project", "p1", "goal", "ship X", Provenance.USER_DECISION)
        self.mem.remember("project", "p1", "goal", "ship Y", Provenance.USER_DECISION)
        self.mem.remember("project", "p2", "goal", "other project", Provenance.USER_DECISION)
        cur, _ = self.mem.recall([("project", "p1")])
        self.assertEqual([i.value for i in cur], ["ship Y"])
        tmp2, root2 = repo()
        other = SQLiteStateStore(root2)
        self.assertEqual(other.active(), [])  # another project never sees this project's state
        other.close()
        tmp2.cleanup()

    def test_invalidation_by_fingerprint(self):
        m = self.mem
        m.remember("project", "p", "file_fact", "a.py defines x", Provenance.DERIVED_STATE, key="a.py", fp_kind=FpKind.CONTENT, fp_subject="a.py")
        m.remember("project", "p", "test_result", "`pytest -q` passed", Provenance.VERIFIED_EVIDENCE, key="pytest", fp_kind=FpKind.INPUTS)
        m.remember("project", "p", "ci_result", "CI green", Provenance.VERIFIED_EVIDENCE, key="ci", fp_kind=FpKind.COMMIT)
        m.remember("project", "p", "env_fact", "pytest installed", Provenance.VERIFIED_EVIDENCE, key="env", fp_kind=FpKind.ENV)
        m.remember("project", "p", "constraint", "do not touch billing", Provenance.USER_CONSTRAINT)
        self.assertEqual(len(m.recall([("project", "p")])[0]), 5)
        (self.root / "a.py").write_text("x = 2\n")  # content and inputs change
        cur, stale = Memory(self.store, self.root).recall([("project", "p")])
        self.assertEqual({i.type for i in stale}, {"file_fact", "test_result"})
        block = Memory(self.store, self.root).state_block([("project", "p")])
        self.assertIn("Stale, rerun before relying on it", block)
        self.assertNotIn("still valid", block)
        subprocess.run("git commit -qam next", shell=True, cwd=self.root, check=True)
        (self.root / "requirements.txt").write_text("pytest\nrequests\n")
        cur, stale = Memory(self.store, self.root).recall([("project", "p")])
        self.assertEqual({i.type for i in cur}, {"constraint"})  # user constraint durable; ci and env now stale
        self.assertEqual({i.type for i in stale}, {"file_fact", "test_result", "ci_result", "env_fact"})

    def test_model_summary_is_labelled_not_evidence(self):
        self.mem.remember("project", "p", "next", "wire the CLI", Provenance.MODEL_SUMMARY)
        self.mem.remember("project", "p", "goal", "ship X", Provenance.USER_DECISION)
        block = self.mem.state_block([("project", "p")])
        self.assertIn("Goal: ship X", block)
        self.assertIn("Next (model summary): wire the CLI", block)

    def test_refuses_transcripts_credentials_and_bulk(self):
        with self.assertRaises(ValueError):
            self.mem.remember("session", "s", "note", "context\nHuman: hi\nAssistant: hello", Provenance.MODEL_SUMMARY)
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "anthropic-test-credential-123456"}):
            self.mem.remember("session", "s", "note", "key is anthropic-test-credential-123456", Provenance.MODEL_SUMMARY)
            raw = (self.root / ".ross" / "ross.db").read_bytes()
            self.assertNotIn(b"anthropic-test-credential-123456", raw)  # scrubbed before storage
        with self.assertRaises(ValueError):
            self.mem.remember("session", "s", "note", "x" * 5000, Provenance.MODEL_SUMMARY)
        self.mem.remember("session", "s", "note", "token=" + "Q" * 30, Provenance.MODEL_SUMMARY)
        self.assertNotIn(b"Q" * 30, (self.root / ".ross" / "ross.db").read_bytes())

    def test_evidence_needs_a_fingerprint(self):
        self.assertIsNone(self.mem.remember("project", "p", "file_fact", "gone.py has f", Provenance.DERIVED_STATE,
                                            fp_kind=FpKind.CONTENT, fp_subject="gone.py"))

    def test_search_fts_and_fallback(self):
        self.mem.remember("project", "p", "decision", "keep the existing auth architecture", Provenance.USER_DECISION, key="d1")
        self.mem.remember("project", "p", "decision", "use cents for money", Provenance.USER_DECISION, key="d2")
        self.assertEqual([i.key for i in self.store.search(["auth"])], ["d1"])
        self.store._fts = False
        self.assertEqual([i.key for i in self.store.search(["cents"])], ["d2"])

    def test_legacy_import_is_read_only_and_invalidates(self):
        d = self.root / ".ross"
        (d / "state.json").write_text('{"goal": "ship X", "next": "do Y", "constraint": ["no prod"], "changed": ["a.py"]}')
        (d / "commands.json").write_text('{"pytest -q": {"result": "pass", "inputs": "deadbeefdeadbeef"}}')
        before = (d / "state.json").read_bytes()
        self.assertEqual(import_legacy(self.store, self.root, "p"), 5)
        self.assertEqual((d / "state.json").read_bytes(), before)
        cur, stale = self.mem.recall([("project", "p")])
        self.assertIn("pytest -q", [i.key for i in stale])  # recorded inputs no longer match
        self.assertEqual({i.provenance for i in cur if i.type == "next"}, {Provenance.MODEL_SUMMARY})


if __name__ == "__main__":
    unittest.main()
