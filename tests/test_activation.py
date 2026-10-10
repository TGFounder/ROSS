"""Offline tests: host discovery, trigger controls, and evidence safety."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ross_activation", ROOT / "benchmarks" / "activation.py")
activation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(activation)


class ActivationTest(unittest.TestCase):
    def setUp(self):
        self.cases = json.loads((ROOT / "benchmarks" / "activation-cases.json").read_text(encoding="utf-8"))
        self.plan = activation.plan(self.cases, "codex", 2, 40)

    def recorded(self, correct=True):
        kinds = {case["id"]: case["mode"] for case in self.cases}
        return [
            {"trial_id": t["trial_id"],
             "outcome": ("activated" if kinds[t["case_id"]] != "negative" else "not-activated")
             if correct else "unknown",
             "trace": "traces/run.txt" if correct else None}
            for t in self.plan["trials"]
        ]

    def trace_root(self, tmp):
        folder = Path(tmp) / "traces"
        folder.mkdir()
        (folder / "run.txt").write_text("untrusted synthetic fixture\n", encoding="utf-8")
        return tmp

    def test_corpus_has_controls(self):
        activation.validate_cases(self.cases)
        self.assertEqual({c["mode"] for c in self.cases}, {"explicit", "implicit", "negative"})

    def test_seed_is_repeatable(self):
        self.assertEqual(self.plan, activation.plan(self.cases, "codex", 2, 40))
        self.assertNotEqual(self.plan["trials"], activation.plan(self.cases, "codex", 2, 41)["trials"])

    def test_plan_detects_changed_fixtures(self):
        cases = json.loads(json.dumps(self.cases))
        cases[0]["prompt"] = "modified after planning"
        with self.assertRaises(ValueError):
            activation.score(cases, self.plan, [])

    def test_plan_rejects_duplicates(self):
        plan = json.loads(json.dumps(self.plan))
        plan["trials"][1] = plan["trials"][0]
        with self.assertRaises(ValueError):
            activation.score(self.cases, plan, [])

    def test_no_trace_root_blocks_positive_status(self):
        report = activation.score(self.cases, self.plan, self.recorded())
        self.assertEqual(report["status"], "evidence-unverified")
        self.assertEqual(report["tallies"]["implicit"]["correct"], 10)
        self.assertIsNone(next(iter(report["trace_manifest"].values()))["sha256"])

    def test_operator_score_does_not_claim_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.trace_root(tmp)
            report = activation.score(self.cases, self.plan, self.recorded(), tmp)
            self.assertEqual(report["status"], "operator-reported-pass")
            self.assertIn("does not prove automatic activation", report["evidence_limit"])
            self.assertEqual(
                next(iter(report["trace_manifest"].values()))["sha256"],
                hashlib.sha256(b"untrusted synthetic fixture\n").hexdigest())

    def test_unknown_is_inconclusive(self):
        report = activation.score(self.cases, self.plan, self.recorded(correct=False))
        self.assertEqual(report["status"], "inconclusive")

    def test_incomplete_is_not_success(self):
        report = activation.score(self.cases, self.plan, self.recorded()[:-1])
        self.assertEqual(report["status"], "incomplete")

    def test_missing_trigger_and_false_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.trace_root(tmp)
            records = self.recorded()
            implicit = next(t for t in self.plan["trials"] if t["case_id"] == "implicit-repair")
            next(r for r in records if r["trial_id"] == implicit["trial_id"])["outcome"] = "not-activated"
            negative = next(t for t in self.plan["trials"] if t["case_id"] == "negative-greeting")
            next(r for r in records if r["trial_id"] == negative["trial_id"])["outcome"] = "activated"
            report = activation.score(self.cases, self.plan, records, tmp)
            self.assertEqual(report["status"], "activation-regression")
            self.assertEqual(report["tallies"]["implicit"]["misses"], 1)
            self.assertEqual(report["tallies"]["negative"]["misses"], 1)

    def test_missing_trace_is_rejected(self):
        records = self.recorded()
        records[0]["trace"] = None
        with self.assertRaises(ValueError):
            activation.score(self.cases, self.plan, records)

    def test_duplicate_or_unknown_record_is_rejected(self):
        records = self.recorded()
        with self.assertRaises(ValueError):
            activation.score(self.cases, self.plan, records + [records[0]])
        records[0]["trial_id"] = "unknown"
        with self.assertRaises(ValueError):
            activation.score(self.cases, self.plan, records)

    def test_traversal_symlinks_and_oversize_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.trace_root(tmp)
            for path in ("../secret", "/etc/passwd", "a//b", "x/./y", "a\\b"):
                with self.subTest(path=path):
                    with self.assertRaises(ValueError):
                        activation.trace_digest(tmp, path)
            target = Path(tmp) / "traces" / "alias"
            try:
                target.symlink_to("run.txt")
            except (OSError, NotImplementedError):
                pass
            else:
                with self.assertRaises(ValueError):
                    activation.trace_digest(tmp, "traces/alias")
            target = Path(tmp) / "traces" / "large"
            with target.open("wb") as f:
                f.seek(activation.MAX_TRACE)
                f.write(b"1")
            with self.assertRaises(ValueError):
                activation.trace_digest(tmp, "traces/large")

    def test_doctor_finds_disk_install_without_claiming_invocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, workspace = Path(tmp) / "home", Path(tmp) / "work"
            home.mkdir()
            workspace.mkdir()
            target = home / ".claude" / "skills" / "ross"
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text("---\nname: ross\ndescription: Test\n---\n", encoding="utf-8")
            report = activation.doctor("claude", home, workspace)
            self.assertEqual(report["paths"][0]["status"], "found-on-disk")
            self.assertIn("not host activation", report["warning"])

    def test_doctor_rejects_bad_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, workspace = Path(tmp) / "home", Path(tmp) / "work"
            home.mkdir()
            workspace.mkdir()
            target = workspace / ".gemini" / "skills" / "ross"
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text("# no metadata\n", encoding="utf-8")
            statuses = [x["status"] for x in activation.doctor("gemini", home, workspace)["paths"]]
            self.assertIn("invalid-frontmatter", statuses)

    def test_validates_cases(self):
        for bad in ([], [{"id": "bad"}],
                    [dict(self.cases[0], mode="negative")],
                    [dict(self.cases[2], prompt="Load Ross for this")]):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    activation.validate_cases(bad)


if __name__ == "__main__":
    unittest.main()
