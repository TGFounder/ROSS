"""Deterministic tests for the ROSS Efficiency Runtime (stdlib unittest)."""
import io
import json
import re
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import importlib.util  # noqa: E402

# Load the plugin runtime under its own module name so it never collides with the `ross` core package.
_spec = importlib.util.spec_from_file_location("ross_runtime", Path(__file__).resolve().parents[1] / "runtime" / "ross.py")
ross = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ross)

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
        raw = (self.root / ".ross" / "state.json").read_text(encoding="utf-8") + (self.root / ".ross" / "deltas.jsonl").read_text(encoding="utf-8")
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

    def prompt(self, text, session="s1"):
        return run_hook("UserPromptSubmit", {"cwd": str(self.root), "session_id": session, "prompt": text})

    def test_session_start_injects_nothing(self):
        self.assertEqual(run_hook("SessionStart", {"cwd": str(self.root), "session_id": "s1"}), {})

    def test_short_question_gets_no_context(self):
        self.assertEqual(self.prompt("what does x do?"), {})
        self.assertFalse((self.root / ".ross").exists())

    def test_automatic_memory_and_resume(self):
        for i in range(3):
            (self.root / f"m{i}.py").write_text(f"def f{i}():\n    return {i}\n")
        subprocess.run("git add -A && git commit -qm more", shell=True, cwd=self.root, check=True)
        self.prompt("Add a currency field to the invoice model and update all the tests")
        (self.root / "m1.py").write_text("def f1():\n    return 11\n")
        run_hook("Stop", {"cwd": str(self.root), "session_id": "s1",
                          "last_assistant_message": "Added currency to m1.\nNext: wire currency into the export"})
        st = ross.state(ross.Store(self.root))
        self.assertTrue(st["goal"].startswith("Add a currency"))
        self.assertEqual(st["next"], "wire currency into the export")
        self.assertIn("m1.py", st["changed"])
        self.assertTrue(all("__pycache__" not in c and not c.startswith("1.py") for c in st["changed"]))
        raw = "".join(p.read_text(encoding="utf-8") for p in (self.root / ".ross").glob("*.json*"))
        self.assertNotIn("transcript", raw.lower())
        ctx = self.prompt("Continue.", session="s2")["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Goal: Add a currency", ctx)
        self.assertIn("Next: wire currency", ctx)
        self.assertIn("m1.py", ctx)
        self.assertIn("f2@1", ctx)  # repo symbol map
        self.assertLess(len(ctx) / 4, 1200)
        self.assertEqual(self.prompt("Continue.", session="s2"), {})  # only once per session

    def test_large_output_compressed_and_retrievable(self):
        log = "\n".join(f"tests/test_x.py::test_{i} PASSED" for i in range(400))
        log += "\nFAILED tests/test_x.py::test_9 - assert 1 == 2\nE   assert 1 == 2\n==== 1 failed, 399 passed in 1.2s ===="
        r = run_hook("PostToolUse", {"cwd": str(self.root), "session_id": "s1", "tool_name": "Bash",
                                     "tool_input": {"command": "python3 -m pytest -v"},
                                     "tool_response": {"stdout": log, "stderr": "", "exit_code": 1}})
        view = r["hookSpecificOutput"]["updatedToolOutput"]
        self.assertLess(len(view), len(log) / 5)
        self.assertIn("FAILED tests/test_x.py::test_9", view)
        self.assertIn("1 failed, 399 passed", view)
        aid = re.search(r"artifact (\w+)", view).group(1)
        self.assertEqual(ross.artifact_view(self.store, aid), log)
        self.assertIn("test_9", ross.artifact_view(self.store, aid, grep="FAILED"))
        small = run_hook("PostToolUse", {"cwd": str(self.root), "session_id": "s1", "tool_name": "Bash",
                                         "tool_input": {"command": "ls"}, "tool_response": {"stdout": "a.py", "exit_code": 0}})
        self.assertEqual(small, {})  # small output passes through unchanged

    def test_artifact_secret_redaction_and_pruning(self):
        aid = ross.store_artifact(self.store, "token=" + "Z" * 30 + "\n" + "x" * 5000)
        self.assertNotIn("Z" * 30, ross.artifact_view(self.store, aid))
        self.assertEqual(ross.prune_artifacts(self.store, 0), 1)
        self.assertIn("not found", ross.artifact_view(self.store, aid))

    def test_reread_of_changed_file_returns_diff(self):
        f = self.root / "big.py"
        f.write_text("".join(f"def f{i}():\n    return {i}\n\n" for i in range(200)))
        subprocess.run("git add -A && git commit -qm big", shell=True, cwd=self.root, check=True)
        p = {"cwd": str(self.root), "session_id": "s1", "tool_name": "Read", "tool_input": {"file_path": str(f)},
             "tool_response": {"type": "text", "file": {"content": f.read_text(encoding="utf-8")}}}
        self.assertEqual(run_hook("PostToolUse", p), {})
        f.write_text(f.read_text(encoding="utf-8").replace("return 7\n", "return 777\n"))
        p["tool_response"] = {"type": "text", "file": {"content": f.read_text(encoding="utf-8")}}
        view = run_hook("PostToolUse", p)["hookSpecificOutput"]["updatedToolOutput"]
        self.assertIn("+    return 777", view)
        self.assertLess(len(view), len(f.read_text(encoding="utf-8")) / 5)

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
        src = RUNTIME.read_text(encoding="utf-8")
        for mod in ("socket", "urllib", "http.client", "requests"):
            self.assertNotIn(f"import {mod}", src)


if __name__ == "__main__":
    with redirect_stdout(io.StringIO()):
        pass
    unittest.main()
