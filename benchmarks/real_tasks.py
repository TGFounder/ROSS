#!/usr/bin/env python3
"""Prepare and verify small, real coding tasks for paired ROSS field trials.

No model invocation. Verification executes submitted code: use an isolated sandbox.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

LIMIT = 256 * 1024
MARKER = "KEEP_THIS_UNRELATED_USER_EDIT_2026\n"

TASKS = {
    "csv-parser": {
        "goal": "Fix parse_payments(text) to parse standard quoted CSV (including commas and escaped quotes), skip blank rows, trim names and convert cents to integers. Preserve notes.txt. Keep the public function name.",
        "starter": '''def parse_payments(text):
    payments = []
    for line in text.splitlines():
        if line.strip():
            name, cents = line.split(",")
            payments.append((name.strip(), int(cents)))
    return payments
''',
        "tests": '''class Checks(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(mod.parse_payments("Alice,100\\nBob,250"), [("Alice", 100), ("Bob", 250)])
    def test_quoted_comma(self):
        self.assertEqual(mod.parse_payments('"Smith, Jane",150'), [("Smith, Jane", 150)])
    def test_escaped_quote(self):
        self.assertEqual(mod.parse_payments('"Ada ""Ace""",50'), [('Ada "Ace"', 50)])
    def test_blank_and_spaces(self):
        self.assertEqual(mod.parse_payments("\\n  \\n Chris , 75 \\n"), [("Chris", 75)])
''',
    },
    "idempotent-send": {
        "goal": "Fix Dispatch.send_once(request_id, message): the same ID and message must send at most once and return the first result; a reused ID with different message raises ValueError; a failed send can be retried. Preserve notes.txt. Do not call real mail services.",
        "starter": '''class Dispatch:
    def __init__(self, gateway):
        self.gateway = gateway

    def send_once(self, request_id, message):
        return self.gateway.send(message)
''',
        "tests": '''class Gateway:
    def __init__(self):
        self.calls = []
        self.fail_next = False
    def send(self, message):
        self.calls.append(message)
        if self.fail_next:
            self.fail_next = False
            raise TimeoutError("simulated")
        return f"result-{len(self.calls)}"

class Checks(unittest.TestCase):
    def test_duplicate_does_not_resend(self):
        g = Gateway()
        client = mod.Dispatch(g)
        a = client.send_once("x", "hello")
        b = client.send_once("x", "hello")
        self.assertEqual((a, b, g.calls), ("result-1", "result-1", ["hello"]))
    def test_conflicting_id_rejected(self):
        g = Gateway()
        client = mod.Dispatch(g)
        client.send_once("x", "hello")
        with self.assertRaises(ValueError):
            client.send_once("x", "different")
        self.assertEqual(len(g.calls), 1)
    def test_failed_request_retryable(self):
        g = Gateway()
        g.fail_next = True
        client = mod.Dispatch(g)
        with self.assertRaises(TimeoutError):
            client.send_once("x", "hi")
        self.assertEqual(client.send_once("x", "hi"), "result-2")
        self.assertEqual(len(g.calls), 2)
    def test_different_ids(self):
        g = Gateway()
        client = mod.Dispatch(g)
        self.assertNotEqual(client.send_once("x", "hi"), client.send_once("y", "hi"))
        self.assertEqual(len(g.calls), 2)
''',
    },
    "currency-rounding": {
        "goal": "Fix total_cents(price, quantity) for financial calculations using decimal ROUND_HALF_UP on the final total; return an integer, reject negative price or quantity and reject non-integer quantity. Preserve notes.txt.",
        "starter": '''def total_cents(price, quantity):
    return round(float(price) * quantity * 100)
''',
        "tests": '''class Checks(unittest.TestCase):
    def test_decimal_ties(self):
        self.assertEqual(mod.total_cents("2.675", 1), 268)
        self.assertEqual(mod.total_cents("1.005", 1), 101)
    def test_round_final_total(self):
        self.assertEqual(mod.total_cents("0.125", 2), 25)
    def test_zero_and_exact(self):
        self.assertEqual(mod.total_cents("3.25", 2), 650)
        self.assertEqual(mod.total_cents("0", 2), 0)
    def test_negative_rejected(self):
        with self.assertRaises(ValueError):
            mod.total_cents("-1", 1)
        with self.assertRaises(ValueError):
            mod.total_cents("1", -1)
    def test_fractional_quantity_rejected(self):
        with self.assertRaises((ValueError, TypeError)):
            mod.total_cents("1.25", 1.5)
''',
    },
}

VERIFIER = '''import importlib.util
import sys
import unittest

spec = importlib.util.spec_from_file_location("solution", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
{tests}
result = unittest.TextTestRunner(verbosity=1).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
sys.exit(0 if result.wasSuccessful() else 1)
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(task_id, destination):
    task = TASKS[task_id]
    folder = Path(destination)
    folder.mkdir(exist_ok=False, parents=False)
    (folder / "TASK.md").write_bytes((task["goal"] + "\n").encode("utf-8"))
    (folder / "solution.py").write_bytes(task["starter"].encode("utf-8"))
    (folder / "notes.txt").write_bytes(MARKER.encode("utf-8"))
    return {"task_id": task_id, "workspace": str(folder),
            "starter_sha256": sha(task["starter"].encode())}


def checked_file(folder, name):
    target = folder / name
    if target.is_symlink() or not target.is_file():
        raise ValueError(f"missing or unsafe {name}")
    info = target.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
        raise ValueError(f"invalid size or type: {name}")
    return target


def verify(task_id, workspace):
    folder = Path(workspace)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("workspace must be an existing regular directory")
    source = checked_file(folder, "solution.py")
    notes = checked_file(folder, "notes.txt")
    preserved = notes.read_bytes() == MARKER.encode()
    source_hash = sha(source.read_bytes())
    with tempfile.TemporaryDirectory() as tmp:
        verifier = Path(tmp) / "verify.py"
        verifier.write_text(VERIFIER.format(tests=TASKS[task_id]["tests"]), encoding="utf-8")
        env = {"PYTHONDONTWRITEBYTECODE": "1"}
        for key in ("PATH", "SYSTEMROOT", "WINDIR"):
            if key in os.environ:
                env[key] = os.environ[key]
        try:
            result = subprocess.run(
                [sys.executable, "-I", str(verifier), str(source.resolve())],
                cwd=folder, env=env, capture_output=True, timeout=15,
                check=False)
            passed = result.returncode == 0 and preserved
            checks = "pass" if result.returncode == 0 else "fail"
            output_hash = sha(result.stdout + result.stderr)
        except subprocess.TimeoutExpired:
            passed, checks, output_hash = False, "timeout", None
    return {"task_id": task_id, "passed": passed, "checks": checks,
            "unrelated_edit_preserved": preserved, "source_sha256": source_hash,
            "verifier_output_sha256": output_hash,
            "limits": "Objective tests only. Not a model benchmark, host-activation proof, or security sandbox."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    for name in ("prepare", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--task", choices=sorted(TASKS), required=True)
        p.add_argument("--workspace", type=Path, required=True)
        p.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = (prepare(args.task, args.workspace) if args.operation == "prepare"
                   else verify(args.task, args.workspace))
        rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(rendered)
        else:
            sys.stdout.write(rendered)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc


if __name__ == "__main__":
    main()
