"""Fingerprints that durable facts are valid against. Git is the source of truth for source history."""
import hashlib
import os
import platform
import subprocess
import sys
from pathlib import Path

from .models import FpKind

MAX_FILES = 4000
MAX_BYTES = 64 * 1024 * 1024
MANIFESTS = ("requirements.txt", "pyproject.toml", "poetry.lock", "package.json", "package-lock.json", "pnpm-lock.yaml",
             "yarn.lock", "go.mod", "go.sum", "Cargo.toml", "Cargo.lock", "Gemfile.lock")


def git(root, *args):
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10)
        return r.stdout.rstrip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def project_files(root):
    files = git(root, "ls-files", "-co", "--exclude-standard").splitlines()
    if not files:
        files = [str(p.relative_to(root)) for p in Path(root).rglob("*") if p.is_file() and ".git" not in p.parts]
    return [f for f in sorted(files) if not f.startswith(".ross/") and "__pycache__" not in f and not f.endswith(".pyc")]


def inputs_hash(root):
    """Hash of every tracked and untracked non-ignored file; None when too large to fingerprint (never reuse then)."""
    h, total = hashlib.sha256(), 0
    for rel in project_files(root)[:MAX_FILES]:
        p = Path(root) / rel
        try:
            total += p.stat().st_size
        except OSError:
            continue
        if total > MAX_BYTES:
            return None
        h.update(rel.encode() + b"\0" + file_hash(p).encode())
    return h.hexdigest()[:16]


def env_identity(root):
    h = hashlib.sha256(f"{sys.version}|{platform.platform()}".encode())
    for m in MANIFESTS:
        p = Path(root) / m
        if p.is_file():
            h.update(m.encode() + file_hash(p).encode())
    return h.hexdigest()[:16]


def current(root, kind, subject=""):
    """Current fingerprint for a kind/subject, or None if it cannot be established (treated as stale)."""
    kind = FpKind(kind)
    if kind is FpKind.CONTENT:
        p = Path(root) / subject
        return file_hash(p) if p.is_file() else None
    if kind is FpKind.INPUTS:
        return inputs_hash(root)
    if kind is FpKind.COMMIT:
        return git(root, "rev-parse", "HEAD") or None
    if kind is FpKind.ENV:
        return env_identity(root)
    return None


def git_identity(root):
    sha = git(root, "rev-parse", "--short", "HEAD")
    if not sha:
        return {}
    dirty = [l[3:] for l in git(root, "status", "--porcelain", "--untracked-files=all").splitlines()
             if len(l) > 3 and not l[3:].startswith(".ross") and "__pycache__" not in l]
    return {"branch": git(root, "rev-parse", "--abbrev-ref", "HEAD"), "sha": sha, "dirty": dirty}


def project_root(start=None):
    start = Path(start or os.getcwd()).resolve()
    top = git(start, "rev-parse", "--show-toplevel")
    return Path(top) if top else start
