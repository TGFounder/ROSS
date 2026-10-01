#!/usr/bin/env python3
"""ROSS Efficiency Runtime: local-first operational state for AI agent work.

Perpetual state, not perpetual transcript. Standard library only. Nothing here
opens a network connection. State lives in <project>/.ross/ (git-ignored).

Commands:
  status                 compact view of durable state and local counters
  context [--budget N]   minimum context for the next decision (~N tokens)
  note KIND TEXT         record one semantic delta (goal, next, decision,
                         constraint, preserve, blocker, fact, done)
  note --remove KIND TEXT
  checkpoint [--next T]  record a resume point (git state is derived)
  savings [--all]        local efficiency meter (measured vs estimated)
  forget [KIND [TEXT]] | --project | --everything
  doctor                 environment and permission checks
  hook EVENT             host hook adapter (JSON on stdin, JSON on stdout)
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

VERSION = "1.1.0-candidate"
KINDS = ("goal", "next", "decision", "constraint", "preserve", "blocker", "fact", "done")
SINGLE = ("goal", "next")
TEST_RE = re.compile(r"(^|[\s;&|(])(pytest|py\.test|python3? -m (pytest|unittest)|npm (run )?test|pnpm (run )?test|yarn test|"
                     r"npx (jest|vitest)|jest|vitest|go test|cargo test|mvn test|gradle test|\./gradlew test|make test|"
                     r"dotnet test|rspec|phpunit|tox)\b")
RERUN_MARK = "ross:rerun"
SECRET_RES = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(sk|rk|pk)[-_](live|test|proj|ant)?[-_]?[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
]
KEYVAL_RE = re.compile(r"(?i)\b((?:api[_-]?key|secret|token|passwd|password|pwd|auth)\w*\s*[:=]\s*)[\"']?[^\s\"',;]{6,}")
MAX_HASH_FILES = 4000
MAX_HASH_BYTES = 64 * 1024 * 1024


# ------------------------------------------------------------------ storage
def project_root(start=None):
    start = Path(start or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
    try:
        out = subprocess.run(["git", "-C", str(start), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return start


def redact(text):
    if not isinstance(text, str):
        return text
    for rx in SECRET_RES:
        text = rx.sub("[REDACTED]", text)
    return KEYVAL_RE.sub(lambda m: m.group(1) + "[REDACTED]", text)


class Store:
    def __init__(self, root=None):
        self.root = project_root(root)
        self.dir = self.root / ".ross"

    def ensure(self):
        if not self.dir.exists():
            self.dir.mkdir(mode=0o700, parents=True)
            (self.dir / ".gitignore").write_text("*\n")
        return self

    def path(self, name):
        return self.dir / name

    def load(self, name, default):
        p = self.path(name)
        try:
            return json.loads(p.read_text())
        except (OSError, ValueError):
            return default

    def save(self, name, data):
        self.ensure()
        p = self.path(name)
        tmp = p.with_suffix(p.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        os.replace(tmp, p)

    def append(self, name, record):
        self.ensure()
        fd = os.open(self.path(name), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

    def lines(self, name):
        try:
            return [json.loads(l) for l in self.path(name).read_text().splitlines() if l.strip()]
        except (OSError, ValueError):
            return []


# ------------------------------------------------------------------ derived state
def git(root, *args):
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def git_state(root):
    sha = git(root, "rev-parse", "--short", "HEAD")
    if not sha:
        return {}
    dirty = [l[3:] for l in git(root, "status", "--porcelain").splitlines() if l and not l[3:].startswith(".ross")]
    return {"branch": git(root, "rev-parse", "--abbrev-ref", "HEAD"), "sha": sha, "dirty": dirty}


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def inputs_hash(root):
    """Hash of every tracked and untracked (non-ignored) file: the state a command observed."""
    files = git(root, "ls-files", "-co", "--exclude-standard").splitlines()
    if not files:
        files = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]
    h, total = hashlib.sha256(), 0
    for rel in sorted(files)[:MAX_HASH_FILES]:
        if rel.startswith(".ross/") or "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        p = root / rel
        try:
            st = p.stat()
        except OSError:
            continue
        total += st.st_size
        if total > MAX_HASH_BYTES:
            return None  # too large to fingerprint cheaply; never reuse results
        h.update(rel.encode() + b"\0" + file_hash(p).encode())
    return h.hexdigest()[:16]


def norm_cmd(cmd):
    if isinstance(cmd, list):
        cmd = " ".join(map(str, cmd))
    return re.sub(r"\s+", " ", str(cmd or "")).strip()


# ------------------------------------------------------------------ semantic state (deltas)
def state(store):
    return store.load("state.json", {})


def note(store, kind, text, remove=False, source="model"):
    if kind not in KINDS:
        raise SystemExit(f"unknown kind {kind}; use one of {', '.join(KINDS)}")
    text = redact(text.strip())
    st = state(store)
    before = json.dumps(st, sort_keys=True)
    if kind in SINGLE:
        st[kind] = None if remove else text
    else:
        items = [i for i in st.get(kind, []) if i != text]
        if not remove:
            items.append(text)
        st[kind] = items[-25:]
    if kind == "done" and not remove and st.get("next") == text:
        st["next"] = None
    if json.dumps(st, sort_keys=True) == before:
        return False  # no durable change: write nothing
    st["updated"] = int(time.time())
    store.save("state.json", st)
    store.append("deltas.jsonl", {"ts": st["updated"], "op": "-" if remove else "+", "kind": kind, "text": text, "source": source})
    return True


def checkpoint(store, next_action=None, source="model"):
    if next_action:
        note(store, "next", next_action, source=source)
    g = git_state(store.root)
    last = (store.lines("checkpoints.jsonl") or [{}])[-1]
    cur = {"sha": g.get("sha"), "dirty": sorted(g.get("dirty", [])), "next": state(store).get("next")}
    if all(last.get(k) == v for k, v in cur.items()):
        return False
    cur.update(ts=int(time.time()), branch=g.get("branch"), source=source)
    store.append("checkpoints.jsonl", cur)
    return True


def verified_tests(store, cur_hash):
    out = []
    for cmd, rec in store.load("commands.json", {}).items():
        if rec.get("result") == "pass" and cur_hash and rec.get("inputs") == cur_hash:
            out.append(cmd)
    return out


def context(store, budget=600):
    st = state(store)
    g = git_state(store.root)
    if not st and not store.path("commands.json").exists():
        return ""
    lines = [f"ROSS state for {store.root.name} (from .ross; derived git state is live):"]
    if g:
        d = g["dirty"]
        lines.append(f"Git: {g['branch']} @ {g['sha']}" + (f"; uncommitted: {', '.join(d[:8])}" + (" ..." if len(d) > 8 else "") if d else "; clean"))
    for kind, label in (("goal", "Goal"), ("next", "Next")):
        if st.get(kind):
            lines.append(f"{label}: {st[kind]}")
    for kind, label in (("blocker", "Blockers"), ("constraint", "Constraints"), ("preserve", "Do not touch"),
                        ("decision", "Decisions"), ("fact", "Verified facts"), ("done", "Done")):
        items = st.get(kind) or []
        if items:
            lines.append(f"{label}: " + "; ".join(reversed(items[-6:])))
    h = inputs_hash(store.root)
    vt = verified_tests(store, h)
    if vt:
        lines.append("Still valid (inputs unchanged since pass): " + "; ".join(vt[:5]))
    fails = [f"`{v['cmd'][:60]}` x{v['count']}" for v in store.load("failures.json", {}).values() if v.get("count", 0) >= 2 and v.get("inputs") == h]
    if fails:
        lines.append("Repeated failures at current inputs (change strategy first): " + "; ".join(fails[:3]))
    lines.append("Trust this state; read files only when the next decision needs them.")
    text, limit = "", budget * 4
    for l in lines:
        if len(text) + len(l) + 1 > limit:
            break
        text += l + "\n"
    return text.strip()


# ------------------------------------------------------------------ metrics
def metric(store, kind, value=1, estimated=False, session=None, detail=None):
    store.append("metrics.jsonl", {"ts": int(time.time()), "kind": kind, "value": value,
                                   "estimated": bool(estimated), "session": session, "detail": redact(detail)})


def transcript_usage(path):
    """Provider-reported usage from a Claude Code transcript (measured)."""
    tot = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "messages": 0}
    seen = set()
    try:
        with open(path) as f:
            for line in f:
                try:
                    j = json.loads(line)
                except ValueError:
                    continue
                msg = j.get("message") or {}
                u = msg.get("usage")
                mid = msg.get("id")
                if not u or mid in seen:
                    continue
                seen.add(mid)
                tot["input"] += u.get("input_tokens", 0) or 0
                tot["output"] += u.get("output_tokens", 0) or 0
                tot["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
                tot["cache_write"] += u.get("cache_creation_input_tokens", 0) or 0
                tot["messages"] += 1
    except OSError:
        return None
    return tot


def savings(store, show_all=False):
    m = store.lines("metrics.jsonl")
    sessions = store.load("sessions.json", {})
    agg = {}
    for r in m:
        a = agg.setdefault(r["kind"], [0, r.get("estimated")])
        a[0] += r.get("value") or 0
    lines = ["ROSS savings (local only; nothing leaves this machine)"]
    meas = {k: sum(s.get(k, 0) for s in sessions.values()) for k in ("input", "output", "cache_read", "cache_write")}
    if sessions:
        lines.append(f"Measured provider tokens over {len(sessions)} session(s): input {meas['input']:,}, output {meas['output']:,}, "
                     f"cache read {meas['cache_read']:,}, cache write {meas['cache_write']:,}  [MEASURED]")
    labels = [("dup_read_avoided", "Duplicate file reads prevented", False), ("read_tokens_avoided", "Context avoided by those reads", True),
              ("test_reused", "Test runs reused (inputs unchanged)", False), ("retry_prevented", "Identical failing retries prevented", False),
              ("context_hydrated", "Sessions resumed from compact state", False), ("hydrated_tokens", "Compact state injected", True)]
    for kind, label, est in labels:
        if kind in agg:
            unit = " tokens" if "tokens" in kind else ""
            lines.append(f"{label}: {agg[kind][0]:,}{unit}  [{'ESTIMATED, bytes/4' if est else 'COUNTED'}]")
    if len(lines) == 1:
        lines.append("No activity recorded yet.")
    return "\n".join(lines)


# ------------------------------------------------------------------ hooks
def out(obj):
    sys.stdout.write(json.dumps(obj))


def deny(event, reason):
    out({"hookSpecificOutput": {"hookEventName": event, "permissionDecision": "deny", "permissionDecisionReason": reason}})


def tool_failed(payload):
    if payload.get("hook_event_name") == "PostToolUseFailure" or payload.get("success") is False:
        return True
    resp = payload.get("tool_response")
    if isinstance(resp, dict):
        for k in ("exit_code", "exitCode", "returncode", "return_code"):
            if isinstance(resp.get(k), int):
                return resp[k] != 0
        if resp.get("interrupted") or resp.get("is_error"):
            return True
        text = (resp.get("stdout") or "") + (resp.get("stderr") or "")
    else:
        text = str(resp or "")
    return bool(re.search(r"(\b\d+ failed\b|\bFAILED\b|\bERRORS?\b|Traceback \(most recent|exit code [1-9]|npm ERR!|\bFAIL\b)", text))


def error_sig(payload):
    resp = payload.get("tool_response") or payload.get("error") or ""
    text = json.dumps(resp) if not isinstance(resp, str) else resp
    lines = [l for l in re.split(r"\\n|\n", text) if re.search(r"(Error|FAIL|failed|assert|Exception)", l)]
    sig = re.sub(r"0x[0-9a-f]+|\d+\.\d+s|\b\d{2,}\b", "#", " | ".join(lines[-3:]))[:240]
    return redact(sig) or "nonzero exit"


def command_of(payload):
    ti = payload.get("tool_input") or {}
    return norm_cmd(ti.get("command") or ti.get("cmd") or ti.get("argv") or "")


def hook(event, payload):
    store = Store(payload.get("cwd"))
    session = payload.get("session_id")
    tool = payload.get("tool_name") or ""
    if event == "SessionStart":
        ctx = context(store)
        if ctx:
            metric(store, "context_hydrated", 1, session=session)
            metric(store, "hydrated_tokens", len(ctx) // 4, estimated=True, session=session)
            out({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}})
        return
    if event == "PreToolUse":
        if tool == "Read":
            ti = payload.get("tool_input") or {}
            fp = ti.get("file_path")
            if not fp or not os.path.isfile(fp):
                return
            key = f"{os.path.realpath(fp)}|{ti.get('offset')}|{ti.get('limit')}"
            rec = store.load("reads.json", {}).get(key)
            if rec and rec.get("session") == session and rec.get("hash") == file_hash(fp):
                size = os.path.getsize(fp)
                metric(store, "dup_read_avoided", 1, session=session, detail=fp)
                metric(store, "read_tokens_avoided", size // 4, estimated=True, session=session)
                deny("PreToolUse", f"ROSS: {os.path.basename(fp)} is unchanged since you read it earlier in this session "
                                   f"(sha256 {rec['hash'][:10]}). Use the content already in context. If you truly need it again, "
                                   f"read a specific offset/limit range.")
            return
        cmd = command_of(payload)
        if not cmd or RERUN_MARK in cmd or os.environ.get("ROSS_FORCE"):
            return
        fails = store.load("failures.json", {})
        cmds = store.load("commands.json", {})
        is_test = bool(TEST_RE.search(cmd))
        if cmd not in fails and not (is_test and cmd in cmds):
            return
        h = inputs_hash(store.root)
        f = fails.get(cmd)
        if h and f and f.get("inputs") == h and f.get("count", 0) >= 2:
            metric(store, "retry_prevented", 1, session=session, detail=cmd[:120])
            deny("PreToolUse", f"ROSS: `{cmd[:120]}` has already failed {f['count']} times with identical inputs and the same error "
                               f"({f.get('sig', '')[:160]}). A third identical attempt adds no information. Change the diagnosis or the "
                               f"inputs first. Append '# {RERUN_MARK}' only if the user explicitly asked for another attempt or something "
                               f"outside the project files changed.")
            return
        c = cmds.get(cmd)
        if is_test and h and c and c.get("result") == "pass" and c.get("inputs") == h:
            metric(store, "test_reused", 1, session=session, detail=cmd[:120])
            deny("PreToolUse", f"ROSS: `{cmd[:120]}` already PASSED against identical inputs (fingerprint {h[:10]}, "
                               f"{time.strftime('%H:%M', time.localtime(c['ts']))}). Rerunning has no information value; treat it as "
                               f"passing. Append '# {RERUN_MARK}' only if the user explicitly asked for a fresh run or something outside the "
                               f"project files changed (environment, services, time-dependent data).")
        return
    if event in ("PostToolUse", "PostToolUseFailure"):
        if tool == "Read":
            ti = payload.get("tool_input") or {}
            fp = ti.get("file_path")
            if fp and os.path.isfile(fp):
                reads = store.load("reads.json", {})
                reads[f"{os.path.realpath(fp)}|{ti.get('offset')}|{ti.get('limit')}"] = {"hash": file_hash(fp), "session": session, "ts": int(time.time())}
                store.save("reads.json", reads)
            return
        cmd = command_of(payload)
        if not cmd:
            return
        cmd_key = cmd.replace(f"# {RERUN_MARK}", "").strip()
        failed = tool_failed(payload)
        is_test = bool(TEST_RE.search(cmd_key))
        fails = store.load("failures.json", {})
        if not failed and not is_test and cmd_key not in fails:
            return
        h = inputs_hash(store.root)
        if failed:
            sig = error_sig(payload)
            prev = fails.get(cmd_key, {})
            same = prev.get("inputs") == h and prev.get("sig") == sig
            fails[cmd_key] = {"cmd": cmd_key, "inputs": h, "sig": sig, "count": prev.get("count", 0) + 1 if same else 1, "ts": int(time.time())}
            store.save("failures.json", fails)
        elif cmd_key in fails:
            del fails[cmd_key]
            store.save("failures.json", fails)
        if is_test:
            cmds = store.load("commands.json", {})
            cmds[cmd_key] = {"result": "fail" if failed else "pass", "inputs": h, "ts": int(time.time())}
            store.save("commands.json", cmds)
        return
    if event in ("Stop", "SessionEnd"):
        tp = payload.get("transcript_path")
        if tp and session:
            u = transcript_usage(tp)
            if u and u["messages"]:
                sess = store.load("sessions.json", {})
                if sess or store.dir.exists():
                    sess[session] = dict(u, ts=int(time.time()))
                    store.save("sessions.json", sess)
        if event == "SessionEnd" and store.dir.exists():
            checkpoint(store, source="hook")
        return


# ------------------------------------------------------------------ cli
def forget(store, args):
    if not args:
        raise SystemExit("usage: forget KIND [TEXT] | --project | --everything")
    if args[0] == "--project":
        if store.dir.exists():
            shutil.rmtree(store.dir)
        return f"Deleted {store.dir}"
    if args[0] == "--everything":
        home = Path.home() / ".ross"
        removed = [str(p) for p in (store.dir, home) if p.exists()]
        for p in removed:
            shutil.rmtree(p)
        return "Deleted: " + (", ".join(removed) if removed else "nothing (no local ROSS state found)")
    kind = args[0]
    st = state(store)
    if kind not in st:
        return f"No {kind} recorded."
    if len(args) > 1:
        note(store, kind, " ".join(args[1:]), remove=True, source="user")
    else:
        st.pop(kind)
        store.save("state.json", st)
        store.append("deltas.jsonl", {"ts": int(time.time()), "op": "forget", "kind": kind, "source": "user"})
    return f"Forgot {kind}."


def doctor(store):
    checks = [("python >= 3.8", sys.version_info >= (3, 8)), ("git available", bool(shutil.which("git")))]
    try:
        store.ensure()
        probe = store.path(".probe")
        probe.write_text("ok")
        probe.unlink()
        checks.append(("state dir writable", True))
        if os.name == "posix":
            checks.append(("state dir private (0700)", (store.dir.stat().st_mode & 0o077) == 0))
        checks.append(("state dir git-ignored", (store.dir / ".gitignore").exists()))
    except OSError:
        checks.append(("state dir writable", False))
    return "\n".join(f"[{'ok' if ok else 'FAIL'}] {name}" for name, ok in checks) + f"\nstate: {store.dir}\nversion: {VERSION}"


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "hook":
        try:
            payload = json.load(sys.stdin)
        except ValueError:
            return 0
        try:
            hook(args[0] if args else payload.get("hook_event_name", ""), payload)
        except Exception as e:  # a hook must never break the host session
            sys.stderr.write(f"ross hook error: {e}\n")
        return 0
    store = Store()
    if cmd == "status":
        print(context(store, budget=2000) or "No ROSS state for this project yet.")
        print(savings(store).split("\n", 1)[-1])
    elif cmd == "context":
        budget = int(args[args.index("--budget") + 1]) if "--budget" in args else 600
        print(context(store, budget) or "")
    elif cmd == "note":
        remove = "--remove" in args
        rest = [a for a in args if a != "--remove"]
        if len(rest) < 2:
            raise SystemExit("usage: note [--remove] KIND TEXT")
        print("recorded" if note(store, rest[0], " ".join(rest[1:]), remove=remove) else "unchanged (nothing written)")
    elif cmd == "checkpoint":
        nxt = " ".join(args[args.index("--next") + 1:]) if "--next" in args else None
        print("checkpoint written" if checkpoint(store, nxt) else "unchanged (nothing written)")
    elif cmd == "savings":
        print(savings(store, "--all" in args))
    elif cmd == "forget":
        print(forget(store, args))
    elif cmd == "doctor":
        print(doctor(store))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
