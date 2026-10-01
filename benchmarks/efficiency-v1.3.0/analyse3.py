import json, sys, statistics as stt
rows=[json.loads(l) for l in open(sys.argv[1])]
K=["model_msgs","turns","uncached_in","cache_read","cache_write","output","tokens_total","cost_usd","tool_calls","tool_result_bytes","file_bytes","full_reads","partial_reads","test_runs","seconds"]
def agg(rs): return {k: round(sum(r[k] for r in rs),4) for k in K}
def pct(a,b): return f"{(b-a)/a*100:+.1f}%" if a else "n/a"
out={}
for scope in ("AB","A","B"):
    print(f"\n=== scope {scope}")
    res={}
    for c in ("baseline","ross"):
        rs=[r for r in rows if r["kind"]=="chain" and r["cond"]==c and r["session"] in scope]
        res[c]=agg(rs); res[c]["sessions_passed"]=f"{sum(r['passed'] for r in rs)}/{len(rs)}"
    for k in ["sessions_passed"]+K:
        a,b=res["baseline"][k],res["ross"][k]
        print(f"{k:18} {a!s:>12} {b!s:>12} {pct(a,b) if not isinstance(a,str) else ''}")
    out[scope]=res
# chain success and per-successful-task
for c in ("baseline","ross"):
    ch=[(r["rep"],r) for r in rows if r["kind"]=="chain" and r["cond"]==c]
    reps=sorted({rep for rep,_ in ch})
    ok=[rep for rep in reps if all(r["passed"] for rr,r in ch if rr==rep)]
    tok=sum(r["tokens_total"] for _,r in ch); cost=sum(r["cost_usd"] for _,r in ch)
    sess_ok=sum(r["passed"] for _,r in ch)
    print(f"{c}: chains fully passed {len(ok)}/{len(reps)}; sessions passed {sess_ok}/{len(ch)}; tokens/successful chain {tok/max(1,len(ok)):,.0f}; cost/successful chain ${cost/max(1,len(ok)):.4f}; tokens/successful session {tok/max(1,sess_ok):,.0f}; cost/successful session ${cost/max(1,sess_ok):.4f}")
sh=[r for r in rows if r["kind"]=="short"]
for c in ("baseline","ross"):
    rs=[r for r in sh if r["cond"]==c]
    print(f"short {c}: tokens {[r['tokens_total'] for r in rs]} cost {[r['cost_usd'] for r in rs]} calls {[r['model_msgs'] for r in rs]} state_created {[r.get('ross_state') for r in rs]} pass {[r['passed'] for r in rs]}")
