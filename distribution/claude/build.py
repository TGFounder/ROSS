#!/usr/bin/env python3
"""Generate and verify the Claude plugin runtime from canonical ROSS.

The Claude distribution is a thin packaging layer. Every runtime file under
ross/skills/ross/ is a byte-for-byte copy of the accepted canonical source and
is never edited by hand.

  build.py build   copy the locked runtime files from the canonical source
  build.py check   fail if the packaged runtime differs from the lock or source
"""

import hashlib
from pathlib import Path
import shutil
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLUGIN = HERE / "ross"
RUNTIME = PLUGIN / "skills" / "ross"
LOCK = HERE / "runtime.lock"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_lock() -> tuple[dict[str, str], dict[str, str]]:
    header: dict[str, str] = {}
    files: dict[str, str] = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        if "=" in line and "  " not in line:
            key, value = line.split("=", 1)
            header[key] = value
            continue
        digest, relative = line.split("  ", 1)
        item = Path(relative)
        if item.is_absolute() or ".." in item.parts or relative in files:
            raise SystemExit(f"FAIL: unsafe or duplicate lock entry: {relative}")
        files[relative] = digest
    if header.get("version") != "1.0.0" or not files:
        raise SystemExit("FAIL: runtime.lock is missing its version or file list")
    return header, files


def check() -> None:
    _, files = read_lock()
    problems: list[str] = []
    for relative, digest in files.items():
        source = ROOT / relative
        packaged = RUNTIME / relative
        if not source.is_file() or source.is_symlink():
            problems.append(f"canonical file missing: {relative}")
        elif sha256(source) != digest:
            problems.append(f"canonical file differs from accepted v1.0.0: {relative}")
        if not packaged.is_file() or packaged.is_symlink():
            problems.append(f"packaged file missing: {relative}")
        elif sha256(packaged) != digest:
            problems.append(f"packaged file differs from accepted v1.0.0: {relative}")
    actual = {p.relative_to(RUNTIME).as_posix() for p in RUNTIME.rglob("*") if p.is_file()}
    for extra in sorted(actual - set(files)):
        problems.append(f"unexpected packaged runtime file: {extra}")
    if (PLUGIN / "LICENSE").read_bytes() != (ROOT / "LICENSE").read_bytes():
        problems.append("plugin LICENSE differs from canonical LICENSE")
    for forbidden in (".mcp.json", "hooks", "bin", "agents", "commands", ".lsp.json", "settings.json"):
        if (PLUGIN / forbidden).exists():
            problems.append(f"skills-only plugin contains {forbidden}")
    if problems:
        raise SystemExit("FAIL: Claude distribution drift\n  " + "\n  ".join(problems))
    print(f"PASS: Claude plugin runtime matches canonical ROSS v1.0.0 ({len(files)} files)")


def build() -> None:
    _, files = read_lock()
    if RUNTIME.exists():
        shutil.rmtree(RUNTIME)
    for relative in files:
        target = RUNTIME / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    shutil.copyfile(ROOT / "LICENSE", PLUGIN / "LICENSE")
    check()


if __name__ == "__main__":
    if sys.argv[1:] == ["build"]:
        build()
    elif sys.argv[1:] == ["check"]:
        check()
    else:
        raise SystemExit("usage: build.py build|check")
