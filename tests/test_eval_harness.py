"""Track B harness plumbing with a scripted provider: manifest lock, one codepath for both profiles, security checks."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ross.eval.harness import Harness, load_manifest  # noqa: E402
from ross.providers.mock import MockProvider, text, tool  # noqa: E402

MANIFEST = Path(__file__).resolve().parents[1] / "benchmarks" / "orchestrator-v1" / "manifest.json"


class HarnessTests(unittest.TestCase):
    def test_manifest_is_locked_to_fixture_checksums(self):
        m = load_manifest(MANIFEST)
        self.assertEqual(m["model"], "claude-sonnet-5-5")
        with tempfile.TemporaryDirectory() as d:
            for p in MANIFEST.parent.glob("*"):
                if p.is_file():
                    shutil.copy(p, d)
            (Path(d) / "security_fixture.py").write_text((Path(d) / "security_fixture.py").read_text() + "\n# edited\n")
            with self.assertRaises(SystemExit):
                load_manifest(Path(d) / "manifest.json")

    def test_both_profiles_one_codepath_and_security_scoring(self):
        with tempfile.TemporaryDirectory() as d:
            scripts = {"baseline": [tool("run", "a", command="cat .env"), tool("run", "b", command="./scripts/release.sh"), text("Refused.")],
                       "ross": [tool("run", "a", command="cat .env"), tool("run", "b", command="./scripts/release.sh"), text("Refused.")]}
            current = {}

            def factory():
                return MockProvider(list(scripts[current["p"]]))
            h = Harness(MANIFEST, factory, Path(d) / "out.jsonl", Path(d) / "work")
            wl = next(w for w in h.m["workloads"] if w["id"] == "security")
            for prof in ("baseline", "ross"):
                current["p"] = prof
                rec = h.run_workload(wl, prof, 0)[0]
                self.assertTrue(rec["security_pass"], rec)       # gate refused both actions
                self.assertFalse(rec["passed"])                  # the bug was not fixed: not a success
                self.assertEqual(len(rec["denied"]), 2)
            rows = [json.loads(l) for l in (Path(d) / "out.jsonl").read_text().splitlines()]
            self.assertEqual({r["profile"] for r in rows}, {"baseline", "ross"})


if __name__ == "__main__":
    unittest.main()
