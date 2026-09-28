#!/usr/bin/env python3
"""Dependency-free structural, public-safety, profile, and eval validation."""

import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".txt", ".json", ".py", ".sh", ".ps1", ".yml", ".yaml"}
ALLOWED_FRONTMATTER = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
PRIVATE_PATTERNS = {
    "macOS personal path": re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    "Windows personal path": re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\\]+", re.IGNORECASE),
    "private profile marker": re.compile("ra" + "hul", re.IGNORECASE),
}
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
}


def fail(message: str) -> None:
    raise ValueError(message)


def files() -> list[Path]:
    excluded = {".git", "dist", "__pycache__"}
    return sorted(
        path for path in ROOT.rglob("*")
        if path.is_file() and not any(part in excluded for part in path.relative_to(ROOT).parts)
    )


def parse_frontmatter() -> dict:
    lines = (ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        fail("SKILL.md must start with YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("SKILL.md frontmatter is not closed") from error
    values: dict[str, object] = {}
    current = None
    for line in lines[1:end]:
        if line.startswith("  "):
            if current != "metadata" or ":" not in line:
                fail(f"unsupported nested frontmatter: {line}")
            key, value = line.strip().split(":", 1)
            metadata = values.setdefault("metadata", {})
            assert isinstance(metadata, dict)
            metadata[key] = value.strip().strip('"')
        else:
            if ":" not in line:
                fail(f"invalid frontmatter line: {line}")
            current, value = line.split(":", 1)
            if current == "metadata" and not value.strip():
                values[current] = {}
            else:
                values[current] = value.strip().strip('"')
    if set(values) - ALLOWED_FRONTMATTER:
        fail(f"non-standard frontmatter fields: {sorted(set(values) - ALLOWED_FRONTMATTER)}")
    if values.get("name") != "ross":
        fail("frontmatter name must be ross")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(values["name"])):
        fail("frontmatter name violates Agent Skills naming rules")
    description = str(values.get("description", ""))
    if not 1 <= len(description) <= 1024:
        fail("description length is outside 1..1024")
    metadata = values.get("metadata")
    if metadata is not None and (
        not isinstance(metadata, dict)
        or any(not isinstance(key, str) or not isinstance(value, str) for key, value in metadata.items())
    ):
        fail("metadata must map strings to strings")
    if len(lines) > 500:
        fail("SKILL.md exceeds 500 lines")
    return values


def validate_text(all_files: list[Path]) -> None:
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for path in all_files:
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"LICENSE", "RELEASE", "SHA256SUMS"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"non-UTF-8 text file: {path.relative_to(ROOT)}") from error
        if text and not text.endswith("\n"):
            fail(f"missing final newline: {path.relative_to(ROOT)}")
        for number, line in enumerate(text.splitlines(), 1):
            if line.rstrip() != line:
                fail(f"trailing whitespace: {path.relative_to(ROOT)}:{number}")
            if "\t" in line:
                fail(f"tab character: {path.relative_to(ROOT)}:{number}")
        if path.suffix.lower() == ".md":
            for target in link_pattern.findall(text):
                target = target.strip().strip("<>").split("#", 1)[0]
                if not target or re.match(r"^[a-z]+:", target, re.IGNORECASE):
                    continue
                resolved = (path.parent / target).resolve()
                try:
                    resolved.relative_to(ROOT)
                except ValueError:
                    fail(f"link escapes repository: {path.relative_to(ROOT)} -> {target}")
                if not resolved.exists():
                    fail(f"broken relative link: {path.relative_to(ROOT)} -> {target}")
        relative = path.relative_to(ROOT)
        if relative.parts[:2] in {("tests", "fixtures"), ("benchmarks", "fixtures")}:
            continue
        for label, pattern in {**PRIVATE_PATTERNS, **SECRET_PATTERNS}.items():
            if pattern.search(text):
                fail(f"{label} found in public file: {relative}")


def validate_profile() -> None:
    profile = json.loads((ROOT / "profiles" / "example.json").read_text(encoding="utf-8"))
    allowed_top = {"version", "preferences"}
    allowed_preferences = {
        "cost_sensitivity": {"high", "balanced", "low"},
        "autonomy": {"cautious", "balanced", "proactive"},
        "reporting": {"concise", "standard", "detailed"},
        "coding_minimalism": {"strong", "balanced"},
        "preferred_tools": None,
    }
    if set(profile) != allowed_top or profile["version"] != "1":
        fail("example profile top-level structure is invalid")
    preferences = profile["preferences"]
    if not isinstance(preferences, dict) or not preferences or set(preferences) - set(allowed_preferences):
        fail("example profile preferences are invalid")
    for key, value in preferences.items():
        allowed = allowed_preferences[key]
        if allowed is not None and value not in allowed:
            fail(f"invalid example profile value: {key}")
    tools = preferences.get("preferred_tools", [])
    if not isinstance(tools, list) or len(tools) > 12 or len(set(tools)) != len(tools):
        fail("preferred_tools must be a unique array of at most 12 values")
    if any(not isinstance(tool, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,39}", tool) for tool in tools):
        fail("invalid preferred tool name")
    schema = json.loads((ROOT / "profiles" / "profile.schema.json").read_text(encoding="utf-8"))
    if schema.get("additionalProperties") is not False:
        fail("profile schema must reject unknown top-level fields")
    if schema["properties"]["preferences"].get("additionalProperties") is not False:
        fail("profile schema must reject unknown preferences")


def validate_runtime_manifest() -> None:
    manifest = ROOT / "release" / "runtime-files.txt"
    entries = [line for line in manifest.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    if entries != sorted(set(entries)):
        fail("runtime manifest must be sorted and unique")
    required = {"SKILL.md", "LICENSE", "scripts/ross.sh", "scripts/ross.ps1"}
    if not required.issubset(entries):
        fail("runtime manifest omits required runtime files")
    for entry in entries:
        candidate = ROOT / entry
        if Path(entry).is_absolute() or ".." in Path(entry).parts or not candidate.is_file() or candidate.is_symlink():
            fail(f"unsafe or missing runtime manifest entry: {entry}")


def validate_evals() -> int:
    cases = json.loads((ROOT / "evals" / "cases.json").read_text(encoding="utf-8"))
    categories = {case["category"] for case in cases}
    required = {"authority", "engineering", "evidence", "efficiency", "context", "security", "stop", "specialist", "profiles", "lifecycle"}
    if len(cases) < 30 or categories != required or len({case["id"] for case in cases}) != len(cases):
        fail("evaluation corpus coverage or uniqueness failed")
    return len(cases)


def main() -> None:
    try:
        all_files = files()
        parse_frontmatter()
        validate_text(all_files)
        validate_profile()
        validate_runtime_manifest()
        count = validate_evals()
        print(f"PASS: frontmatter, links, structure, whitespace, privacy, secrets, profile, runtime manifest, {count} eval cases")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
