#!/usr/bin/env python3
"""Read-only ROSS discovery checks and evidence-backed activation trial scoring.

Does not invoke models, alter host settings, or interpret opaque host traces.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import stat
import sys

HOSTS = ("codex", "claude", "gemini")
ID = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
MAX_TRACE = 8 * 1024 * 1024


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_cases(cases):
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a nonempty list")
    ids = set()
    modes = set()
    for c in cases:
        if not isinstance(c, dict) or set(c) != {"id", "prompt", "mode", "should_activate"}:
            raise ValueError("invalid case fields")
        if not isinstance(c["id"], str) or not ID.fullmatch(c["id"]) or c["id"] in ids:
            raise ValueError("invalid or duplicate case id")
        if not isinstance(c["prompt"], str) or not c["prompt"].strip():
            raise ValueError("missing prompt")
        if c["mode"] not in ("explicit", "implicit", "negative") or type(c["should_activate"]) is not bool:
            raise ValueError("invalid mode or expectation")
        if c["should_activate"] != (c["mode"] != "negative"):
            raise ValueError("mode and activation expectation conflict")
        if c["mode"] == "implicit" and re.search(r"\bross\b", c["prompt"], re.I):
            raise ValueError("implicit prompt must not mention ROSS")
        ids.add(c["id"])
        modes.add(c["mode"])
    if modes != {"explicit", "implicit", "negative"}:
        raise ValueError("include explicit, implicit and negative controls")


def plan(cases, host, repeats, seed):
    validate_cases(cases)
    if host not in HOSTS or type(repeats) is not int or not 1 <= repeats <= 50 or type(seed) is not int:
        raise ValueError("invalid host, repeats or seed")
    trials = [
        {"trial_id": f'{c["id"]}--{n}', "case_id": c["id"], "repeat": n}
        for c in cases for n in range(1, repeats + 1)
    ]
    random.Random(seed).shuffle(trials)
    return {"schema": 1, "host": host, "seed": seed, "repeats": repeats,
            "cases_sha256": fingerprint(cases), "trials": trials}


def verify_plan(cases, schedule):
    validate_cases(cases)
    if not isinstance(schedule, dict) or schedule.get("schema") != 1 or schedule.get("host") not in HOSTS:
        raise ValueError("invalid activation plan")
    if schedule.get("cases_sha256") != fingerprint(cases):
        raise ValueError("cases changed after the plan was created")
    repeats = schedule.get("repeats")
    if type(repeats) is not int or not 1 <= repeats <= 50:
        raise ValueError("invalid repeat count")
    expected = {f'{c["id"]}--{n}' for c in cases for n in range(1, repeats + 1)}
    trials = schedule.get("trials")
    if not isinstance(trials, list) or len(trials) != len(expected):
        raise ValueError("incomplete activation plan")
    seen = set()
    for trial in trials:
        if not isinstance(trial, dict) or set(trial) != {"trial_id", "case_id", "repeat"}:
            raise ValueError("invalid trial")
        identifier = trial["trial_id"]
        if type(trial["repeat"]) is not int or identifier != f'{trial["case_id"]}--{trial["repeat"]}' or identifier not in expected or identifier in seen:
            raise ValueError("duplicate or invalid trial")
        seen.add(identifier)
    if seen != expected:
        raise ValueError("missing trial")
    return expected


def trace_digest(root, ref):
    if root is None:
        return None
    if not isinstance(ref, str) or not ref or "\\" in ref or not re.fullmatch(r"[A-Za-z0-9._/@+-]+", ref):
        raise ValueError("unsafe trace reference")
    parts = ref.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("unsafe trace path component")
    base = Path(root)
    if not base.is_dir() or base.is_symlink():
        raise ValueError("trace root must be an existing non-symlink directory")
    path = base
    for index, part in enumerate(parts):
        path = path / part
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or (index < len(parts) - 1 and not stat.S_ISDIR(mode)):
            raise ValueError("trace contains a symlink or invalid directory")
        if index == len(parts) - 1 and not stat.S_ISREG(mode):
            raise ValueError("trace is not a regular file")
    if path.stat().st_size > MAX_TRACE:
        raise ValueError("trace exceeds size limit")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def score(cases, schedule, observations, trace_root=None):
    expected = verify_plan(cases, schedule)
    if not isinstance(observations, list):
        raise ValueError("observations must be an array")
    seen = {}
    hashes = {}
    for record in observations:
        if not isinstance(record, dict) or set(record) != {"trial_id", "outcome", "trace"}:
            raise ValueError("invalid observation")
        identifier = record["trial_id"]
        if not isinstance(identifier, str) or identifier not in expected or identifier in seen:
            raise ValueError("unknown or duplicate observation")
        if record["outcome"] not in ("activated", "not-activated", "unknown"):
            raise ValueError("invalid activation outcome")
        if record["outcome"] != "unknown" and (not isinstance(record["trace"], str) or not record["trace"]):
            raise ValueError("observed outcome requires a trace reference")
        if record["outcome"] == "unknown" and record["trace"] is not None and not isinstance(record["trace"], str):
            raise ValueError("invalid unknown-outcome trace")
        if record["trace"] is not None:
            hashes[identifier] = {
                "path": record["trace"],
                "sha256": trace_digest(trace_root, record["trace"]),
            }
        seen[identifier] = record["outcome"]
    tallies = {}
    for mode in ("explicit", "implicit", "negative"):
        ids = {c["id"] for c in cases if c["mode"] == mode}
        values = [seen[t["trial_id"]] for t in schedule["trials"]
                  if t["case_id"] in ids and t["trial_id"] in seen]
        want = "not-activated" if mode == "negative" else "activated"
        tallies[mode] = {
            "planned": len(ids) * schedule["repeats"],
            "recorded": len(values),
            "correct": values.count(want),
            "misses": sum(v not in (want, "unknown") for v in values),
            "unknown": values.count("unknown"),
        }
    complete = len(seen) == len(expected)
    if not complete:
        status = "incomplete"
    elif any(v == "unknown" for v in seen.values()):
        status = "inconclusive"
    elif trace_root is None:
        status = "evidence-unverified"
    elif any(v["misses"] for v in tallies.values()):
        status = "activation-regression"
    else:
        status = "operator-reported-pass"
    return {
        "schema": 1, "host": schedule["host"], "status": status,
        "complete": complete, "recorded": len(seen), "planned": len(expected),
        "tallies": tallies, "trace_manifest": hashes,
        "evidence_limit": "Only trace file existence and bytes are checked. "
                          "The human-recorded outcome and trace meaning require independent review. "
                          "This report does not prove automatic activation.",
    }


def doctor(host, home, workspace):
    if host not in HOSTS:
        raise ValueError("unsupported host")
    locations = {
        "codex": ((home, ".agents/skills/ross"), (home, ".codex/skills/ross"),
                  (workspace, ".agents/skills/ross")),
        "claude": ((home, ".claude/skills/ross"), (workspace, ".claude/skills/ross")),
        "gemini": ((home, ".gemini/skills/ross"), (home, ".agents/skills/ross"),
                   (workspace, ".gemini/skills/ross"), (workspace, ".agents/skills/ross")),
    }[host]
    output = []
    for base, relative in locations:
        target = Path(base) / relative
        if not target.exists() and not target.is_symlink():
            state = "not-found"
        elif target.is_symlink() or (target / "SKILL.md").is_symlink():
            state = "symlink-needs-review"
        elif not target.is_dir() or not (target / "SKILL.md").is_file():
            state = "invalid-layout"
        else:
            manifest = (target / "SKILL.md").read_text(encoding="utf-8")[:65536]
            lines = manifest.splitlines()
            front = lines[1:lines.index("---", 1)] if len(lines) > 1 and lines[0] == "---" and "---" in lines[1:] else []
            state = ("found-on-disk" if any(x.strip() == "name: ross" for x in front)
                     and any(x.startswith("description: ") and x.partition(": ")[2].strip() for x in front)
                     else "invalid-frontmatter")
        output.append({"location": str(target), "status": state})
    return {"host": host, "paths": output,
            "warning": "Disk discovery is not host activation. Verify with a new host session and native trace."}


def emit(payload, target):
    content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if target:
        with Path(target).open("x", encoding="utf-8") as file:
            file.write(content)
    else:
        sys.stdout.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("doctor")
    p.add_argument("--host", choices=HOSTS, required=True)
    p.add_argument("--home", type=Path, default=Path.home())
    p.add_argument("--workspace", type=Path, default=Path.cwd())
    p = sub.add_parser("plan")
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--host", choices=HOSTS, required=True)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--output", type=Path)
    p = sub.add_parser("score")
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--observations", type=Path, required=True)
    p.add_argument("--trace-root", type=Path)
    p.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            result = doctor(args.host, args.home, args.workspace)
            emit(result, None)
        elif args.command == "plan":
            emit(plan(load(args.cases), args.host, args.repeats, args.seed), args.output)
        else:
            emit(score(load(args.cases), load(args.plan), load(args.observations),
                       args.trace_root), args.output)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc


if __name__ == "__main__":
    main()
