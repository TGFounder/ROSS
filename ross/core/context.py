"""Context policy: a byte-stable prefix (policy + tools) and a small dynamic suffix (request, preflight, relevant state).
Cache is not memory: the provider cache holds processed prompt bytes for minutes; ROSS memory is durable and enters context
only when relevant."""
import re
from pathlib import Path

from . import evidence

RESUME_RE = re.compile(r"^\s*(continue|resume|carry on|keep going|go on|proceed|pick up|where were we)\b", re.I)
CODING_RE = re.compile(r"\b(add|implement|fix|refactor|build|update|change|create|write|debug|make|remove|rename|migrate|support|finish|test)\b", re.I)
PATH_RE = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w-][\w.-]*\.(?:py|js|ts|tsx|go|rs|java|rb|md|json|toml|ya?ml|cfg|ini|sh|sql|txt))(?![\w/])")
MANIFEST_KIND = {"pyproject.toml": "python", "requirements.txt": "python", "setup.py": "python", "package.json": "node",
                 "go.mod": "go", "Cargo.toml": "rust", "pom.xml": "java", "Gemfile": "ruby"}


def classify(prompt):
    p = (prompt or "").strip()
    if RESUME_RE.match(p) and len(p) < 80:
        return "resume"
    if CODING_RE.search(p) and len(p) >= 40:
        return "coding"
    return "simple"


def preflight(root, prompt, max_files=80):
    """Deterministic, cheap repository facts. No content scan, no tests, no network, no secret files."""
    g = evidence.git_identity(root)
    files = evidence.project_files(root)
    if not files:
        return ""
    kinds = sorted({k for m, k in MANIFEST_KIND.items() if (Path(root) / m).is_file()})
    lines = ["Repository facts (ROSS preflight):"]
    if g:
        lines.append(f"git {g['branch']} @ {g['sha']}; " + (f"uncommitted: {', '.join(g['dirty'][:15])}" if g["dirty"] else "clean"))
    if kinds:
        lines.append("project type: " + ", ".join(kinds))
    shown = files[:max_files]
    lines.append(f"{len(files)} files: " + " ".join(shown) + (f" ... (+{len(files) - max_files})" if len(files) > max_files else ""))
    named = [m.group(1) for m in PATH_RE.finditer(prompt or "")]
    missing = [n for n in named if not any(f == n or f.endswith("/" + n) for f in files)]
    if missing:
        lines.append("named but not found: " + ", ".join(missing[:10]))
    return "\n".join(lines)


def first_message(prompt, blocks):
    """Dynamic suffix: context blocks first, then the user's request, as one user turn."""
    parts = [b for b in blocks if b]
    return "\n\n".join(parts + [prompt]) if parts else prompt


def cache_plan(caps, explicit):
    """Where caching goes. Provider-native automatic caching is the competent default; the ROSS policy adds an explicit
    breakpoint at the end of the stable prefix so new sessions reuse it, plus a rolling breakpoint on the newest block."""
    if caps.prompt_caching == "none":
        return {"mode": "none"}
    if explicit and "explicit" in caps.prompt_caching:
        return {"mode": "explicit", "stable_ttl": "5m", "rolling": True}
    return {"mode": "auto"}


def should_compact(context_tokens, cached_prefix_tokens, expected_future_calls, read_rate, write_rate, compaction_cost_tokens):
    """Compaction only when it pays: future savings on re-reads must exceed rewriting the cache plus the compaction itself."""
    removable = max(0, context_tokens - cached_prefix_tokens)
    saving = removable * read_rate * expected_future_calls
    cost = (context_tokens - removable) * write_rate + compaction_cost_tokens * write_rate
    return saving > cost
