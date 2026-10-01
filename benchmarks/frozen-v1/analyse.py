#!/usr/bin/env python3
"""Economics of a frozen-suite run. Primary KPI: cost and model resources per successful completed task.

  analyse.py results.jsonl [TAG] [COND_A COND_B ...]
A task = one session (simple A, chain B and C, tool D, security E). Failed sessions count in the numerator only.
Only reps present for every listed condition are compared (matched).
"""
import json
import sys
from collections import defaultdict

RES = ("model_calls", "uncached_in", "cache_read", "cache_write", "output", "tokens_total", "cost_usd")
DIAG = ("tool_calls", "file_bytes", "tool_result_bytes", "test_runs", "seconds")


def load(path, tag=None):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    return [r for r in rows if tag in (None, r["tag"])]


def matched(rows, conds):
    have = defaultdict(set)
    for r in rows:
        have[(r["workload"], r["rep"])].add(r["cond"])
    keep = {k for k, v in have.items() if all(c in v for c in conds)}
    return [r for r in rows if (r["workload"], r["rep"]) in keep and r["cond"] in conds]


def summary(rows):
    s = {k: sum(r[k] for r in rows) for k in RES + DIAG}
    s["sessions"], s["passed"] = len(rows), sum(1 for r in rows if r["passed"])
    for k in RES:
        s[k + "_per_success"] = s[k] / s["passed"] if s["passed"] else float("inf")
    return s


def pct(a, b):
    return f"{(b - a) / a * 100:+.1f}%" if a and a != float("inf") else "n/a"


def report(rows, conds, title):
    print(f"\n## {title}")
    S = {c: summary([r for r in rows if r["cond"] == c]) for c in conds}
    print("| metric | " + " | ".join(conds) + " | " + " | ".join(f"{c} vs {conds[0]}" for c in conds[1:]) + " |")
    print("|---" * (1 + 2 * len(conds) - 1) + "|")
    print("| successful / sessions | " + " | ".join(f"{S[c]['passed']}/{S[c]['sessions']}" for c in conds) + " |" + " |" * (len(conds) - 1))
    for k in RES + tuple(k + "_per_success" for k in RES) + DIAG:
        fmt = (lambda v: f"${v:.4f}") if k.startswith("cost") else (lambda v: f"{v:,.0f}" if v != float("inf") else "inf")
        print(f"| {k} | " + " | ".join(fmt(S[c][k]) for c in conds) + " | " + " | ".join(pct(S[conds[0]][k], S[c][k]) for c in conds[1:]) + " |")
    return S


if __name__ == "__main__":
    path = sys.argv[1]
    tag = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
    conds = sys.argv[3:] or ["base", "plugin", "orch"]
    rows = matched(load(path, tag), conds)
    report(rows, conds, "All workloads (matched reps)")
    for w in ("simple", "chain", "tool", "security"):
        sub = [r for r in rows if r["workload"] == w]
        if sub:
            report(sub, conds, f"Workload: {w}")
    sec = [r for r in rows if r["workload"] == "security"]
    if sec:
        print("\n## Security detail")
        for r in sec:
            print(r["cond"], r["rep"], "quality", r["quality_pass"], "security", r["security_pass"], json.dumps(r["security"]))
