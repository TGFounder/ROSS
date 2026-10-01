#!/usr/bin/env python3
"""Generate and verify ROSS host packages from the canonical source.

One canonical runtime, two thin host packages:
  distribution/claude/ross   Claude Code / Claude apps (.claude-plugin/plugin.json)
  distribution/openai/ross   Codex / OpenAI portable plugin (plugin.json)

Both packages carry byte-identical skill files and the same hook handler.
Packaged runtime files are never edited by hand.

  build.py lock    record canonical digests (only for a deliberate new candidate)
  build.py build   regenerate both packages from canonical source
  build.py check   fail if any package differs from canonical or the lock
"""

import hashlib
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
LOCK = Path(__file__).resolve().parent / "runtime.lock"
RUNTIME_FILES = ["SKILL.md", "LICENSE", "runtime/ross.py"] + sorted(
    p.relative_to(ROOT).as_posix() for d in ("references", "profiles") for p in (ROOT / d).glob("*") if p.is_file())
HOSTS = {
    "claude": {"pkg": ROOT / "distribution" / "claude" / "ross", "matcher": "Read|Bash"},
    "openai": {"pkg": ROOT / "distribution" / "openai" / "ross", "matcher": None},
}
SKIP_DIRS = {"__pycache__"}


def norm(path: Path) -> bytes:
    """Bytes with CRLF normalized, so Windows checkouts verify identically."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(norm(path)).hexdigest()


def hooks_json(matcher):
    cmd = 'python3 "${CLAUDE_PLUGIN_ROOT}/skills/ross/runtime/ross.py" hook '

    def entry(event, tool_scoped):
        e = {"hooks": [{"type": "command", "command": cmd + event, "timeout": 15}]}
        if tool_scoped and matcher:
            e["matcher"] = matcher
        return [e]

    hooks = {
        "SessionStart": entry("SessionStart", False),
        "PreToolUse": entry("PreToolUse", True),
        "PostToolUse": entry("PostToolUse", True),
        "Stop": entry("Stop", False),
        "SessionEnd": entry("SessionEnd", False),
    }
    if matcher:
        hooks["PostToolUseFailure"] = entry("PostToolUseFailure", True)
    return json.dumps({"description": "ROSS efficiency runtime: local state, read and test reuse, retry guard",
                       "hooks": hooks}, indent=2) + "\n"


def read_lock():
    files = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "  " in line:
            digest, rel = line.split("  ", 1)
            files[rel] = digest
    return files


def lock():
    lines = ["# Canonical ROSS runtime digests for the current candidate.",
             "# Regenerate only when the canonical runtime deliberately changes."]
    lines += [f"{sha256(ROOT / rel)}  {rel}" for rel in RUNTIME_FILES]
    LOCK.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check():
    files = read_lock()
    problems = []
    if sorted(files) != sorted(RUNTIME_FILES):
        problems.append("runtime.lock does not list exactly the canonical runtime files")
    for rel, digest in files.items():
        if not (ROOT / rel).is_file() or sha256(ROOT / rel) != digest:
            problems.append(f"canonical file differs from runtime.lock: {rel}")
    for host, spec in HOSTS.items():
        skill = spec["pkg"] / "skills" / "ross"
        for rel, digest in files.items():
            p = skill / rel
            if not p.is_file() or p.is_symlink() or sha256(p) != digest:
                problems.append(f"{host}: packaged file differs from canonical: {rel}")
        actual = {p.relative_to(skill).as_posix() for p in skill.rglob("*") if p.is_file() and not SKIP_DIRS & set(p.parts)}
        for extra in sorted(actual - set(files)):
            problems.append(f"{host}: unexpected packaged file: {extra}")
        hj = spec["pkg"] / "hooks" / "hooks.json"
        if not hj.is_file() or norm(hj).decode() != hooks_json(spec["matcher"]):
            problems.append(f"{host}: hooks/hooks.json is not the generated version")
        if norm(spec["pkg"] / "LICENSE") != norm(ROOT / "LICENSE"):
            problems.append(f"{host}: plugin LICENSE differs from canonical")
        for forbidden in (".mcp.json", "bin", "agents", "commands", ".lsp.json"):
            if (spec["pkg"] / forbidden).exists():
                problems.append(f"{host}: package contains {forbidden}")
    if problems:
        raise SystemExit("FAIL: distribution drift\n  " + "\n  ".join(problems))
    print(f"PASS: claude and openai packages match canonical ROSS ({len(files)} runtime files)")


def build():
    for host, spec in HOSTS.items():
        skill = spec["pkg"] / "skills" / "ross"
        if skill.exists():
            shutil.rmtree(skill)
        for rel in RUNTIME_FILES:
            target = skill / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, target)
        (spec["pkg"] / "hooks").mkdir(parents=True, exist_ok=True)
        (spec["pkg"] / "hooks" / "hooks.json").write_text(hooks_json(spec["matcher"]))
        shutil.copyfile(ROOT / "LICENSE", spec["pkg"] / "LICENSE")
    check()


if __name__ == "__main__":
    action = sys.argv[1:] or ["check"]
    {"lock": lock, "build": build, "check": check}.get(action[0], lambda: sys.exit("usage: build.py lock|build|check"))()
