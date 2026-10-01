#!/usr/bin/env python3
"""ROSS Efficiency Runtime: local-first operational state for AI agent work.

Perpetual state, not perpetual transcript. Standard library only. Nothing here
opens a network connection. State lives in <project>/.ross/ (git-ignored).

Commands:
  status                 compact view of durable state and local counters
  context [--budget N] [--deep]  continuation state (level 1; --deep adds level 3 history)
  map [CHARS]            path: symbol@line map of the repository (never injected automatically)
  note KIND TEXT         record one semantic delta (goal, next, decision,
                         constraint, preserve, blocker, fact, done)
  note --remove KIND TEXT
  checkpoint [--next T]  record a resume point (git state is derived)
  savings [--all]        local efficiency meter (measured / counted / estimated)
  exec CMD / view CMD    run a command / plain file read with the minimum actionable output
  artifact ID [--grep P | --lines A-B]   retrieve a full tool output kept locally
  prune [MAX_BYTES]      prune stored artifacts (default: all)
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

VERSION = "1.3.0-candidate"
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
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def save(self, name, data):
        self.ensure()
        p = self.path(name)
        tmp = p.with_suffix(p.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        os.replace(tmp, p)

    def append(self, name, record):
        self.ensure()
        fd = os.open(self.path(name), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

    def lines(self, name):
        try:
            return [json.loads(l) for l in self.path(name).read_text(encoding="utf-8").splitlines() if l.strip()]
        except (OSError, ValueError):
            return []


# ------------------------------------------------------------------ derived state
def git(root, *args):
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10)
        return r.stdout.rstrip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def git_state(root):
    sha = git(root, "rev-parse", "--short", "HEAD")
    if not sha:
        return {}
    dirty = [l[3:] for l in git(root, "status", "--porcelain", "--untracked-files=all").splitlines()
             if len(l) > 3 and not l[3:].startswith(".ross") and "__pycache__" not in l and not l.endswith(".pyc")]
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


def _trim(cmd):
    c = re.sub(r"\s*#\s*" + re.escape(RERUN_MARK), "", norm_cmd(cmd))
    c = re.sub(r"\s+2>&1", "", c)
    while True:
        new = re.sub(r"\s*\|\s*(tail|head|grep [^|]+)(\s+-n)?(\s+-?\d+)?\s*$", "", c)
        if new == c:
            return c
        c = new


def test_key(cmd):
    """One key per test invocation regardless of output trimming (`2>&1 | tail -20`), chained status commands,
    or a preceding edit script on earlier lines."""
    if isinstance(cmd, list):
        cmd = " ".join(map(str, cmd))
    segs = [x.strip() for x in re.split(r"\n|&&|;|\|\|", str(cmd or "")) if x.strip()]
    tests = [x for x in segs if (m := TEST_RE.search(x)) and m.start() < 40]
    return _trim(tests[-1]) if tests else _trim(cmd)


def pure_test(cmd):
    return test_key(cmd) == _trim(cmd)


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


def context(store, budget=400, deep=False):
    """Level 1 continuation state (the result of history, not history); level 3 with deep=True."""
    st = state(store)
    if not any(st.get(k) for k in ("goal", "next", "last_result", "changed", "blocker", "constraint", "preserve")):
        return ""
    g = git_state(store.root)
    lines = ["ROSS resume. Continuing means carrying on with the unfinished or explicitly deferred work below; "
             "this state was derived at the end of the last session, so re-verify only what you change."]
    if st.get("goal"):
        lines.append("Goal: " + st["goal"])
    if st.get("next"):
        lines.append("Next: " + st["next"])
    for kind, label in (("blocker", "Blocker"), ("constraint", "Constraints"), ("preserve", "Do not touch")):
        if st.get(kind):
            lines.append(f"{label}: " + "; ".join(reversed(st[kind][-4:])))
    if st.get("last_result"):
        lines.append("Last session ended with: " + st["last_result"].replace("\n", " ")[-480:])
    if g:
        d = g["dirty"]
        moved = st.get("end_sha") and st["end_sha"] != g["sha"]
        lines.append(f"Git: {g['branch']} @ {g['sha']}" + (f" (was {st['end_sha']} at session end)" if moved else "")
                     + (f"; uncommitted: {', '.join(d[:10])}" + (" ..." if len(d) > 10 else "") if d else "; clean"))
    if st.get("changed"):
        lines.append("Changed last session: " + ", ".join(st["changed"][:12]))
    h = inputs_hash(store.root)
    cmds = store.load("commands.json", {})
    ok = [c for c, r in cmds.items() if r.get("result") == "pass" and h and r.get("inputs") == h]
    stale = [c for c, r in cmds.items() if r.get("result") == "pass" and c not in ok]
    bad = [f"`{c}`: {r.get('summary', '')[:140]}" for c, r in cmds.items() if r.get("result") == "fail"]
    if ok:
        lines.append("Tests still passing on identical inputs (no need to rerun): " + "; ".join(
            f"`{c}` ({cmds[c].get('summary', '')[:60]})" for c in ok[:3]))
    if stale:
        lines.append("Passed before, inputs changed since: " + "; ".join(f"`{c}`" for c in stale[:3]))
    if bad:
        lines.append("Last known failures: " + "; ".join(bad[:3]))
    if deep:
        for kind, label in (("decision", "Decisions"), ("fact", "Facts"), ("done", "Done")):
            if st.get(kind):
                lines.append(f"{label}: " + "; ".join(reversed(st[kind][-10:])))
        for c in store.lines("checkpoints.jsonl")[-5:]:
            lines.append(f"Checkpoint {c.get('sha')} on {c.get('branch')}: next={c.get('next')}")
    elif any(st.get(k) for k in ("decision", "fact", "done")):
        lines.append(f'Older decisions and facts: python3 "{Path(__file__).resolve()}" context --deep')
    text, limit = "", budget * 4 if not deep else 1 << 20
    for l in lines:
        if len(text) + len(l) + 1 > limit:
            break
        text += l + "\n"
    return text.strip()


# ------------------------------------------------------------------ structural index (no file content stored)
SRC_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".rb", ".php", ".cs", ".kt", ".swift", ".c", ".cc", ".cpp", ".h"}
SYM_RE = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:def|class|function|func|fn|interface|type|struct|enum|"
                    r"const|let|public|private|protected|static)\s+([A-Za-z_][\w]*)")


def symbols(path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if path.suffix == ".py":
        import ast
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        out = []
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.append([n.name, n.lineno])
                if isinstance(n, ast.ClassDef):
                    out += [[f"{n.name}.{m.name}", m.lineno] for m in n.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))][:12]
            elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id.isupper():
                out.append([n.targets[0].id, n.lineno])
        return out
    return [[m.group(1), i] for i, l in enumerate(text.splitlines(), 1) if (m := SYM_RE.match(l))][:40]


def tracked(root):
    return [f for f in git(root, "ls-files", "-co", "--exclude-standard").splitlines()
            if not f.startswith(".ross/") and "__pycache__" not in f][:MAX_HASH_FILES]


def index_symbols(store, files):
    """Symbol index (hashes and names only, never content), refreshed only for files that changed."""
    src = [f for f in files if Path(f).suffix in SRC_EXT][:400]
    index = store.load("index.json", {})
    changed = False
    for rel in src:
        p = store.root / rel
        try:
            h = file_hash(p)
        except OSError:
            continue
        rec = index.get(rel)
        if not rec or rec.get("hash") != h:
            index[rel] = {"hash": h, "symbols": symbols(p), "lines": sum(1 for _ in open(p, encoding="utf-8", errors="replace"))}
            changed = True
    if changed:
        store.save("index.json", {k: v for k, v in index.items() if k in src})
    return index


def repo_map(store, budget_chars=2400):
    """Path: symbol@line map. Not injected automatically; `ross map` prints it on request."""
    files = tracked(store.root)
    index = index_symbols(store, files)
    out = []
    for rel in sorted(index):
        rec = index[rel]
        syms = ", ".join(f"{s}@{n}" for s, n in rec["symbols"][:10])
        out.append(f"{rel} ({rec['lines']}L): {syms}" if syms else f"{rel} ({rec['lines']}L)")
    text = ""
    for l in out:
        if len(text) + len(l) + 1 > budget_chars:
            text += f"... {len(out) - text.count(chr(10))} more files\n"
            break
        text += l + "\n"
    return text.rstrip()


# ------------------------------------------------------------------ progressive hydration (level 2: what this task names)
PATH_RE = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w-][\w.-]*\.(?:py|pyi|js|jsx|ts|tsx|mjs|cjs|go|rs|java|kt|rb|php|cs|c|cc|cpp|h|hpp|"
                     r"swift|md|rst|txt|json|toml|ya?ml|cfg|ini|sh|sql))(?![\w/])")
IDENT_RE = re.compile(r"`([A-Za-z_][\w.]{2,80})`|\b([A-Za-z_]\w*\.[A-Za-z_]\w+|[a-z][a-z0-9]*_[a-z0-9_]+|"
                      r"[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+|[A-Z][A-Z0-9]*_[A-Z0-9_]+)\b")
SECRET_FILE_RE = re.compile(r"(^|/)(\.env[^/]*|[^/]*\.(pem|key|p12|pfx|keystore)|id_[rd]sa[^/]*|[^/]*(secret|credential)[^/]*)$", re.I)
SMALL_FILE = 4000      # chars; named files up to this size are provided whole
HYDRATE_BUDGET = 9000  # chars (~2.3k tokens) for everything level 2 adds


def anchors(texts):
    """Deterministic relevance signals: file paths and code identifiers that the text names."""
    paths, idents = [], []
    for t in texts:
        for m in PATH_RE.finditer(t or ""):
            if m.group(1) not in paths:
                paths.append(m.group(1))
        for m in IDENT_RE.finditer(t or ""):
            name = m.group(1) or m.group(2)
            if name and not PATH_RE.fullmatch(name) and name not in idents:
                idents.append(name)
    return paths, idents[:20]


def resolve_paths(files, names):
    out = []
    for n in names:
        n = n[2:] if n.startswith("./") else n
        for f in [f for f in files if f == n or f.endswith("/" + n)][:2]:
            if f not in out and not SECRET_FILE_RE.search(f):
                out.append(f)
    return out


def mark_seen(store, rel, session, how):
    seen = store.load("seen.json", {})
    p = store.root / rel
    seen[rel] = {"hash": file_hash(p), "blob": git_blob(store.root, p), "session": session, "how": how}
    store.save("seen.json", seen)


def hydrate(store, texts, session, budget=HYDRATE_BUDGET):
    """Level 2: current contents of small files the task names, outlines of large ones and of files those
    documents name, and the exact range of named symbols. Never the whole repo; nothing provided twice per session."""
    paths, idents = anchors(texts)
    if not paths and not idents:
        return ""
    files = tracked(store.root)
    if not files:
        return ""
    named = resolve_paths(files, paths)
    index = index_symbols(store, files) if (named or idents) else {}
    seen = {k for k, v in store.load("seen.json", {}).items() if v.get("session") == session}
    blocks, outlines, used, full = [], [], [0], []

    def add(block):
        if used[0] + len(block) > budget:
            return False
        blocks.append(block)
        used[0] += len(block)
        return True

    def provide(rel, whole_ok=True):
        if rel in seen or rel in full:
            return
        p = store.root / rel
        try:
            text = redact(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            return
        if whole_ok and len(text) <= SMALL_FILE:
            if add(f"=== {rel} (current, whole file) ===\n{text.rstrip()}"):
                full.append(rel)
            return text
        rec = index.get(rel)
        if rec and rec["symbols"]:
            outlines.append(f"{rel} ({rec['lines']} lines): " + ", ".join(f"{s}@{n}" for s, n in rec["symbols"][:30]))
        elif not rec:
            outlines.append(f"{rel} ({text.count(chr(10)) + 1} lines)")

    for rel in named:
        text = provide(rel)
        if text and Path(rel).suffix in (".md", ".rst", ".txt"):  # a plan or doc the task names: files it names, one level
            for r2 in resolve_paths(files, anchors([text])[0]):
                if r2 not in named:
                    provide(r2)
    for name in idents:
        leaf = name.split(".")[-1]
        hits = [(rel, s, n) for rel, rec in index.items() for s, n in rec["symbols"] if s == name or s.split(".")[-1] == leaf][:2]
        for rel, s, n in hits:
            if rel in full or rel in seen:
                continue
            try:
                lines = (store.root / rel).read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            nxt = [m for t, m in index[rel]["symbols"] if m > n and "." not in t]
            end = min(min(nxt) - 1 if nxt else len(lines), n + 59)
            add(f"=== {rel}:{n}-{end} ({s}) ===\n" + redact("\n".join(lines[n - 1:end]).rstrip()))
    if outlines:
        add("Outlines (symbol@line; read the ranges you need):\n" + "\n".join(dict.fromkeys(outlines)))
    if not blocks:
        return ""
    for rel in full:
        mark_seen(store, rel, session, "provided")
    return "ROSS: current contents of files this task names (no need to read these again unless you change them):\n" + "\n".join(blocks)


# ------------------------------------------------------------------ artifact store (raw outputs stay local)
ARTIFACT_CAP = 64 * 1024 * 1024
PASS_THROUGH = 3000  # characters; smaller outputs reach the model unchanged
OUT_BUDGET = 3200


def store_artifact(store, text):
    data = redact(text).encode("utf-8", "replace")
    aid = hashlib.sha256(data).hexdigest()[:12]
    d = store.ensure().dir / "artifacts"
    d.mkdir(mode=0o700, exist_ok=True)
    p = d / f"{aid}.txt"
    if not p.exists():
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        prune_artifacts(store)
    return aid


def prune_artifacts(store, cap=ARTIFACT_CAP):
    d = store.dir / "artifacts"
    if not d.exists():
        return 0
    files = sorted(d.glob("*.txt"), key=lambda p: p.stat().st_mtime)
    total, removed = sum(p.stat().st_size for p in files), 0
    while files and total > cap:
        p = files.pop(0)
        total -= p.stat().st_size
        p.unlink()
        removed += 1
    return removed


def artifact_view(store, aid, grep=None, lines=None):
    p = store.dir / "artifacts" / f"{aid}.txt"
    if not p.exists():
        return f"artifact {aid} not found (pruned or deleted)"
    rows = p.read_text(encoding="utf-8", errors="replace").splitlines()
    if grep:
        rx = re.compile(grep)
        return "\n".join(f"{i}: {l}" for i, l in enumerate(rows, 1) if rx.search(l))
    if lines:
        a, _, b = lines.partition("-")
        return "\n".join(rows[int(a) - 1:int(b or a)])
    return "\n".join(rows)


def _pick(lines, rx, limit):
    return [l for l in lines if rx.search(l)][:limit]


def pytest_groups(lines):
    """Failures grouped by root error: count, example tests, failing location and the code around it."""
    sections, cur = [], None
    for l in lines:
        m = re.match(r"^_{3,} (.+?) _{3,}$", l)
        if m:
            cur = [m.group(1)]
            sections.append(cur)
        elif re.match(r"^=+ (short test summary|warnings summary|\d+ (passed|failed))", l):
            cur = None
        elif cur is not None:
            cur.append(l)
    groups = {}
    for sec in sections:
        errs = [l for l in sec if l.startswith("E ")]
        sig = re.sub(r"\s+", " ", errs[0] if errs else "(no E line)")
        sig = re.sub(r"'[^']*'|\"[^\"]*\"|\b\d+(\.\d+)?\b", "_", sig)[:160]
        locs = [l for l in sec if re.match(r"^\S+\.py:\d+: ", l)]
        g = groups.setdefault(sig, {"tests": [], "loc": locs[-1] if locs else "", "code": []})
        g["tests"].append(sec[0])
        if not g["code"]:
            first_e = next((i for i, l in enumerate(sec) if l.startswith("E ")), len(sec))
            g["code"] = [l[:160] for l in sec[max(1, first_e - 8):first_e] if l.strip()][-8:] + [e[:200] for e in errs[:2]]
    out = []
    for i, (sig, g) in enumerate(sorted(groups.items(), key=lambda kv: -len(kv[1]["tests"]))):
        out.append(f"{len(g['tests'])} failing with: {sig}  e.g. {', '.join(g['tests'][:3])}")
        if i < 3:
            out += ([f"  at {g['loc']}"] if g["loc"] else []) + [f"  {l}" for l in g["code"]]
    return out


def compress(cmd, text, failed, aid_cmd):
    """Deterministic minimum actionable view of a large tool output, or None to pass through."""
    if len(text) <= PASS_THROUGH:
        return None
    lines = text.splitlines()
    body = []
    if re.search(r"pytest|unittest|tox", cmd) or re.search(r"^=+ .*(passed|failed|error)", text, re.M):
        body += [l for l in lines if re.search(r"^=+ .*(passed|failed|error|no tests).*=+$|^\d+ (passed|failed|errors?)\b.* in [\d.]+s|"
                                               r"^Ran \d+ tests|^(OK|FAILED \()", l)][-2:]
        body += pytest_groups(lines)
        if len(body) < 3:
            body += _pick(lines, re.compile(r"^(FAILED|ERROR) |^E\s{2,}|^\S+\.py:\d+: |^(FAIL|ERROR): "), 60)
    elif re.search(r"jest|vitest|npm (run )?test|pnpm|yarn test", cmd):
        body += _pick(lines, re.compile(r"\u2715|\u25cf|FAIL |Tests?:|Test Files|Error:|expected|received", re.I), 60)
    elif re.search(r"\btsc\b|typescript", cmd) or re.search(r"error TS\d+", text):
        body += _pick(lines, re.compile(r"error TS\d+|Found \d+ error"), 60)
    elif re.search(r"^git (diff|show)", cmd) or (cmd.startswith("git log") and "\ndiff --git " in text):
        files = _pick(lines, re.compile(r"^diff --git "), 80)
        body += [f"{len(files)} files changed:"] + [f.split(" b/", 1)[-1] for f in files]
        body += [l for l in lines if l.startswith(("@@", "+", "-")) and not l.startswith(("+++", "---"))][:80]
    elif re.search(r"\beslint\b", cmd) or re.search(r"✖ \d+ problems?", text):
        for l in lines:
            if re.match(r"^\S.*\.(js|jsx|ts|tsx|mjs|cjs|vue)$", l) or re.match(r"^\s+\d+:\d+\s+(error|warning)", l) or "problem" in l:
                body.append(l)
        body = body[:80]
    elif re.search(r"\b(npm|pnpm|yarn|pip3?) (install|i|add|ci)\b", cmd):
        body += _pick(lines, re.compile(r"ERR!|\berror\b|\bwarn(ing)?\b|deprecated|vulnerabilit|added \d+|Successfully installed|"
                                        r"packages? (are|is) looking|Done in|Progress: resolved", re.I), 40)
    elif re.search(r"^git log\b", cmd) and lines and lines[0].startswith("commit "):
        commits, cur = [], None
        for l in lines:
            if l.startswith("commit "):
                cur = l[7:19]
            elif cur and l.startswith("    ") and l.strip():
                commits.append(f"{cur} {l.strip()}")
                cur = None
        body = [f"{len(commits)} commits (subjects only):"] + commits[:60]
    elif re.search(r"^(grep|rg|git grep)\b", cmd) and sum(1 for l in lines if re.match(r"^[^:\s]+:\d*:?", l)) > len(lines) * 0.6:
        per = {}
        for l in lines:
            per.setdefault(l.split(":", 1)[0], []).append(l)
        body = [f"{len(lines)} matches in {len(per)} files: " + ", ".join(f"{f} ({len(v)})" for f, v in list(per.items())[:30])]
        for f, v in per.items():
            body += v[:4]
            if len(body) > 70:
                break
    elif re.search(r"^(find|ls|git ls-files|tree)\b", cmd) and sum(1 for l in lines if " " not in l.strip()) > len(lines) * 0.8:
        dirs = {}
        for l in lines:
            parts = l.strip().lstrip("./").split("/")
            dirs[parts[0] if len(parts) > 1 else "."] = dirs.get(parts[0] if len(parts) > 1 else ".", 0) + 1
        body = [f"{len(lines)} entries; by top-level directory: " + ", ".join(f"{d} ({n})" for d, n in sorted(dirs.items(), key=lambda x: -x[1])[:25])]
        body += lines[:40]
    elif text.lstrip()[:1] in "[{":
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if data is not None:
            first = data[0] if isinstance(data, list) and data else data
            keys = list(first.keys())[:30] if isinstance(first, dict) else []
            body = [f"JSON {type(data).__name__} with {len(data)} items" + (f"; keys: {', '.join(map(str, keys))}" if keys else "")]
            body += json.dumps(data, indent=1)[:1500].splitlines()
    if not body:
        body += _pick(lines, re.compile(r"\b(error|Error|ERROR|warning|Warning|FAIL|failed|Traceback|exception|Exception)\b"), 40)
        tb = [i for i, l in enumerate(lines) if l.startswith("Traceback")]
        if tb:  # root error and the frames nearest to it
            body += lines[tb[-1]:tb[-1] + 1] + [l for l in lines[tb[-1]:] if l.strip().startswith("File ")][-4:] + lines[-6:]
    if not body:
        body = lines[:15] + ["..."] + lines[-25:]
    seen, kept = set(), []
    for l in body:
        if l not in seen:
            seen.add(l)
            kept.append(l[:300])
    shown = "\n".join(kept)[:OUT_BUDGET]
    return (f"[ROSS: {len(text):,} chars, {len(lines):,} lines, exit {'non-zero' if failed else '0'}; showing the actionable lines. "
            f"Full output: {aid_cmd}]\n{shown}")


# ------------------------------------------------------------------ metrics (MEASURED / COUNTED / ESTIMATED / INFERRED)
def metric(store, kind, value=1, estimated=False, session=None, detail=None, cls=None):
    store.append("metrics.jsonl", {"ts": int(time.time()), "kind": kind, "value": value,
                                   "cls": cls or ("ESTIMATED" if estimated else "COUNTED"), "session": session, "detail": redact(detail)})


def transcript_usage(path):
    """Provider-reported usage from a Claude Code transcript (MEASURED)."""
    tot = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "messages": 0}
    seen = set()
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
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
        a = agg.setdefault(r["kind"], [0, r.get("cls") or ("ESTIMATED" if r.get("estimated") else "COUNTED")])
        a[0] += r.get("value") or 0
    lines = ["ROSS savings (local only; nothing leaves this machine)"]
    if sessions:
        t = {k: sum(s.get(k, 0) for s in sessions.values()) for k in ("input", "cache_read", "cache_write", "output", "messages")}
        lines.append(f"[MEASURED] {len(sessions)} session(s), {t['messages']} model turns: uncached input {t['input']:,}, "
                     f"cached input {t['cache_read']:,}, cache write {t['cache_write']:,}, output {t['output']:,}")
    labels = [("outputs_compressed", "Tool outputs compressed"), ("raw_output_bytes", "Raw output bytes kept local"),
              ("presented_output_bytes", "Output bytes shown to the model"), ("reread_diffed", "Re-reads served as a diff"),
              ("large_read_outlined", "Very large reads served as outline + head"), ("read_bytes_displaced", "File bytes displaced by diffs/outlines"),
              ("dup_read_avoided", "Duplicate reads stopped"), ("test_reused", "Test runs reused (inputs unchanged)"),
              ("retry_prevented", "Identical failing retries prevented"), ("resume_injected", "Sessions resumed from compact state"),
              ("injected_bytes", "Bytes of state/map injected"), ("read_tokens_avoided", "Read tokens avoided"),
              ("hydrated_tokens", "Compact state injected (tokens)")]
    for kind, label in labels:
        if kind in agg:
            cls = agg[kind][1] + (", bytes/4" if agg[kind][1] == "ESTIMATED" else "")
            lines.append(f"[{cls}] {label}: {agg[kind][0]:,}")
    if "raw_output_bytes" in agg and "presented_output_bytes" in agg:
        cut = agg["raw_output_bytes"][0] - agg["presented_output_bytes"][0]
        lines.append(f"[ESTIMATED, bytes/4] Tool-output tokens kept out of context: {cut // 4:,}")
    if len(lines) == 1:
        lines.append("No activity recorded yet.")
    return "\n".join(lines)


# ------------------------------------------------------------------ hooks
RESUME_RE = re.compile(r"^\s*(continue|resume|carry on|keep going|go on|proceed|pick up|where were we|next)\b", re.I)
CODING_RE = re.compile(r"\b(add|implement|fix|refactor|build|update|change|create|write|debug|make|remove|rename|migrate|support|finish)\b", re.I)
LARGE_READ = 60000


def out(obj):
    sys.stdout.write(json.dumps(obj))


def deny(event, reason):
    out({"hookSpecificOutput": {"hookEventName": event, "permissionDecision": "deny", "permissionDecisionReason": reason}})


def replace_output(event, text):
    out({"hookSpecificOutput": {"hookEventName": event, "updatedToolOutput": text}})


def tool_text(payload):
    resp = payload.get("tool_response")
    if resp is None:
        resp = payload.get("error") or ""
    if isinstance(resp, dict):
        if isinstance(resp.get("file"), dict):
            return resp["file"].get("content") or ""
        parts = [resp[k] for k in ("stdout", "stderr", "content", "output") if isinstance(resp.get(k), str) and resp[k]]
        if parts:
            return "\n".join(parts)
        if isinstance(resp.get("filenames"), list):
            return "\n".join(map(str, resp["filenames"]))
        return json.dumps(resp)
    if isinstance(resp, list):
        return "\n".join(map(str, resp))
    return str(resp)


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
    return bool(re.search(r"(\b\d+ failed\b|\bFAILED\b|\bERRORS?\b|Traceback \(most recent|exit code [1-9]|npm ERR!|\bFAIL\b)", tool_text(payload)))


def error_sig(payload):
    text = tool_text(payload)
    lines = [l for l in text.splitlines() if re.search(r"(Error|FAIL|failed|assert|Exception)", l)]
    sig = re.sub(r"0x[0-9a-f]+|\d+\.\d+s|\b\d{2,}\b", "#", " | ".join(lines[-3:]))[:240]
    return redact(sig) or "nonzero exit"


HEAVY_RE = re.compile(r"(^|[\s;&|(])(pytest|py\.test|python3? -m (pytest|unittest)|npm|pnpm|yarn|npx|jest|vitest|tsc|eslint|ruff|"
                      r"flake8|mypy|pylint|go (test|build|vet)|cargo (test|build|clippy)|mvn|gradle|\./gradlew|make|dotnet|"
                      r"pip3? install|git (diff|log|show)|grep -[a-zA-Z]*r|rg |find |tox)\b")
READ_SEG_RE = re.compile(r"(^|&&|;|\|\||\n)\s*(cat|nl|sed|head|tail|less|more|awk|bat|echo|printf|python3? -c)\b")
UNSAFE_WRAP_RE = re.compile(r"(^|[;&|]\s*)(cd|export|source|\.|alias|unset|set|pushd|popd)\s|<<|&\s*$|\bsudo\b")
WRAP_RE = re.compile(r'ross\.py"? exec (.+)$')


def command_of(payload):
    ti = payload.get("tool_input") or {}
    cmd = norm_cmd(ti.get("command") or ti.get("cmd") or ti.get("argv") or "")
    m = WRAP_RE.search(cmd)
    if m:
        import shlex
        try:
            return norm_cmd(shlex.split(m.group(1))[0])
        except (ValueError, IndexError):
            return cmd
    return cmd


def run_exec(store, cmd):
    """Run a command exactly as the shell would; keep full output local, print the actionable view, keep the exit code."""
    shell = "/bin/bash" if os.name == "posix" and os.path.exists("/bin/bash") else None
    p = subprocess.run(cmd, shell=True, executable=shell, capture_output=True, text=True, errors="replace")
    text = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    if len(text) <= PASS_THROUGH:
        sys.stdout.write(p.stdout or "")
        sys.stderr.write(p.stderr or "")
        return p.returncode
    aid = store_artifact(store, text)
    view = compress(cmd, text, p.returncode != 0, f'python3 "{Path(__file__).resolve()}" artifact {aid} [--grep PATTERN | --lines A-B]')
    metric(store, "outputs_compressed", 1, detail=cmd[:120])
    metric(store, "raw_output_bytes", len(text))
    metric(store, "presented_output_bytes", len(view))
    sys.stdout.write(view + "\n")
    return p.returncode


FULL_MARK = "ross:full"
CAT_RE = re.compile(r"^(cat|nl)(\s+-n)?(\s+[\w./@+-]+)+$")  # plain whole-file reads only: no pipes, globs, redirects
LARGE_SHELL_READ = 24000


def run_view(store, cmd, session):
    """Serve a plain `cat`/`nl` of project files: unchanged-since-seen files are not repeated, changed ones come as a
    diff, very large ones as an outline plus the first lines. Exit code and error text are the real command's."""
    import difflib
    import shlex
    argv = shlex.split(cmd)
    files = [a for a in argv[1:] if not a.startswith("-")]
    if not files or any(not os.path.isfile(f) for f in files):
        return subprocess.run(cmd, shell=True).returncode
    seen = store.load("seen.json", {})
    out, saved = [], 0
    for f in files:
        p = Path(f).resolve()
        try:
            rel = str(p.relative_to(store.root))
            text = p.read_text(encoding="utf-8")
        except (ValueError, OSError, UnicodeDecodeError):
            rel, text = None, None
        if rel is None:
            r = subprocess.run([argv[0]] + [a for a in argv[1:] if a.startswith("-")] + [f], capture_output=True, text=True, errors="replace")
            out.append(r.stdout)
            continue
        h, rec = file_hash(p), seen.get(rel)
        shown = None
        if rec and rec.get("session") == session and rec.get("hash") == h:
            shown = f"[ROSS: {rel} is unchanged since it was {rec.get('how', 'read')} earlier in this session; not repeated. Add '# {FULL_MARK}' to print it.]\n"
        elif rec and rec.get("session") == session and rec.get("blob"):
            old = git(store.root, "cat-file", "-p", rec["blob"])
            if old:
                diff = "".join(difflib.unified_diff(old.splitlines(True), text.splitlines(True), f"{rel} (seen earlier)", f"{rel} (now)", n=3))
                if diff and len(diff) < 0.6 * len(text):
                    shown = f"[ROSS: {rel} changed since you saw it; only the changes are shown.]\n{diff}"
        if shown is None and len(text) > LARGE_SHELL_READ:
            syms = symbols(p)
            head = "\n".join(text.splitlines()[:80])
            shown = (f"[ROSS: {rel} is {len(text):,} chars / {text.count(chr(10)) + 1} lines. Outline and first 80 lines; read a range with "
                     f"sed -n 'A,Bp' {f}, or add '# {FULL_MARK}' to print it all.]\nOutline: "
                     + ", ".join(f"{s}@{n}" for s, n in syms[:60]) + f"\n{head}\n")
        if shown is None:
            if argv[0] == "nl" or "-n" in argv[1:]:
                shown = subprocess.run([argv[0]] + [a for a in argv[1:] if a.startswith("-")] + [f], capture_output=True, text=True, errors="replace").stdout
            else:
                shown = text
            seen[rel] = {"hash": h, "blob": git_blob(store.root, p), "session": session, "how": "read"}
        else:
            saved += max(0, len(text) - len(shown))
        out.append(shown)
    store.save("seen.json", seen)
    if saved:
        metric(store, "read_bytes_displaced", saved, session=session)
        metric(store, "shell_reads_reduced", 1, session=session)
    sys.stdout.write("".join(out))
    return 0


def git_blob(root, path):
    return git(root, "hash-object", "--", str(path))


def handle_read(store, event, payload, session):
    ti = payload.get("tool_input") or {}
    fp = ti.get("file_path")
    if not fp or not os.path.isfile(fp):
        return
    key = f"{os.path.realpath(fp)}|{ti.get('offset')}|{ti.get('limit')}"
    content = tool_text(payload)
    reads = store.load("reads.json", {})
    prev = reads.get(key)
    blob = git_blob(store.root, fp)
    reads[key] = {"hash": file_hash(fp), "blob": blob, "session": session, "ts": int(time.time())}
    store.save("reads.json", reads)
    full = not ti.get("offset") and not ti.get("limit")
    if full:
        try:
            mark_seen(store, str(Path(fp).resolve().relative_to(store.root)), session, "read")
        except ValueError:
            pass
    if full and prev and prev.get("session") == session and prev.get("blob") and prev["blob"] != blob:
        old = git(store.root, "cat-file", "-p", prev["blob"])  # git is the source of truth; no copy stored
        if old:
            import difflib
            diff = "".join(difflib.unified_diff(old.splitlines(True), Path(fp).read_text(encoding="utf-8", errors="replace").splitlines(True),
                                                "before", "now", n=3))
            if diff and len(diff) < 0.6 * len(content):
                metric(store, "reread_diffed", 1, session=session, detail=fp)
                metric(store, "read_bytes_displaced", len(content) - len(diff), session=session)
                replace_output(event, f"[ROSS: {os.path.basename(fp)} changed since you read it earlier in this session; "
                                      f"everything outside these hunks is unchanged from that read.]\n{diff}")
                return
    if full and len(content) > LARGE_READ:
        syms = symbols(Path(fp))
        head = "\n".join(content.splitlines()[:150])
        outline = ", ".join(f"{s}@{n}" for s, n in syms[:80])
        view = (f"[ROSS: {os.path.basename(fp)} is {len(content):,} chars. Showing an outline and the first 150 lines; "
                f"read the part you need with offset/limit.]\nOutline: {outline}\n{head}")
        metric(store, "large_read_outlined", 1, session=session, detail=fp)
        metric(store, "read_bytes_displaced", len(content) - len(view), session=session)
        replace_output(event, view)


NUDGE = "ROSS: Enough state is available to batch the next safe inspection/execution step."
WRITE_RE = re.compile(r"<<|(^|[^2&])>\s*[\w./]|\bsed -i|\btee\b|\.write(_text)?\(|open\([^)]*['\"][wa]|\bpatch\b|\bgit (apply|commit|mv|rm)\b|\b(mv|cp|rm|mkdir|touch)\s")
NEXT_RE = re.compile(r"(?im)^\W*(?:next(?: steps?)?|remaining|still to do|todo|follow[- ]up)\W*[:\-]\s*(.+)$")
DEFER_RE = re.compile(r"(?i)\b(next session|haven'?t (started|done)|have not (started|done)|not (started|done) yet|left (it |this )?for|deferred|"
                      r"still (needs?|to do)|remaining work|out of scope for now)\b")
BLOCK_RE = re.compile(r"(?im)^\W*(?:blocker|blocked(?: on| by)?)\W*[:\-]\s*(.+)$|([^.\n]*\b(?:blocked (?:on|by)|cannot proceed|can'?t proceed)\b[^.\n]*)")


def next_and_blocker(msg):
    """Explicit next step and blocker from the agent's own final message; no model call, no inference beyond the text."""
    m = NEXT_RE.search(msg)
    nxt = m.group(1).strip() if m else None
    if not nxt:
        for sent in re.split(r"(?<=[.!?])\s+|\n+", msg):
            if DEFER_RE.search(sent):
                nxt = sent.strip(" -*")
                break
    b = BLOCK_RE.search(msg)
    return nxt, (b.group(1) or b.group(2)).strip(" -*") if b else None


def _turns(path, tail=None):
    """Assistant turns from a host transcript: [(message id, kinds)], kinds in inspect/implement/verify/recovery."""
    try:
        with open(path, "rb") as f:
            if tail:
                f.seek(max(0, os.path.getsize(path) - tail))
            raw = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    turns, errored = [], False
    for line in raw:
        try:
            j = json.loads(line)
        except ValueError:
            continue
        msg = j.get("message") or {}
        content = msg.get("content") if isinstance(msg.get("content"), list) else []
        if j.get("type") == "assistant":
            if not turns or turns[-1][0] != msg.get("id"):
                turns.append([msg.get("id"), set(), errored])
                errored = False
            for c in content:
                if c.get("type") != "tool_use":
                    continue
                name, cmd = c.get("name", ""), str((c.get("input") or {}).get("command") or "")
                acted = False
                if name in ("Edit", "Write", "MultiEdit", "NotebookEdit") or (cmd and WRITE_RE.search(cmd)):
                    turns[-1][1].add("implement")
                    acted = True
                if cmd and TEST_RE.search(cmd):
                    turns[-1][1].add("verify")
                    acted = True
                if not acted:
                    turns[-1][1].add("inspect")
        elif j.get("type") == "user":
            for c in content:
                if c.get("type") == "tool_result" and (c.get("is_error") or re.search(r"\b\d+ failed\b|Traceback|Exit code [1-9]", json.dumps(c.get("content"))[:20000])):
                    errored = True
    return turns


def turn_stats(path):
    turns = _turns(path)
    if not turns:
        return None
    s = {"turns": len(turns), "inspection_only": 0, "implementation": 0, "verification": 0, "recovery": 0,
         "to_first_action": None, "to_implementation": None, "to_verified": None}
    for i, (_, kinds, after_error) in enumerate(turns, 1):
        if kinds == {"inspect"}:
            s["inspection_only"] += 1
        if "implement" in kinds:
            s["implementation"] += 1
            s["to_implementation"] = s["to_implementation"] or i
        if "verify" in kinds:
            s["verification"] += 1
            s["to_verified"] = i
        if kinds and kinds != {"inspect"}:
            s["to_first_action"] = s["to_first_action"] or i
        if after_error and kinds:
            s["recovery"] += 1
    return s


def nudge_due(store, payload, session):
    """Two consecutive inspection-only turns: say once per session that state suffices to batch the next step."""
    tp = payload.get("transcript_path")
    if not tp or not session or not store.dir.exists():
        return False
    turns = [t for t in _turns(tp, tail=262144) if t[1]]
    if len(turns) < 2 or turns[-1][1] != {"inspect"} or turns[-2][1] != {"inspect"}:
        return False
    flags = store.load("nudges.json", {})
    if session in flags:
        return False
    flags = {k: v for k, v in flags.items() if v > time.time() - 7 * 86400}
    flags[session] = int(time.time())
    store.save("nudges.json", flags)
    return True


def hook(event, payload):
    store = Store(payload.get("cwd"))
    session = payload.get("session_id")
    tool = payload.get("tool_name") or ""
    rt = Path(__file__).resolve()
    if event == "SessionStart":
        return  # context is chosen once the prompt is known (UserPromptSubmit)
    if event == "UserPromptSubmit":
        prompt = (payload.get("prompt") or "").strip()
        resume = bool(RESUME_RE.match(prompt)) and len(prompt) < 80
        coding = bool(CODING_RE.search(prompt)) and len(prompt) >= 40
        if not (resume or coding) or not store.root.joinpath(".git").exists() and not store.dir.exists():
            return  # level 0: no state read or written, nothing injected
        st = state(store)
        first = st.get("session") != session
        new = dict(st)
        if coding and not resume:
            new["goal"] = redact(prompt[:400])
            if first:
                new.pop("next", None)  # a new instruction supersedes the old next step
        if first:
            new["session"] = session
            new["session_sha"] = git(store.root, "rev-parse", "HEAD")
        parts = []
        if resume and first:
            lvl1 = context(store)  # level 1, from the state the last session left
            if lvl1:
                parts.append(lvl1)
                metric(store, "resume_injected", 1, session=session)
        if new != st:
            new["updated"] = int(time.time())
            store.save("state.json", new)
        texts = [prompt] + ([st.get("goal"), st.get("next"), "; ".join(st.get("blocker") or [])] if resume else [])
        lvl2 = hydrate(store, texts, session)  # level 2, only what the task names
        if lvl2:
            parts.append(lvl2)
            metric(store, "hydrated_files", lvl2.count("\n=== ") + lvl2.startswith("=== "), session=session)
        if parts:
            ctx = "\n\n".join(parts)
            metric(store, "injected_bytes", len(ctx), session=session)
            out({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}})
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
                metric(store, "dup_read_avoided", 1, session=session, detail=fp)
                metric(store, "read_tokens_avoided", os.path.getsize(fp) // 4, estimated=True, session=session)
                deny("PreToolUse", f"ROSS: {os.path.basename(fp)} is unchanged since you read it earlier in this session. "
                                   f"Use the content already in context.")
            return
        cmd = command_of(payload)
        if not cmd or os.environ.get("ROSS_FORCE"):
            return
        ti = payload.get("tool_input") or {}
        raw = norm_cmd(ti.get("command") or "")
        if tool == "Bash" and CAT_RE.match(cmd) and FULL_MARK not in raw and not WRAP_RE.search(raw) and store.root.joinpath(".git").exists():
            import shlex
            out({"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": dict(
                ti, command=f'ROSS_SESSION={shlex.quote(session or "")} python3 "{rt}" view {shlex.quote(ti.get("command") or cmd)}')}})
            return
        wrap = (tool == "Bash" and HEAVY_RE.search(cmd) and not UNSAFE_WRAP_RE.search(cmd) and not ti.get("run_in_background")
                and not WRAP_RE.search(raw) and FULL_MARK not in raw and not READ_SEG_RE.search(ti.get("command") or ""))
        fails = store.load("failures.json", {})
        cmds = store.load("commands.json", {})
        is_test = bool(TEST_RE.search(cmd))
        tkey = test_key(cmd) if is_test else cmd
        guarded = RERUN_MARK not in cmd and ((tkey in fails and (not is_test or pure_test(cmd))) or (is_test and tkey in cmds and pure_test(cmd)))
        if not guarded:
            if wrap:
                import shlex
                run = ti.get("command") or cmd
                if is_test and pure_test(run) and "|" in run:
                    run = tkey  # ROSS gives the root errors and the summary instead of an arbitrary head/tail slice
                out({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                            "updatedInput": dict(ti, command=f'python3 "{rt}" exec {shlex.quote(run)}')}})
            return
        h = inputs_hash(store.root)
        f = fails.get(tkey)
        if h and f and f.get("inputs") == h and f.get("count", 0) >= 2:
            metric(store, "retry_prevented", 1, session=session, detail=cmd[:120])
            deny("PreToolUse", f"ROSS: `{cmd[:120]}` already failed {f['count']} times with identical inputs and the same error "
                               f"({f.get('sig', '')[:160]}). Change the diagnosis or the inputs first. Append '# {RERUN_MARK}' only "
                               f"if the user asked for another attempt or something outside the project files changed.")
            return
        c = cmds.get(tkey)
        if is_test and h and c and c.get("result") == "pass" and c.get("inputs") == h:
            metric(store, "test_reused", 1, session=session, detail=cmd[:120])
            deny("PreToolUse", f"ROSS: `{cmd[:120]}` already PASSED against identical inputs; treat it as passing. Append "
                               f"'# {RERUN_MARK}' only if the user asked for a fresh run or something outside the project files changed.")
            return
        if wrap:
            import shlex
            out({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                        "updatedInput": dict(ti, command=f'python3 "{rt}" exec {shlex.quote(ti.get("command") or cmd)}')}})
        return
    if event in ("PostToolUse", "PostToolUseFailure"):
        if tool == "Read":
            handle_read(store, event, payload, session)
            return
        text = tool_text(payload)
        if tool in ("Grep", "Glob"):
            if len(text) > PASS_THROUGH:
                aid = store_artifact(store, text)
                lines = text.splitlines()
                view = (f"[ROSS: {len(lines):,} results ({len(text):,} chars). First 60 shown. Full list: python3 \"{rt}\" artifact {aid} "
                        f"[--grep PATTERN]. Narrow the search if these are not enough.]\n" + "\n".join(lines[:60]))
                metric(store, "outputs_compressed", 1, session=session)
                metric(store, "raw_output_bytes", len(text), session=session)
                metric(store, "presented_output_bytes", len(view), session=session)
                replace_output(event, view)
            return
        cmd = command_of(payload)
        if not cmd:
            return
        cmd_key = cmd.replace(f"# {RERUN_MARK}", "").strip()
        failed = tool_failed(payload)
        is_test = bool(TEST_RE.search(cmd_key))
        if is_test:
            cmd_key = test_key(cmd_key)
        fails = store.load("failures.json", {})
        if failed or is_test or cmd_key in fails:
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
                summary = next((l for l in text.splitlines()[::-1] if re.search(r"passed|failed|error|Ran \d+|Tests?:", l)), "")
                cmds[cmd_key] = {"result": "fail" if failed else "pass", "inputs": h, "ts": int(time.time()), "summary": redact(summary)[:200]}
                store.save("commands.json", cmds)
        res = {}
        raw_cmd = str((payload.get("tool_input") or {}).get("command") or "")
        if (len(text) > PASS_THROUGH and HEAVY_RE.search(cmd) and not WRAP_RE.search(norm_cmd(raw_cmd))
                and not READ_SEG_RE.search(raw_cmd)):  # never compress output the agent asked to read
            aid = store_artifact(store, text)
            view = compress(cmd_key, text, failed, f'python3 "{rt}" artifact {aid} [--grep PATTERN | --lines A-B]')
            if view:
                metric(store, "outputs_compressed", 1, session=session, detail=cmd_key[:120])
                metric(store, "raw_output_bytes", len(text), session=session)
                metric(store, "presented_output_bytes", len(view), session=session)
                res["updatedToolOutput"] = view
        if nudge_due(store, payload, session):
            metric(store, "batch_nudge", 1, session=session)
            res["additionalContext"] = NUDGE
        if res:
            out({"hookSpecificOutput": dict(res, hookEventName=event)})
        return
    if event in ("Stop", "SessionEnd"):
        if not store.dir.exists():
            return
        tp = payload.get("transcript_path")
        if tp and session:
            u = transcript_usage(tp)
            if u and u["messages"]:
                sess = store.load("sessions.json", {})
                sess[session] = dict(u, ts=int(time.time()))
                store.save("sessions.json", sess)
        st = state(store)
        new = dict(st)
        msg = (payload.get("last_assistant_message") or "").strip()
        if msg:
            new["last_result"] = redact(msg)[-500:]
            nxt, blocker = next_and_blocker(msg)
            if nxt:
                new["next"] = redact(nxt)[:240]
            if blocker:
                new["blocker"] = [redact(blocker)[:240]]
            elif new.get("blocker") and not nxt:
                new.pop("blocker")
        g = git_state(store.root)
        if g:
            new["end_sha"], new["branch"] = g["sha"], g["branch"]
        if tp and session:
            t = turn_stats(tp)
            if t:
                sess = store.load("sessions.json", {})
                sess.setdefault(session, {})["turn_stats"] = t
                store.save("sessions.json", sess)
        base = st.get("session_sha")
        changed = set(git(store.root, "diff", "--name-only", base).splitlines()) if base else set()
        changed |= set(git_state(store.root).get("dirty", []))
        if changed:
            new["changed"] = sorted(changed)[:30]
        if new != st:
            new["updated"] = int(time.time())
            store.save("state.json", new)
        if event == "SessionEnd":
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
        budget = int(args[args.index("--budget") + 1]) if "--budget" in args else 400
        print(context(store, budget, deep="--deep" in args) or "")
    elif cmd == "map":
        print(repo_map(store, budget_chars=int(args[0]) if args else 6000) or "")
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
    elif cmd == "exec":
        if not args:
            raise SystemExit("usage: exec COMMAND")
        return run_exec(store, " ".join(args))
    elif cmd == "view":
        if not args:
            raise SystemExit("usage: view 'cat FILE ...'")
        return run_view(store, " ".join(args), os.environ.get("ROSS_SESSION") or "")
    elif cmd == "artifact":
        if not args:
            raise SystemExit("usage: artifact ID [--grep PATTERN | --lines A-B]")
        g = args[args.index("--grep") + 1] if "--grep" in args else None
        ln = args[args.index("--lines") + 1] if "--lines" in args else None
        print(artifact_view(store, args[0], g, ln))
    elif cmd == "prune":
        print(f"removed {prune_artifacts(store, int(args[0]) if args else 0)} artifact(s)")
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
