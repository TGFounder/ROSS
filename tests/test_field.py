"""Offline regression coverage for ROSS field-trial planning and assessment."""
import hashlib
import importlib.util
import tempfile
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("ross_field", Path(__file__).resolve().parents[1] / "benchmarks" / "field.py")
field = importlib.util.module_from_spec(spec)
spec.loader.exec_module(field)


class FieldTrialsTest(unittest.TestCase):
    def setUp(self):
        self.plan = field.make_plan([{"id": "task-a"}, {"id": "task-b"}], 3, 21)

    def records(self):
        return [{
            "trial_id": t["trial_id"], "passed": t["condition"] == "ross",
            "evidence": "artifact/verified-test-log.txt", "unauthorized_action": False,
            "false_completion": False,
            "activation": "observed" if t["condition"] == "ross" else "not-applicable",
            **({"activation_evidence": "artifact/skill-load-log.txt"} if t["condition"] == "ross" else {}),
            "cost_usd": 0.02, "duration_seconds": 1.0, "input_tokens": 100,
            "output_tokens": 20,
        } for t in self.plan["trials"]]

    def test_balanced_deterministic_and_randomized(self):
        self.assertEqual(self.plan, field.make_plan([{"id": "task-a"}, {"id": "task-b"}], 3, 21))
        self.assertNotEqual(self.plan["trials"], field.make_plan([{"id": "task-a"}, {"id": "task-b"}], 3, 22)["trials"])
        self.assertEqual(len(field.validate_plan(self.plan)), 12)

    def test_positive_signal_not_claimed_proven(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "artifact"
            folder.mkdir()
            (folder / "verified-test-log.txt").write_text("test evidence", encoding="utf-8")
            (folder / "skill-load-log.txt").write_text("host trace", encoding="utf-8")
            report = field.assess(self.plan, self.records(), evidence_root=tmp)
        self.assertEqual(report["status"], "preliminary-positive-signal")
        self.assertEqual(report["paired"]["ross_only"], 6)
        self.assertAlmostEqual(report["conditions"]["ross"]["cost_per_success_usd"], .02)
        self.assertEqual(len(report["evidence_manifest"]), 2)
        self.assertIn("not independently verified", report["evidence_level"])
        self.assertIn("No statistical superiority", report["conclusion"])

    def test_incomplete_does_not_extrapolate_cost(self):
        report = field.assess(self.plan, self.records()[:-1])
        self.assertEqual(report["status"], "incomplete")
        self.assertIsNone(report["conditions"]["baseline"]["total_cost_usd"])
        self.assertIsNone(report["conditions"]["ross"]["total_cost_usd"])

    def test_unchecked_evidence_blocks_positive_signal(self):
        report = field.assess(self.plan, self.records())
        self.assertEqual(report["status"], "evidence-unverified")
        self.assertIsNone(report["evidence_manifest"])

    def test_missing_or_directory_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(OSError):
                field.assess(self.plan, self.records(), evidence_root=tmp)
            folder = Path(tmp) / "artifact"
            folder.mkdir()
            (folder / "verified-test-log.txt").mkdir()
            (folder / "skill-load-log.txt").write_text("trace")
            with self.assertRaises(ValueError):
                field.assess(self.plan, self.records(), evidence_root=tmp)

    def test_traversal_and_absolute_paths_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for unsafe in ("../outside.txt", "/etc/passwd", "x//file", "x/./file",
                           "D:\\\\folder\\\\file", "https://example.com/evidence"):
                with self.subTest(unsafe=unsafe):
                    records = self.records()
                    records[0]["evidence"] = unsafe
                    with self.assertRaises((OSError, ValueError)):
                        field.assess(self.plan, records, evidence_root=tmp)

    def test_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "artifact"
            folder.mkdir()
            (folder / "verified-test-log.txt").write_text("test")
            try:
                (folder / "skill-load-log.txt").symlink_to("verified-test-log.txt")
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            with self.assertRaises(ValueError):
                field.assess(self.plan, self.records(), evidence_root=tmp)

    def test_hash_detects_changed_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "artifact"
            folder.mkdir()
            a = folder / "verified-test-log.txt"
            a.write_bytes(b"actual test log")
            (folder / "skill-load-log.txt").write_bytes(b"host observed")
            one = field.assess(self.plan, self.records(), evidence_root=tmp)
            self.assertEqual(one["status"], "preliminary-positive-signal")
            self.assertEqual(one["evidence_manifest"][0]["sha256"],
                             hashlib.sha256(b"host observed").hexdigest() if one["evidence_manifest"][0]["path"].endswith("skill-load-log.txt") else hashlib.sha256(b"actual test log").hexdigest())
            a.write_bytes(b"changed log")
            two = field.assess(self.plan, self.records(), evidence_root=tmp)
            self.assertNotEqual(one["evidence_manifest"], two["evidence_manifest"])

    def test_evidence_size_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "artifact"
            folder.mkdir()
            (folder / "verified-test-log.txt").write_bytes(b"a" * (field.MAX_EVIDENCE_BYTES + 1))
            (folder / "skill-load-log.txt").write_bytes(b"trace")
            with self.assertRaises(ValueError):
                field.assess(self.plan, self.records(), evidence_root=tmp)

    def test_missing_measurement_never_claimed(self):
        records = self.records()
        del records[0]["cost_usd"]
        report = field.assess(self.plan, records)
        self.assertIsNone(report["conditions"][self.plan["trials"][0]["condition"]]["total_cost_usd"])

    def test_unsafe_overrides_positive(self):
        records = self.records()
        records[0]["false_completion"] = True
        self.assertEqual(field.assess(self.plan, records)["status"], "safety-failure")

    def test_activation_unknown_blocks_comparison(self):
        records = self.records()
        next(r for r in records if r["activation"] == "observed")["activation"] = "unknown"
        self.assertEqual(field.assess(self.plan, records)["status"], "activation-unverified")

    def test_activation_cannot_be_just_claimed(self):
        records = self.records()
        next(r for r in records if r["activation"] == "observed").pop("activation_evidence")
        with self.assertRaises(ValueError):
            field.assess(self.plan, records)

    def test_rejects_duplicate_or_unknown_trials(self):
        records = self.records()
        with self.assertRaises(ValueError):
            field.assess(self.plan, records + [records[0]])
        records[0]["trial_id"] = "unknown"
        with self.assertRaises(ValueError):
            field.assess(self.plan, records)

    def test_rejects_invalid_metrics_and_type_confusion(self):
        for bad in (-1, float("nan"), "0.1", True):
            with self.subTest(bad=bad):
                records = self.records()
                records[0]["cost_usd"] = bad
                with self.assertRaises(ValueError):
                    field.assess(self.plan, records)

    def test_rejects_tampered_plan(self):
        plan = field.make_plan([{"id": "one"}], 1, 1)
        plan["trials"][0]["condition"] = plan["trials"][1]["condition"]
        with self.assertRaises(ValueError):
            field.assess(plan, [])

    def test_task_definitions_cannot_change_after_planning(self):
        tasks = [{"id": "task-a"}, {"id": "task-b"}]
        field.check_taskset(self.plan, tasks)
        tasks[0]["prompt"] = "changed"
        with self.assertRaises(ValueError):
            field.check_taskset(self.plan, tasks)

    def test_bad_task_ids(self):
        for tasks in ([], [{"id": "x"}, {"id": "x"}], [{"id": "../secret"}]):
            with self.assertRaises(ValueError):
                field.make_plan(tasks, 2, 1)


if __name__ == "__main__":
    unittest.main()
