"""Deterministic tool-output reduction: the smallest useful representation, with the full output kept as an artifact.
Never a model call. Ported from the plugin runtime's proven compressor (the plugin itself is unchanged)."""
import re

PASS_THROUGH = 3000
BUDGET = 3200


# Lines that must never be reduced away: security-relevant findings travel to the model even when everything else is cut.
SECURITY_RE = re.compile(r"(?i)\b(insecure\w*|tls|ssl|certificates?|verify\s*=\s*false|verification\b.{0,20}\bdisabled|cve-\d{4}-\d+|"
                         r"vulnerab\w*|security\w*|unsafe|credentials?|secrets?|private key|permission denied|hardcoded)\b")
WARNING_RE = re.compile(r"\b\w*Warning\b:")


def _pick(lines, rx, limit):
    return [l for l in lines if rx.search(l)][:limit]


def _warnings(lines, limit=10):
    """Warning messages, from a pytest 'warnings summary' section when present, otherwise from Python warning lines."""
    out, inside = [], False
    for l in lines:
        if re.match(r"^=+ warnings summary =+$", l):
            inside = True
            continue
        if inside and (re.match(r"^=+ ", l) or l.startswith("-- Docs:")):
            inside = False
        if (inside or not out) and WARNING_RE.search(l):
            out.append(l.strip())
    return out[:limit]


def _pytest_groups(lines):
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
        sig = re.sub(r"'[^']*'|\"[^\"]*\"|\b\d+(\.\d+)?\b", "_", re.sub(r"\s+", " ", errs[0] if errs else "(no E line)"))[:160]
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


def reduce_output(cmd, text, exit_code, artifact_id):
    """Return text unchanged when small, else exit status, root errors, locations, summary and the artifact pointer."""
    if len(text) <= PASS_THROUGH:
        return text
    lines = text.splitlines()
    body, lead = [], 0
    if re.search(r"pytest|unittest|tox", cmd) or re.search(r"^=+ .*(passed|failed|error)", text, re.M):
        body += [l for l in lines if re.search(r"^=+ .*(passed|failed|error|no tests).*=+$|^\d+ (passed|failed|errors?)\b.* in [\d.]+s|"
                                               r"^Ran \d+ tests|^(OK|FAILED \()", l)][-2:]
        lead = len(body)
        body += _pytest_groups(lines)
        if len(body) < 3:
            body += _pick(lines, re.compile(r"^(FAILED|ERROR) |^E\s{2,}|^\S+\.py:\d+: |^(FAIL|ERROR): "), 60)
    elif re.search(r"jest|vitest|npm (run )?test|pnpm|yarn test", cmd):
        body += _pick(lines, re.compile(r"✕|●|FAIL |Tests?:|Test Files|Error:|expected|received", re.I), 60)
    elif re.search(r"\btsc\b", cmd) or re.search(r"error TS\d+", text):
        body += _pick(lines, re.compile(r"error TS\d+|Found \d+ error"), 60)
    elif re.search(r"^git (diff|show)", cmd):
        files = _pick(lines, re.compile(r"^diff --git "), 80)
        body += [f"{len(files)} files changed:"] + [f.split(" b/", 1)[-1] for f in files]
        body += [l for l in lines if l.startswith(("@@", "+", "-")) and not l.startswith(("+++", "---"))][:80]
    if not body:
        body += _pick(lines, re.compile(r"\b(error|Error|ERROR|warning|Warning|FAIL|failed|Traceback|exception|Exception)\b"), 40)
        tb = [i for i, l in enumerate(lines) if l.startswith("Traceback")]
        if tb:
            body += lines[tb[-1]:tb[-1] + 1] + [l for l in lines[tb[-1]:] if l.strip().startswith("File ")][-4:] + lines[-6:]
    if not body:
        body = lines[:15] + ["..."] + lines[-25:]
    # Security findings and warnings go right after the leading summary so the size budget can never cut them.
    body = body[:lead] + _pick(lines, SECURITY_RE, 8) + _warnings(lines) + body[lead:]
    seen, kept = set(), []
    for l in body:
        if l.strip() not in seen:
            seen.add(l.strip())
            kept.append(l[:300])
    where = f"artifact {artifact_id} (use the artifact tool with grep or lines)" if artifact_id else "not kept (sensitive output)"
    return (f"[exit {exit_code}; {len(text):,} chars, {len(lines):,} lines; showing the actionable lines. Full output: {where}]\n"
            + "\n".join(kept)[:BUDGET])
