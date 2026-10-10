"""Dependency-free offline checks for the real-work benchmark fixtures."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ross_real_tasks", ROOT / "benchmarks" / "real_tasks.py")
tasks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tasks)

GOOD = {
    "csv-parser": '''import csv
import io

def parse_payments(text):
    output = []
    for row in csv.reader(io.StringIO(text)):
        if not row or not any(item.strip() for item in row):
            continue
        if len(row) != 2:
            raise ValueError("invalid row")
        output.append((row[0].strip(), int(row[1].strip())))
    return output
''',
    "idempotent-send": '''class Dispatch:
    def __init__(self, gateway):
        self.gateway = gateway
        self._sent = {}

    def send_once(self, request_id, message):
        if request_id in self._sent:
            old_message, response = self._sent[request_id]
            if message != old_message:
                raise ValueError("conflicting request")
            return response
        response = self.gateway.send(message)
        self._sent[request_id] = (message, response)
        return response
''',
    "currency-rounding": '''from decimal import Decimal, ROUND_HALF_UP

def total_cents(price, quantity):
    if type(quantity) is not int:
        raise TypeError("quantity must be integer")
    amount = Decimal(str(price))
    if amount < 0 or quantity < 0:
        raise ValueError("negative amount")
    return int((amount * quantity * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
''',
}


class RealWorkTest(unittest.TestCase):
    def test_every_starter_has_real_failure(self):
        for name in tasks.TASKS:
            with self.subTest(task=name), tempfile.TemporaryDirectory() as tmp:
                workspace = Path(tmp) / name
                tasks.prepare(name, workspace)
                self.assertFalse(tasks.verify(name, workspace)["passed"])

    def test_independent_reference_solution_passes(self):
        for name, solution in GOOD.items():
            with self.subTest(task=name), tempfile.TemporaryDirectory() as tmp:
                workspace = Path(tmp) / name
                tasks.prepare(name, workspace)
                (workspace / "solution.py").write_text(solution, encoding="utf-8")
                report = tasks.verify(name, workspace)
                self.assertTrue(report["passed"], report)

    def test_preserve_unrelated_edit_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "csv"
            tasks.prepare("csv-parser", workspace)
            (workspace / "solution.py").write_text(GOOD["csv-parser"], encoding="utf-8")
            (workspace / "notes.txt").write_text("changed", encoding="utf-8")
            report = tasks.verify("csv-parser", workspace)
            self.assertFalse(report["passed"])
            self.assertEqual(report["checks"], "pass")
            self.assertFalse(report["unrelated_edit_preserved"])

    def test_cannot_overwrite_prepared_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "task"
            tasks.prepare("currency-rounding", workspace)
            with self.assertRaises(FileExistsError):
                tasks.prepare("currency-rounding", workspace)

    def test_symlinked_solution_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "task"
            tasks.prepare("currency-rounding", workspace)
            source = workspace / "solution.py"
            source.unlink()
            try:
                source.symlink_to(workspace / "notes.txt")
            except (OSError, NotImplementedError):
                self.skipTest("symlink unavailable")
            with self.assertRaises(ValueError):
                tasks.verify("currency-rounding", workspace)

    def test_missing_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "task"
            tasks.prepare("currency-rounding", workspace)
            (workspace / "solution.py").unlink()
            with self.assertRaises(ValueError):
                tasks.verify("currency-rounding", workspace)


if __name__ == "__main__":
    unittest.main()
