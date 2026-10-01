"""Small, stable tool surface. Identical schemas and implementations for every profile; the profile only changes how much
of a result enters context. Every call passes the security gate first."""
import os
import re
import subprocess
from pathlib import Path

from ..core.evidence import file_hash, project_files
from ..core.redact import redact
from ..core.security import injection_notice
from .reduce import reduce_output

SCHEMAS = [  # order and bytes are part of the cacheable prefix: never reorder or edit casually
    {"name": "inspect", "description": "Read a file (optionally a line range), search files with a regex, or list files. Paths are relative to the repository root.",
     "schema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "file to read, or directory to list"},
         "start": {"type": "integer"}, "end": {"type": "integer"},
         "grep": {"type": "string", "description": "regex; searches the file at path, or all project files when path is omitted"}}}},
    {"name": "apply_patch", "description": "Edit a file: replace the exact text `old` (must occur once) with `new`; omit `old` to create or overwrite the file with `new`.",
     "schema": {"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}},
                "required": ["path", "new"]}},
    {"name": "run", "description": "Run a non-interactive shell command in the repository root and return its exit code and output. Set final=true only on the last verifying command when your answer is in the same message.",
     "schema": {"type": "object", "properties": {"command": {"type": "string"}, "final": {"type": "boolean"}}, "required": ["command"]}},
    {"name": "artifact", "description": "Retrieve a stored full tool output by id, filtered by regex grep or a line range like 120-180.",
     "schema": {"type": "object", "properties": {"id": {"type": "string"}, "grep": {"type": "string"}, "lines": {"type": "string"}},
                "required": ["id"]}},
]
BASELINE_RUN_CAP = 30000   # chars, head and tail kept: a competent host default
BASELINE_READ_CAP = 2000   # lines per read
LARGE_FILE = 24000         # chars: the ROSS profile shows an outline and the first lines instead


def _numbered(lines, start):
    return "\n".join(f"{i:>5}\t{l}" for i, l in enumerate(lines, start))


def outline(text, suffix):
    if suffix == ".py":
        import ast
        try:
            tree = ast.parse(text)
            return ", ".join(f"{n.name}@{n.lineno}" for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))[:2000]
        except SyntaxError:
            pass
    rx = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:def|class|function|func|fn|interface|struct|enum)\s+([A-Za-z_]\w*)")
    return ", ".join(f"{m.group(1)}@{i}" for i, l in enumerate(text.splitlines(), 1) if (m := rx.match(l)))[:2000]


class Tools:
    def __init__(self, ctx):
        self.ctx = ctx  # session context: root, gate, artifacts, profile, scheduler, telemetry

    def execute(self, name, args):
        """Returns (text, is_error, meta). meta carries exit codes and paths for memory/evidence."""
        fn = getattr(self, "_" + name, None)
        if not fn or name not in {s["name"] for s in SCHEMAS}:
            return f"unknown tool {name}", True, {}
        try:
            return fn(**{k: v for k, v in (args or {}).items() if k in ("path", "start", "end", "grep", "old", "new", "command", "final", "id", "lines")})
        except TypeError as e:
            return f"bad arguments: {e}", True, {}

    # ---------------------------------------------------------------- inspect
    def _inspect(self, path=None, start=None, end=None, grep=None):
        c = self.ctx
        if grep and not path:
            try:
                rx = re.compile(grep)
            except re.error as e:
                return f"bad regex: {e}", True, {}
            hits = []
            for rel in project_files(c.root):
                if not c.gate.check_read(rel).allowed:
                    continue
                try:
                    for i, l in enumerate((c.root / rel).read_text(encoding="utf-8").splitlines(), 1):
                        if rx.search(l):
                            hits.append(f"{rel}:{i}: {l[:200]}")
                except (OSError, UnicodeDecodeError):
                    continue
                if len(hits) > 400:
                    break
            return self._finish("grep " + grep, "\n".join(hits) or "no matches", 0, True, show_exit=False)
        path = path or "."
        d = c.gate.check_read(path)
        if not d.allowed:
            return f"ROSS policy: {d.reason}", True, {}
        real, rel = c.gate.ws.resolve(path)
        p = Path(real)
        if p.is_dir():
            files = [f for f in project_files(c.root) if rel in (".", None) or f.startswith(rel.rstrip("/") + "/")]
            return self._finish("ls " + (rel or path), "\n".join(files[:500]) + (f"\n... {len(files) - 500} more" if len(files) > 500 else ""), 0, True, show_exit=False)
        if not p.is_file():
            return f"no such file: {path}", True, {}
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"{path} is not a UTF-8 text file", True, {}
        lines = text.splitlines()
        if grep:
            try:
                rx = re.compile(grep)
            except re.error as e:
                return f"bad regex: {e}", True, {}
            return "\n".join(f"{i}: {l}" for i, l in enumerate(lines, 1) if rx.search(l)) or "no matches", False, {"path": rel}
        whole = not start and not end
        if whole and c.profile.on("context_selection"):
            dup = c.scheduler.seen_unchanged(rel, file_hash(p))
            if dup:
                return dup, False, {"path": rel}
            if len(text) > LARGE_FILE:
                c.telemetry("large_read_outlined", 1, "COUNTED")
                return (f"[{rel}: {len(text):,} chars, {len(lines)} lines. Outline: {outline(text, p.suffix)}. First 80 lines below; "
                        f"read ranges with start/end.]\n" + _numbered(lines[:80], 1)), False, {"path": rel}
        s, e = max(1, start or 1), min(len(lines), end or len(lines))
        if e - s + 1 > BASELINE_READ_CAP:
            e = s + BASELINE_READ_CAP - 1
        body = redact(_numbered(lines[s - 1:e], s))
        if whole:
            c.scheduler.mark_seen(rel, file_hash(p))
        note = injection_notice(body)
        return body + ("\n" + note if note else ""), False, {"path": rel, "whole": whole}

    # ---------------------------------------------------------------- apply_patch
    def _apply_patch(self, path, new, old=None):
        c = self.ctx
        d = c.gate.check_write(path, whole_file=old is None)
        if not d.allowed:
            return f"ROSS policy: {d.reason}", True, {}
        real, rel = c.gate.ws.resolve(path)
        p = Path(real)
        if old is not None:
            if not p.is_file():
                return f"no such file: {path}", True, {}
            text = p.read_text(encoding="utf-8")
            n = text.count(old)
            if n != 1:
                return f"`old` occurs {n} times in {rel}; it must occur exactly once", True, {}
            p.write_text(text.replace(old, new, 1), encoding="utf-8")
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(new, encoding="utf-8")
        c.scheduler.forget_seen(rel)
        return f"updated {rel}", False, {"path": rel, "changed": True}

    # ---------------------------------------------------------------- run
    def _run(self, command, final=False):
        c = self.ctx
        d = c.gate.check_command(command)
        if not d.allowed:
            return f"ROSS policy: {d.reason} Ask the user if this is really wanted.", True, {}
        reused = c.scheduler.reuse_test(command)
        if reused:
            return reused, False, {"command": command, "exit": 0, "reused": True, "final": final}
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ROSS_API_KEY")}
        env["PYTHONDONTWRITEBYTECODE"] = "1"  # an edit and a run in the same second must never execute stale bytecode
        try:
            p = subprocess.run(command, shell=True, cwd=str(c.root), capture_output=True, text=True, errors="replace", timeout=600,
                               env=env, executable="/bin/bash" if os.path.exists("/bin/bash") else None)
            out, code = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else ""), p.returncode
        except subprocess.TimeoutExpired:
            out, code = "command timed out after 600s", 124
        meta = {"command": command, "exit": code, "final": final}
        text, _, _ = self._finish(command, out, code, d.persist_output)
        c.scheduler.record_run(command, code, out)
        return text, code != 0, meta

    def _finish(self, cmd, out, code, persist, show_exit=True):
        c = self.ctx
        note = injection_notice(out)
        if c.profile.on("tool_output_reduction"):
            aid = c.artifacts.put(out, persist=persist) if len(out) > 3000 else None
            text = reduce_output(cmd, redact(out), code, aid)
            if len(out) > 3000:
                c.telemetry("output_chars_kept_local", len(out) - len(text), "COUNTED")
        else:
            out = redact(out)
            text = out if len(out) <= BASELINE_RUN_CAP else out[:BASELINE_RUN_CAP // 2] + f"\n[... {len(out) - BASELINE_RUN_CAP:,} chars truncated ...]\n" + out[-BASELINE_RUN_CAP // 2:]
        if show_exit:
            text = f"exit code {code}\n{text}"
        return text + ("\n" + note if note else ""), code != 0, {}

    # ---------------------------------------------------------------- artifact
    def _artifact(self, id, grep=None, lines=None):
        return self.ctx.artifacts.get(id, grep=grep, lines=lines), False, {}
