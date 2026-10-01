#!/usr/bin/env python3
"""Build 3 matched acceptance: base Claude Code vs same model + ROSS plugin.

Chain: Session A (unfamiliar repo, failing suite with masked bugs, feature) -> process exits ->
Session B prompt exactly "Continue." (next work is in ROADMAP.md). Both run to natural completion.
Quality: visible suite + hidden acceptance tests. Usage is provider-reported (stream-json result).
"""
import concurrent.futures as cf, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import shipq_fixture as F

ROOT = Path(os.environ["ACC_ROOT"]); PLUGIN = Path(os.environ["ROSS_PLUGIN"]); CFG = Path(os.environ["ACC_CFG"])
MODEL = os.environ.get("ACC_MODEL", "claude-sonnet-5-5"); OUT = ROOT / os.environ.get("ACC_OUT", "acceptance3.jsonl")
TEST_RE = re.compile(r"pytest|unittest")
READ_RE = re.compile(r"^\s*(cat|head|tail|sed -n|nl|less|awk)\b")


def sh(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=300)


def make_repo(path):
    for rel, text in F.FILES.items():
        p = path / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
    sh("git init -q && git config user.email t@t && git config user.name t && git add -A && git commit -qm init", path)


def analyse(stdout):
    msgs, uses, results, result = [], {}, {}, {}
    for line in stdout.splitlines():
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if j.get("type") == "assistant":
            m = j["message"]
            if not msgs or msgs[-1]["id"] != m.get("id"):
                msgs.append({"id": m.get("id"), "tools": []})
            for c in m.get("content", []):
                if c.get("type") == "tool_use":
                    msgs[-1]["tools"].append(c["id"]); uses[c["id"]] = c
        elif j.get("type") == "user":
            content = (j.get("message") or {}).get("content")
            for c in content if isinstance(content, list) else []:
                if c.get("type") == "tool_result":
                    results[c["tool_use_id"]] = json.dumps(c.get("content"))
        elif j.get("type") == "result":
            result = j
    s = dict(tool_calls=len(uses), tool_result_bytes=sum(len(v) for v in results.values()), file_bytes=0, full_reads=0,
             partial_reads=0, test_runs=0, first_edit_turn=None, last_test_turn=None, inspect_only_turns=0, model_msgs=len(msgs))
    for i, m in enumerate(msgs, 1):
        kinds = set()
        for tid in m["tools"]:
            u = uses[tid]; name, inp = u["name"], u.get("input", {}); out = results.get(tid, "")
            cmd = inp.get("command", "") if name == "Bash" else ""
            if name in ("Edit", "Write", "MultiEdit") or (cmd and re.search(r"<<|>\s*\S|open\(.*['\"]w|\bsed -i|\.write_text|patch", cmd)):
                kinds.add("edit")
            if name == "Read":
                s["file_bytes"] += len(out)
                s["partial_reads" if (inp.get("offset") or inp.get("limit")) else "full_reads"] += 1
            elif cmd and READ_RE.match(cmd):
                s["file_bytes"] += len(out)
                s["partial_reads" if re.match(r"\s*(sed -n|head|tail)", cmd) else "full_reads"] += 1
            if cmd and TEST_RE.search(cmd):
                s["test_runs"] += 1; kinds.add("test"); s["last_test_turn"] = i
        if "edit" in kinds and s["first_edit_turn"] is None:
            s["first_edit_turn"] = i
        if m["tools"] and not kinds:
            s["inspect_only_turns"] += 1
    return s, result


def claude(prompt, cwd, ross, log):
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID")}
    env.update(CLAUDE_CONFIG_DIR=str(CFG), CLAUDE_CODE_SYNC_SKILLS="0", CLAUDE_CODE_SYNC_PLUGINS="0", CLAUDE_CODE_CCR_EARLY_PLUGINS_SYNC="0")
    args = ["claude", "-p", prompt, "--model", MODEL, "--allowedTools", "Bash Read Glob Grep Write Edit",
            "--output-format", "stream-json", "--verbose", "--max-turns", "80"]
    if ross:
        args += ["--plugin-dir", str(PLUGIN)]
    t0 = time.time()
    p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=2400)
    log.write_text(p.stdout)
    s, result = analyse(p.stdout)
    u = result.get("usage") or {}
    return dict(seconds=round(time.time() - t0, 1), cost_usd=result.get("total_cost_usd") or 0, turns=result.get("num_turns") or 0,
                subtype=result.get("subtype"), uncached_in=u.get("input_tokens", 0), cache_read=u.get("cache_read_input_tokens", 0),
                cache_write=u.get("cache_creation_input_tokens", 0), output=u.get("output_tokens", 0),
                tokens_total=sum(u.get(k, 0) or 0 for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")),
                final=(result.get("result") or "")[-600:], **s)


def grade(repo, only):
    (repo / "hidden_acceptance_test.py").write_text(F.HIDDEN)
    r = sh(f"python3 -m pytest -q -p no:cacheprovider tests hidden_acceptance_test.py -k '{only}' 2>&1 | tail -1", repo)
    (repo / "hidden_acceptance_test.py").unlink()
    return ("failed" not in r.stdout and "error" not in r.stdout.lower() and "passed" in r.stdout), r.stdout.strip()


def chain(cond, rep):
    base = ROOT / "runs" / f"{cond}_{rep}"
    shutil.rmtree(base, ignore_errors=True)
    repo = base / "repo"; repo.mkdir(parents=True); make_repo(repo)
    recs = []
    for sess, prompt, only in (("A", F.TASK_A, "not test_b_"), ("B", F.TASK_B, "")):
        r = claude(prompt, repo, cond == "ross", base / f"{sess}.jsonl")
        ok, tail = grade(repo, only)
        rec = dict(kind="chain", cond=cond, rep=rep, session=sess, passed=ok, test_tail=tail, **r)
        recs.append(rec)
        with open(OUT, "a") as f:
            f.write(json.dumps(rec) + "\n")
    return recs


def short(cond, rep):
    repo = ROOT / "runs" / f"short_{cond}_{rep}"
    shutil.rmtree(repo, ignore_errors=True); repo.mkdir(parents=True); make_repo(repo)
    r = claude(F.SHORT_TASK, repo, cond == "ross", repo.parent / f"short_{cond}_{rep}.jsonl")
    rec = dict(kind="short", cond=cond, rep=rep, session="-", passed=("-" in r["final"] or "minus" in r["final"].lower()),
               test_tail="", ross_state=(repo / ".ross").exists(), **r)
    with open(OUT, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return [rec]


if __name__ == "__main__":
    reps, workers, what = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "chain,short"
    conds = os.environ.get("ACC_CONDS", "baseline,ross").split(",")
    jobs = [(k, c, r) for k in what.split(",") for r in range(reps) for c in conds]
    with cf.ThreadPoolExecutor(workers) as ex:
        for recs in ex.map(lambda j: (chain if j[0] == "chain" else short)(j[1], j[2]), jobs):
            for r in recs:
                print(r["kind"], r["cond"], r["rep"], r["session"], "pass" if r["passed"] else "FAIL", r["tokens_total"],
                      f"${r['cost_usd']:.3f}", r["turns"], "turns", r["subtype"], flush=True)
