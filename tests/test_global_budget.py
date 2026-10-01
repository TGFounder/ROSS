"""Run-wide hard spend governor: one cap shared by every session and profile in an evaluation run (offline, no live model)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ross.core.budget import Budget, BudgetExceeded, GlobalBudgetExhausted, Governor, RunBudget  # noqa: E402
from ross.core.models import Usage  # noqa: E402
from ross.eval.harness import NOT_RUN_GLOBAL, Harness  # noqa: E402
from ross.orchestration.loop import Session  # noqa: E402
from ross.orchestration.profile import Profile  # noqa: E402
from ross.providers.base import ModelResponse, ProviderError, estimate_tokens  # noqa: E402
from ross.providers.mock import MockProvider, text, tool  # noqa: E402

MANIFEST = Path(__file__).resolve().parents[1] / "benchmarks" / "orchestrator-v1" / "manifest.json"
RATES = {"input": 2.0, "output": 10.0, "cache_write_5m": 2.5, "cache_write_1h": 4.0, "cache_read": 0.2}


def make_repo():
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name).resolve()
    (root / "a.py").write_text("x = 1\n")
    subprocess.run("git init -q && git config user.email t@t && git config user.name t && git add -A && git commit -qm i",
                   shell=True, cwd=root, check=True)
    return tmp, root


class WorstCaseProvider(MockProvider):
    """Every call bills its full worst case: all input as 1h cache writes plus the entire output allowance.
    Counts every create() attempt, so a refused request is provably never sent."""

    def __init__(self, steps=1000, fail_first=0, maybe_billed=True):
        super().__init__([tool("inspect", f"t{i}", path="a.py") for i in range(steps)])
        self.attempts, self.fail_first, self.maybe_billed = 0, fail_first, maybe_billed

    def create(self, request):
        self.attempts += 1
        if self.attempts <= self.fail_first:
            raise ProviderError("overloaded", status=529, retryable=True, maybe_billed=self.maybe_billed)
        self.requests.append(request)
        out = self.script.pop(0)(request)
        n = estimate_tokens(request)
        return ModelResponse(content=out, stop_reason="tool_use",
                             usage=Usage(cache_write=n, cache_write_1h=n, output=request.max_output))


class GovernorUnit(unittest.TestCase):
    def gov(self, session_usd, run):
        return Governor(Budget(max_usd=session_usd), "anthropic", "claude-sonnet-5-5", RATES, run_budget=run)

    def test_c_request_must_fit_both_caps(self):
        run = RunBudget(1.0)
        g = self.gov(0.5, run)
        w = g.worst_case(10000, 1000)  # 0.04 + 0.01 = 0.05
        self.assertAlmostEqual(w, 0.05)
        g.admit(10000, 1000)  # fits both
        run.add(0.97)  # global nearly spent; session still has $0.50
        with self.assertRaises(GlobalBudgetExhausted):
            g.admit(10000, 1000)
        self.assertTrue(run.exhausted)
        g2 = self.gov(0.01, RunBudget(5.0))  # session cap binds while global has room
        with self.assertRaises(BudgetExceeded) as cm:
            g2.admit(10000, 1000)
        self.assertNotIsInstance(cm.exception, GlobalBudgetExhausted)

    def test_e_possibly_billed_failure_charges_worst_case_globally(self):
        run = RunBudget(1.0)
        g = self.gov(1.0, run)
        g.charge_failed_attempt(10000, 1000)
        self.assertAlmostEqual(run.spent_usd, 0.05)
        self.assertAlmostEqual(g.spent_usd, 0.05)

    def test_completed_call_charges_global(self):
        run = RunBudget(1.0)
        g = self.gov(1.0, run)
        c = g.charge(Usage(uncached_input=1000, output=100))
        self.assertAlmostEqual(run.spent_usd, c)

    def test_no_pricing_cannot_promise_a_global_cap(self):
        with self.assertRaises(BudgetExceeded):
            Governor(Budget(), "unknown", "model-x", run_budget=RunBudget(5.0))


class SessionLevel(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root = make_repo()

    def tearDown(self):
        self.tmp.cleanup()

    def session(self, prov, profile, run, session_usd=1.0, max_output=2000):
        return Session(self.root, prov, profile, Budget(max_usd=session_usd, max_calls=100), "Inspect a.py and report.",
                       rate_override=RATES, max_output=max_output, run_budget=run)

    def test_a_global_budget_is_shared_across_baseline_and_ross(self):
        run = RunBudget(0.30)
        r1 = self.session(WorstCaseProvider(), Profile.baseline(), run).run()
        spent_after_base = run.spent_usd
        self.assertGreater(spent_after_base, 0)
        p2 = WorstCaseProvider()
        r2 = self.session(p2, Profile.ross(), run).run()
        self.assertEqual(r1.status, "budget")
        self.assertEqual(r2.status, "budget")
        self.assertLessEqual(run.spent_usd, 0.30 + 1e-12)
        self.assertAlmostEqual(run.spent_usd, r1.cost_usd + r2.cost_usd, places=5)
        self.assertTrue(run.exhausted)

    def test_b_session_cap_still_applies_under_generous_global(self):
        run = RunBudget(5.0)
        r = self.session(WorstCaseProvider(), Profile.baseline(), run, session_usd=0.10).run()
        self.assertEqual(r.status, "budget")
        self.assertLessEqual(r.cost_usd, 0.10 + 1e-12)
        self.assertFalse(run.exhausted)

    def test_d_retries_cannot_escape_the_global_cap(self):
        # First attempt fails (possibly billed, retryable): its worst case is charged, then the retry must be re-admitted.
        probe = self.session(WorstCaseProvider(), Profile.baseline(), RunBudget(100.0))
        req = probe._request([{"role": "user", "content": [{"type": "text", "text": "x"}]}], 2000)
        one = Governor(Budget(), "anthropic", "claude-sonnet-5-5", RATES).worst_case(estimate_tokens(req) * 2, 2000)
        run = RunBudget(one * 1.5)  # room for the failed attempt, not for its retry
        prov = WorstCaseProvider(fail_first=1)
        r = self.session(prov, Profile.baseline(), run).run()
        self.assertEqual(r.status, "budget")
        self.assertEqual(prov.attempts, 1)  # the retry was refused before it reached the provider
        self.assertLessEqual(run.spent_usd, run.max_usd + 1e-12)
        self.assertGreater(run.spent_usd, 0)  # the possibly billed failure was charged

    def test_g_exhausted_global_budget_makes_no_provider_call(self):
        run = RunBudget(0.0001)
        prov = WorstCaseProvider()
        r = self.session(prov, Profile.ross(), run).run()
        self.assertEqual((r.status, r.calls, prov.attempts), ("budget", 0, 0))
        self.assertIn("global run budget", r.detail)


class HarnessLevel(unittest.TestCase):
    def test_f_fourteen_session_mocked_evaluation_never_exceeds_five_dollars(self):
        with tempfile.TemporaryDirectory() as d:
            providers = []

            def factory():
                p = WorstCaseProvider()
                p.model = "claude-sonnet-5-5"
                providers.append(p)
                return p
            h = Harness(MANIFEST, factory, Path(d) / "out.jsonl", Path(d) / "work", max_total_usd=5.0)
            total_sessions = sum(len(w["sessions"]) for w in h.m["workloads"]) * 2
            self.assertEqual(total_sessions, 14)
            # Raise the session cap so only the global cap can bind (the frozen manifest itself is never edited).
            h.m["budget_per_session"] = dict(h.m["budget_per_session"], max_usd=1.0, max_calls=1000)
            rows = h.run(reps=1)
            self.assertEqual(len(rows), 14)
            spent = sum(r["cost_usd"] for r in rows)
            self.assertLessEqual(h.run_budget.spent_usd, 5.0 + 1e-9)
            self.assertLessEqual(spent, 5.0 + 1e-9)
            self.assertAlmostEqual(spent, h.run_budget.spent_usd, places=4)
            self.assertTrue(h.run_budget.exhausted)
            not_run = [r for r in rows if r["status"] == NOT_RUN_GLOBAL]
            self.assertTrue(not_run)
            sent_after = sum(p.attempts for p in providers)
            self.assertEqual(sent_after, sum(r["calls"] for r in rows))  # no hidden calls beyond those recorded
            persisted = [json.loads(l) for l in (Path(d) / "out.jsonl").read_text().splitlines()]
            self.assertEqual(len(persisted), 14)

    def test_without_global_cap_harness_behaves_as_before(self):
        with tempfile.TemporaryDirectory() as d:
            h = Harness(MANIFEST, lambda: MockProvider([text("ok")]), Path(d) / "o.jsonl", Path(d) / "w")
            self.assertIsNone(h.run_budget)


if __name__ == "__main__":
    unittest.main()
