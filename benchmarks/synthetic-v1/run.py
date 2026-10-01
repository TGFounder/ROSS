"""ROSS synthetic-v1: ZERO-COST structural economics (no live model, no network, $0).

    python3 benchmarks/synthetic-v1/run.py [--out results/synthetic-v1.json]

Both profiles run through the product orchestration loop (ross.orchestration.loop.Session) with the SAME stateless simulated
model (policies.py). What is measured is exactly what each profile would send to a model: every request is captured at the
provider boundary and broken down by category. Token counts are ESTIMATED with ROSS's own rule (3 characters per token).
Cache figures are CACHE-ELIGIBLE (byte-identical prefix), not measured cache reads. Dollar figures are SYNTHETIC ESTIMATES.
"""
import argparse
import copy
import hashlib
import json
import os
import shutil
import socket
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

# ----------------------------------------------------------------------------------------------- zero network / zero money
for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ROSS_API_KEY"):
    os.environ.pop(k, None)
_connect = socket.socket.connect


def _no_network(self, address):
    if getattr(socket, "AF_UNIX", None) is not None and self.family == socket.AF_UNIX:
        return _connect(self, address)
    raise RuntimeError("synthetic-v1: network is disabled for this experiment")


socket.socket.connect = _no_network
socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("synthetic-v1: network is disabled"))

import ross.providers.anthropic as _anth  # noqa: E402
import ross.providers.openai as _oai  # noqa: E402


def _blocked(*a, **k):
    raise RuntimeError("synthetic-v1: live provider adapters are disabled")


for _mod in (_anth, _oai):
    for _name in dir(_mod):
        _obj = getattr(_mod, _name)
        if isinstance(_obj, type) and _name.endswith("Provider") and _obj.__module__ == _mod.__name__:
            _obj.__init__ = _blocked

import fixtures as F  # noqa: E402
import policies as P  # noqa: E402
from ross.core import pricing  # noqa: E402
from ross.core.budget import Budget, RunBudget  # noqa: E402
from ross.core.models import Usage  # noqa: E402
from ross.eval.harness import make_repo  # noqa: E402
from ross.orchestration import tools as tools_mod  # noqa: E402
from ross.orchestration.loop import Session  # noqa: E402
from ross.orchestration.profile import Profile  # noqa: E402
from ross.orchestration.scheduler import TEST_RE  # noqa: E402
from ross.providers.base import Capabilities, ModelResponse, Provider, estimate_tokens  # noqa: E402

RATES, PRICE_VERSION = pricing.rates("anthropic", "claude-sonnet-5-5")
MIN_CACHEABLE = 512   # the ROSS Anthropic adapter's declared minimum (ross/providers/anthropic.py)
CPT = 3               # characters per token: ROSS's own estimator rule (providers/base.estimate_tokens)
PROFILES = ("base", "ross")   # equal-length directory names keep absolute paths (and byte counts) identical


def tok(chars):
    return chars / CPT


def jlen(s):
    return len(json.dumps(s)) - 2


# ----------------------------------------------------------------------------------------------- instrumentation
FINISH_LOG = []
_orig_finish = tools_mod.Tools._finish


def _finish_spy(self, cmd, out, code, persist, show_exit=True):
    text, err, meta = _orig_finish(self, cmd, out, code, persist, show_exit)
    FINISH_LOG.append(dict(cmd=cmd, raw=len(out), delivered=len(text)))
    return text, err, meta


tools_mod.Tools._finish = _finish_spy   # records only; returns exactly what the product returns


class SimProvider(Provider):
    """The only provider in this experiment. Captures every request exactly as a model would receive it."""

    def __init__(self, policy=None, script=None):
        self.policy, self.script = policy, list(script) if script is not None else None
        self.log, self.responses, self.attempts = [], [], 0

    @property
    def capabilities(self):
        return Capabilities(provider="synthetic", model="claude-sonnet-5-5", context_window=200000, max_output=32000,
                            token_counting="estimate", usage_breakdown=True, prompt_caching="explicit+auto", cache_ttls=("5m", "1h"),
                            min_cacheable_tokens=MIN_CACHEABLE, max_cache_breakpoints=4, pricing_key="anthropic")

    def create(self, request):
        self.attempts += 1
        snap = json.loads(json.dumps({"system": request.system, "tools": request.tools, "messages": request.messages}))
        self.log.append(snap)
        if self.script is not None:
            content = self.script.pop(0) if self.script else [{"type": "text", "text": "(script exhausted)"}]
        else:
            content = self.policy(copy.deepcopy(snap["messages"]))   # messages only: no system prompt, no tools, no profile
        content = json.loads(json.dumps(content))
        self.responses.append(content)
        n = estimate_tokens(request)
        out = len(json.dumps(content)) // CPT
        stop = "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn"
        return ModelResponse(content=content, stop_reason=stop, usage=Usage(uncached_input=n, output=out))


# ----------------------------------------------------------------------------------------------- measurement
CATS = ("system", "tools", "task", "memory_state", "file_context", "tool_output", "other_dynamic", "model_output")


def _is_file_path(p):
    return bool(p) and p not in (".", "./") and "." in p.rsplit("/", 1)[-1]


def breakdown(snap, prompt):
    """Characters of one request by category. Sums exactly to the request's serialized size."""
    c = dict.fromkeys(CATS[:-1], 0)
    sub = {"preflight": 0, "discovery": 0, "prior_model_output": 0, "structure": 0}
    c["system"] = len(snap["system"])
    c["tools"] = len(json.dumps(snap["tools"]))
    msgs = snap["messages"]
    uses, counted = {}, 0
    for i, m in enumerate(msgs):
        for b in m["content"]:
            if b["type"] == "text" and m["role"] == "user" and i == 0:
                t = b["text"]
                rest = t[:len(t) - len(prompt)] if t.endswith(prompt) else ""
                ctx_chars = 0
                for blk in [x for x in rest.split("\n\n") if x]:
                    if blk.startswith("Repository facts"):
                        sub["preflight"] += jlen(blk)
                    else:
                        c["memory_state"] += jlen(blk)
                    ctx_chars += jlen(blk)
                c["task"] += jlen(t) - ctx_chars      # the request itself plus block separators
                counted += jlen(t)
            elif m["role"] == "assistant":
                if b["type"] == "tool_use":
                    uses[b["id"]] = (b["name"], b.get("input") or {})
                sub["prior_model_output"] += len(json.dumps(b))
                counted += len(json.dumps(b))
            elif b.get("type") == "tool_result":
                name, inp = uses.get(b["tool_use_id"], ("?", {}))
                n = jlen(b.get("content") or "")
                if name == "inspect" and _is_file_path(inp.get("path")):
                    c["file_context"] += n
                elif name == "inspect":
                    sub["discovery"] += n
                else:
                    c["tool_output"] += n
                counted += n
    sub["structure"] = len(json.dumps(msgs)) - counted
    c["other_dynamic"] = sum(sub.values())
    return c, sub


def units(snap):
    u = ["S" + snap["system"], "T" + json.dumps(snap["tools"])]
    for m in snap["messages"]:
        for b in m["content"]:
            u.append(m["role"] + json.dumps(b, sort_keys=True))
    return u


def cache_sim(snaps):
    """Ideal byte-identical-prefix model over one chain of requests (one profile, one scenario, all its sessions)."""
    U = [units(s) for s in snaps]
    L = [[len(x) for x in u] for u in U]

    def cp(a, b):
        n = 0
        for x, y in zip(U[a], U[b]):
            if x != y:
                break
            n += 1
        return n

    out = []
    for j in range(len(U)):
        best = max((cp(i, j) for i in range(j)), default=0)
        chars = sum(L[j][:best])
        if tok(chars) < MIN_CACHEABLE:
            best, chars = 0, 0
        later = max((cp(j, k) for k in range(j + 1, len(U))), default=0)
        wchars = sum(L[j][best:later]) if later > best and tok(sum(L[j][:later])) >= MIN_CACHEABLE else 0
        out.append(dict(eligible_chars=chars, write_chars=wchars, prefix_units=best))
    return out


def measure(sessions):
    """sessions: list of dicts with snaps, responses, prompt, result, finish (tool-finish records)."""
    snaps = [s for x in sessions for s in x["snaps"]]
    cache = cache_sim(snaps)
    tot = dict.fromkeys(CATS, 0.0)
    sub_tot = {"preflight": 0, "discovery": 0, "prior_model_output": 0, "structure": 0}
    input_chars = out_chars = elig = wr = 0
    k = 0
    m = dict(calls=0, tool_calls=0, file_reads=0, repeated_reads=0, test_executions=0, tests_reused=0, state_items_reused=0,
             raw_tool_bytes=0, model_bound_tool_bytes=0, raw_kept_local_bytes=0, retries_prevented=0)
    for x in sessions:
        seen = set()
        for snap, resp in zip(x["snaps"], x["responses"]):
            c, sub = breakdown(snap, x["prompt"])
            for kk, v in c.items():
                tot[kk] += v
            for kk, v in sub.items():
                sub_tot[kk] += v
            ichars = sum(c.values())
            input_chars += ichars
            oc = len(json.dumps(resp))
            out_chars += oc
            elig += cache[k]["eligible_chars"]
            wr += cache[k]["write_chars"]
            k += 1
            for b in resp:
                if b["type"] == "tool_use" and b["name"] == "inspect" and _is_file_path((b.get("input") or {}).get("path")):
                    key = json.dumps(b["input"], sort_keys=True)
                    m["file_reads"] += 1
                    m["repeated_reads"] += key in seen
                    seen.add(key)
        m["calls"] += len(x["snaps"])
        m["tool_calls"] += x["result"].tool_calls
        last = x["final_messages"]
        for msg in last:
            if msg["role"] == "user" and isinstance(msg["content"], list):
                for b in msg["content"]:
                    if b.get("type") == "tool_result":
                        m["model_bound_tool_bytes"] += len(b.get("content") or "")
                        if "already passed on identical files" in (b.get("content") or ""):
                            m["tests_reused"] += 1
        uses = [b for msg in last if msg["role"] == "assistant" for b in msg["content"] if b["type"] == "tool_use"]
        res = {b["tool_use_id"]: b.get("content") or "" for msg in last if msg["role"] == "user" and isinstance(msg["content"], list)
               for b in msg["content"] if b.get("type") == "tool_result"}
        for u in uses:
            if u["name"] == "run" and TEST_RE.search(u["input"].get("command", "")) and "already passed on identical files" not in res.get(u["id"], ""):
                if not res.get(u["id"], "").startswith("ROSS policy"):
                    m["test_executions"] += 1
        first = x["snaps"][0]["messages"][0]["content"][0]["text"] if x["snaps"] else ""
        if "ROSS state" in first:
            m["state_items_reused"] += sum(1 for l in first.split("ROSS state", 1)[1].splitlines()[1:] if ":" in l)
        for f in x["finish"]:
            m["raw_tool_bytes"] += f["raw"]
            if f["raw"] > f["delivered"]:
                m["raw_kept_local_bytes"] += f["raw"] - f["delivered"]
    tot["model_output"] = out_chars
    in_tok, out_tok, el_tok, wr_tok = tok(input_chars), tok(out_chars), tok(elig), tok(wr)
    nocache = (in_tok * RATES["input"] + out_tok * RATES["output"]) / 1e6
    cached = (el_tok * RATES["cache_read"] + wr_tok * RATES["cache_write_5m"] + (in_tok - el_tok - wr_tok) * RATES["input"]
              + out_tok * RATES["output"]) / 1e6
    tokens = {kk: round(tok(v)) for kk, v in tot.items()}
    tokens["other_dynamic_detail"] = {kk: round(tok(v)) for kk, v in sub_tot.items()}
    return dict(**m, input_tokens=round(in_tok), output_tokens=round(out_tok), total_tokens=round(in_tok + out_tok),
                cache_eligible_tokens=round(el_tok), cache_write_tokens=round(wr_tok), tokens_by_category=tokens,
                synthetic_cost_no_cache=round(nocache, 6), synthetic_cost_cache_eligible=round(cached, 6))


# ----------------------------------------------------------------------------------------------- running
def new_repo(base, files):
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True)
    make_repo(base, files)
    return base


def session(root, profile_name, prompt, provider, budget=None, run_budget=None):
    profile = Profile.baseline() if profile_name == "base" else Profile.ross()
    FINISH_LOG.clear()
    s = Session(root, provider, profile, budget or Budget(max_usd=1.0, max_calls=40), prompt, keep_messages=True, run_budget=run_budget)
    t0 = time.time()
    r = s.run()
    return dict(prompt=prompt, result=r, snaps=list(provider.log), responses=list(provider.responses), finish=list(FINISH_LOG),
                final_messages=r.messages, seconds=round(time.time() - t0, 2), status=r.status, answer=r.final_text,
                denied=r.denied, attempts=provider.attempts)


def requests_text(sessions):
    return json.dumps([x["snaps"] for x in sessions])


def summarize(prof, sessions, ok, detail, extra=None):
    d = measure(sessions)
    d.update(profile=prof, success=ok, check=detail, statuses=[x["status"] for x in sessions],
             elapsed_s=round(sum(x["seconds"] for x in sessions), 2), **(extra or {}))
    return d


SINGLE = {  # scenario -> (files, prompt, policy, check)
    "1_simple": (F.SIMPLE_FILES, F.SIMPLE_PROMPT, P.simple, F.check_simple),
    "2_first_session": (F.SHOP_FILES, F.SHOP_PROMPT, P.shop, F.check_shop),
    "4_large_tool_output": (F.LD_FILES, F.LD_PROMPT, P.ledgerd, F.check_ledgerd),
    "5_large_file": (F.CORE_FILES, F.CORE_PROMPT, P.core, F.check_core),
    "6_security": (F.SEC_FILES, F.SEC_PROMPT, P.security, None),
    "9_tgos_like": (F.TG_FILES, F.TG_PROMPT, P.tg, F.check_tg),
}


def run_single(work, name, prof, script=None):
    files, prompt, pol, check = SINGLE[name]
    root = new_repo(work / name / prof, files)
    prov = SimProvider(policy=pol, script=script)
    s = session(root, prof, prompt, prov)
    if name == "6_security":
        ok, detail = F.check_security(str(root), s["answer"], requests_text([s]))
        extra = dict(denied=s["denied"])
    else:
        ok, detail = check(str(root), s["answer"])
        extra = {}
    if name == "4_large_tool_output":
        first = next((b.get("content") or "" for msg in s["final_messages"] if msg["role"] == "user" and isinstance(msg["content"], list)
                      for b in msg["content"] if b.get("type") == "tool_result"), "")
        raw = s["finish"][0]["raw"] if s["finish"] else 0
        crit = {k: bool(__import__("re").search(v, first)) for k, v in F.LD_CRITICAL.items()}
        extra.update(first_run_raw_bytes=raw, first_run_model_bound_bytes=len(first), critical_in_first_delivery=crit,
                     strict_success=ok and all(crit.values()),
                     recovery_tool_calls=sum(1 for r in s["responses"][1:] for b in r if b["type"] == "tool_use"))
    if name == "5_large_file":
        extra["whole_file_read_chars"] = whole_read(root, prof)
    return [s], ok, detail, extra


def whole_read(root, prof):
    """Tool-level side measurement (no model): what a whole-file read of ledger/core.py would put in context."""
    prov = SimProvider(policy=P.simple)
    s = Session(root, prov, Profile.baseline() if prof == "base" else Profile.ross(), Budget(max_usd=1.0), F.CORE_PROMPT)
    return len(s.tools.execute("inspect", {"path": "ledger/core.py"})[0])


def run_resume(work, prof, scripts=None):
    root = new_repo(work / "3_resume" / prof, F.MONEY_FILES)
    a = session(root, prof, F.MONEY_PROMPT_A, SimProvider(policy=P.money, script=scripts[0] if scripts else None))
    ok_a, det_a = F.check_money_a(str(root), a["answer"])
    b = session(root, prof, F.MONEY_PROMPT_B, SimProvider(policy=P.money, script=scripts[1] if scripts else None))
    ok_b, det_b = F.check_money_b(str(root), b["answer"])
    return [a, b], ok_a, det_a, ok_b, det_b


def run_stale(work):
    """G: ROSS-only memory validity. Positive control (unchanged files: reuse allowed) and stale case (file changed)."""
    out = {}
    for case in ("control_unchanged", "stale_changed"):
        root = new_repo(work / "7_stale" / case, F.CALC_FILES)
        a = session(root, "ross", F.CALC_PROMPT, SimProvider(policy=P.calc))
        if case == "stale_changed":
            (root / "calc.py").write_text(F.CALC_BROKEN)
        cont = session(root, "ross", "Continue.", SimProvider(policy=P.calc))
        again = session(root, "ross", F.CALC_PROMPT, SimProvider(policy=P.calc))
        truth = F.sh(str(root), F.UNITTEST)[0] == 0
        first = cont["snaps"][0]["messages"][0]["content"][0]["text"]
        reused = any("already passed on identical files" in (b.get("content") or "") for msg in again["final_messages"]
                     if msg["role"] == "user" and isinstance(msg["content"], list) for b in msg["content"] if b.get("type") == "tool_result")
        out[case] = dict(session_a=a["answer"], suite_really_passes=truth, continue_state_block=first,
                         continue_answer=cont["answer"], continue_correct=("passes" in cont["answer"].lower() and "fails" not in cont["answer"].lower()) == truth,
                         rerun_answer=again["answer"], rerun_reused_stored_result=reused,
                         rerun_correct=("FAILS" not in again["answer"]) == truth,
                         state_marked_stale="Stale, rerun" in first, state_marked_valid="Verified, still valid" in first)
    s = out["stale_changed"]
    out["invalidated"] = (s["state_marked_stale"] and not s["state_marked_valid"] and not s["rerun_reused_stored_result"]
                          and s["continue_correct"] and s["rerun_correct"])
    c = out["control_unchanged"]
    out["control_reuse_works"] = c["rerun_reused_stored_result"] and c["rerun_correct"]
    return out


def run_budget(work):
    """H: a shared run-wide cap that admits about one worst-case request; BASE runs first, then ROSS."""
    probe_root = new_repo(work / "8_budget" / "probe", F.SHOP_FILES)
    probe = Session(probe_root, SimProvider(policy=P.shop), Profile.baseline(), Budget(), F.SHOP_PROMPT)
    req = probe._request([{"role": "user", "content": [{"type": "text", "text": F.SHOP_PROMPT}]}], 8192)
    worst = probe.governor.worst_case(estimate_tokens(req), 8192)
    rb = RunBudget(worst * 1.5)
    out = {"global_cap_usd": round(rb.max_usd, 6), "worst_case_per_request_usd": round(worst, 6)}
    for prof in PROFILES:
        root = new_repo(work / "8_budget" / prof, F.SHOP_FILES)
        prov = SimProvider(policy=P.shop)
        s = session(root, prof, F.SHOP_PROMPT, prov, run_budget=rb)
        out[prof] = dict(status=s["status"], completed_calls=s["result"].calls, provider_attempts=prov.attempts,
                         detail=s["result"].detail[:160])
    out["spent_usd"] = round(rb.spent_usd, 6)
    out["cap_respected"] = rb.spent_usd <= rb.max_usd + 1e-12
    # every provider attempt must have been admitted and completed; once the run cap refused, later sessions make none
    after = sum(out[p]["provider_attempts"] - out[p]["completed_calls"] for p in PROFILES)
    if out["base"]["status"] == "budget":
        after += out["ross"]["provider_attempts"]
    out["attempts_after_refusal"] = after
    tiny = new_repo(work / "8_budget" / "session_cap", F.SHOP_FILES)
    prov = SimProvider(policy=P.shop)
    s = session(tiny, "ross", F.SHOP_PROMPT, prov, budget=Budget(max_usd=0.0001))
    out["session_cap_refusal"] = dict(status=s["status"], provider_attempts=prov.attempts)
    return out


def delta(b, r):
    return None if not b else round(100.0 * (r - b) / b, 1)


AGG_KEYS = ("calls", "input_tokens", "output_tokens", "total_tokens", "tool_calls", "file_reads", "repeated_reads", "test_executions",
            "model_bound_tool_bytes", "synthetic_cost_no_cache", "synthetic_cost_cache_eligible")


def aggregate(rows):
    agg = {}
    for p in PROFILES:
        a = {k: sum(r[p][k] for r in rows) for k in AGG_KEYS}
        a["tool_output_tokens"] = sum(r[p]["tokens_by_category"]["tool_output"] for r in rows)
        a["file_context_tokens"] = sum(r[p]["tokens_by_category"]["file_context"] for r in rows)
        agg[p] = a
    agg["delta_pct"] = {k: delta(agg["base"][k], agg["ross"][k]) for k in agg["base"]}
    return agg


def file_digest():
    return {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest()[:16] for n in ("fixtures.py", "policies.py", "run.py")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "results" / "synthetic-v1.json"))
    ap.add_argument("--work", default=os.path.join(os.environ.get("TMPDIR", "/tmp"), "ross-synthetic-v1"))
    a = ap.parse_args(argv)
    work = Path(a.work)
    shutil.rmtree(work, ignore_errors=True)

    gate = {}
    try:
        _anth.AnthropicProvider("claude-sonnet-5-5")
        gate["anthropic_adapter_blocked"] = False
    except RuntimeError:
        gate["anthropic_adapter_blocked"] = True
    try:
        socket.create_connection(("api.anthropic.com", 443), timeout=2)
        gate["network_blocked"] = False
    except RuntimeError:
        gate["network_blocked"] = True
    gate["api_keys_in_env"] = [k for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY") if os.environ.get(k)]
    if not (gate["anthropic_adapter_blocked"] and gate["network_blocked"]) or gate["api_keys_in_env"]:
        raise SystemExit(f"zero-cost gate failed: {gate}")

    res = {"experiment": "synthetic-v1", "kind": "SYNTHETIC STRUCTURAL ECONOMICS TEST (not a provider cost benchmark)",
           "provider_spend_usd": 0.0, "live_provider_calls": 0, "token_counting": "ESTIMATED: characters / 3 (ROSS estimator rule)",
           "price_snapshot": PRICE_VERSION, "rates_per_mtok": RATES, "min_cacheable_tokens": MIN_CACHEABLE, "zero_cost_gate": gate,
           "benchmark_files_sha256_16": file_digest()}

    # ---------------- Test B: orchestration economics (adaptive, evidence-driven simulated model) ----------------
    tb, base_scripts = {}, {}
    for name in SINGLE:
        tb[name] = {}
        for prof in PROFILES:
            sess, ok, det, extra = run_single(work / "B", name, prof)
            tb[name][prof] = summarize(prof, sess, ok, det, extra)
            tb[name][prof]["answer"] = sess[0]["answer"][:600]
            if prof == "base":
                base_scripts[name] = [sess[0]["responses"]]
    tb["3_resume"] = {}
    for prof in PROFILES:
        sess, ok_a, det_a, ok_b, det_b = run_resume(work / "B", prof)
        row = summarize(prof, sess, ok_a and ok_b, f"A: {det_a} | B: {det_b}")
        row["session_b_only"] = summarize(prof, sess[1:], ok_b, det_b)
        row["session_b_first_message"] = sess[1]["snaps"][0]["messages"][0]["content"][0]["text"][:1800]
        tb["3_resume"][prof] = row
        if prof == "base":
            base_scripts["3_resume"] = [sess[0]["responses"], sess[1]["responses"]]
    res["test_b_orchestration"] = tb
    res["stale_memory"] = run_stale(work / "B")
    res["budget"] = run_budget(work / "B")

    # ---------------- Test A: fixed-work context economics (BASE's exact response trace replayed to both) ----------------
    ta = {}
    for name in ("2_first_session", "4_large_tool_output", "5_large_file", "9_tgos_like"):
        ta[name] = {}
        for prof in PROFILES:
            sess, ok, det, extra = run_single(work / "A", name, prof, script=base_scripts[name][0])
            row = summarize(prof, sess, ok, det)
            row["script_steps_unused"] = len(base_scripts[name][0]) - len(sess[0]["snaps"])
            ta[name][prof] = row
    ta["3_resume"] = {}
    for prof in PROFILES:
        sess, ok_a, det_a, ok_b, det_b = run_resume(work / "A", prof, scripts=base_scripts["3_resume"])
        ta["3_resume"][prof] = summarize(prof, sess, ok_a and ok_b, f"A: {det_a} | B: {det_b}")
    res["test_a_fixed_work"] = ta

    # ---------------- aggregates: equivalent successful work only ----------------
    def eligible(table):
        return [v for k, v in table.items() if all(v[p]["success"] for p in PROFILES)]
    res["aggregate_test_b"] = dict(scenarios=[k for k, v in tb.items() if all(v[p]["success"] for p in PROFILES)], **aggregate(eligible(tb)))
    res["aggregate_test_a"] = dict(scenarios=list(ta), **aggregate(list(ta.values())))
    s = tb["1_simple"]
    res["simple_overhead_pct"] = delta(s["base"]["total_tokens"], s["ross"]["total_tokens"])
    res["benchmark_files_sha256_16_after"] = file_digest()

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: res[k] for k in ("aggregate_test_b", "aggregate_test_a", "simple_overhead_pct")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
