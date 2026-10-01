"""Deterministic tests for the ROSS Efficiency Runtime (stdlib unittest)."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import ross  # noqa: E402

RUNTIME = Path(ross.__file__)


def run_hook(event, payload):
    p = subprocess.run([sys.executable, str(RUNTIME), "hook", event], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout) if p.stdout.strip() else {}


def decision(resp):
    return (resp.get("hookSpecificOutput") or {}).get("permissionDecision")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for c in ("git init -q", "git config user.email t@t", "git config user.name t"):
            subprocess.run(c, shell=True, cwd=self.root, check=True)
        (self.root / "a.py").write_text("x = 1\n")
        subprocess.run("git add -A && git commit -qm init", shell=True, cwd=self.root, check=True)
        self.store = ross.Store(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def bash(self, event, cmd, session="s1", failed=None, output=""):
        p = {"cwd": str(self.root), "session_id": session, "tool_name": "Bash", "tool_input": {"command": cmd}}
        if event != "PreToolUse":
            p["tool_response"] = {"stdout": output, "stderr": "", "exit_code": 1 if failed else 0}
        return run_hook(event, p)


class StateTests(Base):
    def test_delta_only_and_restart_persistence(self):
        self.assertTrue(ross.note(self.store, "goal", "ship release"))
        self.assertFalse(ross.note(self.store, "goal", "ship release"))  # unchanged: nothing written
        ross.note(self.store, "decision", "keep backend")
        deltas = self.store.lines("deltas.jsonl")
        self.assertEqual(len(deltas), 2)
        fresh = ross.Store(self.root)  # simulated restart
        self.assertEqual(ross.state(fresh)["goal"], "ship release")
        self.assertNotIn("transcript", json.dumps(ross.state(fresh)))

    def test_context_is_budgeted_and_minimal(self):
        self.assertEqual(ross.context(self.store), "")  # nothing recorded: inject nothing
        ross.note(self.store, "goal", "g")
        for i in range(40):
            ross.note(self.store, "decision", f"decision number {i} " + "x" * 80)
        ctx = ross.context(self.store, budget=120)
        self.assertLessEqual(len(ctx), 120 * 4)
        self.assertIn("Goal: g", ctx)

    def test_checkpoint_writes_only_on_change(self):
        self.assertTrue(ross.checkpoint(self.store, "next step"))
        self.assertFalse(ross.checkpoint(self.store))
        (self.root / "b.py").write_text("y=2\n")
        self.assertTrue(ross.checkpoint(self.store))

    def test_secret_filter(self):
        fake = "sk" + "-proj-" + "ABCDEFGHIJKLMNOPQRSTUV"
        ross.note(self.store, "fact", "api_key=" + fake + " and gh" + "p_" + "a" * 36 + " password: hunter2hunter2")
        raw = (self.root / ".ross" / "state.json").read_text() + (self.root / ".ross" / "deltas.jsonl").read_text()
        self.assertNotIn("ABCDEFGHIJKLMNOP", raw)
        self.assertNotIn("hunter2", raw)
        self.assertNotIn("a" * 36, raw)

    def test_permissions_and_forget(self):
        ross.note(self.store, "blocker", "metadata")
        if os.name == "posix":
            self.assertEqual(os.stat(self.root / ".ross").st_mode & 0o077, 0)
            self.assertEqual(os.stat(self.root / ".ross" / "state.json").st_mode & 0o077, 0)
        ross.forget(self.store, ["blocker", "metadata"])
        self.assertEqual(ross.state(self.store).get("blocker"), [])
        ross.forget(self.store, ["--project"])
        self.assertFalse((self.root / ".ross").exists())

    def test_state_is_gitignored(self):
        ross.note(self.store, "goal", "g")
        self.assertNotIn(".ross", subprocess.run("git status --porcelain", shell=True, cwd=self.root, capture_output=True, text=True).stdout)


class HookTests(Base):
    def test_duplicate_read_blocked_then_invalidated_on_change(self):
        f = str(self.root / "a.py")
        p = {"cwd": str(self.root), "session_id": "s1", "tool_name": "Read", "tool_input": {"file_path": f}}
        self.assertIsNone(decision(run_hook("PreToolUse", p)))
        run_hook("PostToolUse", p)
        self.assertEqual(decision(run_hook("PreToolUse", p)), "deny")  # unchanged reread
        self.assertIsNone(decision(run_hook("PreToolUse", dict(p, session_id="s2"))))  # new session: allowed
        Path(f).write_text("x = 2\n")
        self.assertIsNone(decision(run_hook("PreToolUse", p)))  # changed: must re-read

    def test_test_reuse_and_invalidation(self):
        cmd = "python3 -m pytest -q"
        self.bash("PostToolUse", cmd, output="3 passed in 0.1s")
        self.assertEqual(decision(self.bash("PreToolUse", cmd)), "deny")
        self.assertIsNone(decision(self.bash("PreToolUse", cmd + f" # {ross.RERUN_MARK}")))
        (self.root / "a.py").write_text("x = 3\n")  # relevant change invalidates
        self.assertIsNone(decision(self.bash("PreToolUse", cmd)))

    def test_failed_test_is_never_reused_as_pass(self):
        cmd = "npm test"
        self.bash("PostToolUse", cmd, failed=True, output="1 failed")
        self.assertIsNone(decision(self.bash("PreToolUse", cmd)))

    def test_failure_loop_stops_third_identical_attempt(self):
        cmd = "make build"
        for _ in range(2):
            self.assertIsNone(decision(self.bash("PreToolUse", cmd)))
            self.bash("PostToolUse", cmd, failed=True, output="Error: missing header foo.h")
        self.assertEqual(decision(self.bash("PreToolUse", cmd)), "deny")
        (self.root / "a.py").write_text("changed\n")  # new information: allowed again
        self.assertIsNone(decision(self.bash("PreToolUse", cmd)))

    def test_session_start_hydrates_only_when_state_exists(self):
        p = {"cwd": str(self.root), "session_id": "s9", "hook_event_name": "SessionStart"}
        empty = run_hook("SessionStart", p)["hookSpecificOutput"]["additionalContext"]
        self.assertLess(len(empty) / 4, 120)  # only the short rules digest when no state exists
        ross.note(self.store, "goal", "finish refactor")
        ctx = run_hook("SessionStart", p)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("finish refactor", ctx)

    def test_usage_is_measured_from_transcript(self):
        t = self.root / "t.jsonl"
        t.write_text("\n".join(json.dumps({"message": {"id": f"m{i}", "usage": {"input_tokens": 10, "output_tokens": 5}}}) for i in (1, 1, 2)))
        ross.note(self.store, "goal", "g")
        run_hook("Stop", {"cwd": str(self.root), "session_id": "s1", "transcript_path": str(t)})
        s = ross.Store(self.root).load("sessions.json", {})["s1"]
        self.assertEqual((s["input"], s["output"], s["messages"]), (20, 10, 2))  # duplicate message ids counted once

    def test_hook_never_breaks_host_on_bad_input(self):
        p = subprocess.run([sys.executable, str(RUNTIME), "hook", "PreToolUse"], input="not json", capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_no_network_imports(self):
        src = RUNTIME.read_text()
        for mod in ("socket", "urllib", "http.client", "requests"):
            self.assertNotIn(f"import {mod}", src)


if __name__ == "__main__":
    with redirect_stdout(io.StringIO()):
        pass
    unittest.main()
