#!/usr/bin/env python3
"""Dependency-free structural, public-safety, profile, and eval validation."""

import hashlib
import json
from pathlib import Path
import re
import struct
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
AUTHORIZED_PUBLIC_CONTACT = "rahul@trustgraphed.com"
ACCEPTED_RUNTIME_SHA = "5e54f13cb143e9e5c43996a0ce01a55577ca4cd9"
ACCEPTED_RUNTIME_SUMS_SHA256 = "64c1274177503f98c8d038daa170f882074370d5f0f813f0407fdc40d42c0ee8"


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
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"LICENSE", "NOTICE", "RELEASE", "SHA256SUMS"}:
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
        relative = path.relative_to(ROOT)
        immutable_plugin_runtime = relative.parts[:5] == (
            "distribution", "openai", "ross", "skills", "ross"
        )
        if path.suffix.lower() == ".md" and not immutable_plugin_runtime:
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
        if relative.parts[:2] in {("tests", "fixtures"), ("benchmarks", "fixtures")}:
            continue
        public_contact_removed = text.replace(AUTHORIZED_PUBLIC_CONTACT, "")
        for label, pattern in PRIVATE_PATTERNS.items():
            if pattern.search(public_contact_removed):
                fail(f"{label} found in public file: {relative}")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                fail(f"{label} found in public file: {relative}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_openai_distribution() -> None:
    notice = (
        "ROSS — Reliable Operating Super Skill\n"
        "Copyright 2026 TRUSTGRAPHED SYSTEMS PRIVATE LIMITED\n"
        "Contact: rahul@trustgraphed.com\n"
        "Licensed under the Apache License, Version 2.0.\n"
    )
    if (ROOT / "NOTICE").read_text(encoding="utf-8") != notice:
        fail("repository NOTICE does not match the accepted attribution")

    plugin = ROOT / "distribution" / "openai" / "ross"
    if (plugin / "NOTICE").read_text(encoding="utf-8") != notice:
        fail("plugin NOTICE does not match the accepted attribution")
    if any((plugin / name).exists() for name in ("mcp.json", ".mcp.json", ".app.json")):
        fail("skills-only plugin contains MCP or app configuration")

    manifest = json.loads((plugin / "plugin.json").read_text(encoding="utf-8"))
    if manifest.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
        fail("plugin manifest uses an unsupported portable schema")
    if manifest.get("name") != "ross" or manifest.get("version") != "1.0.0":
        fail("plugin name or version does not match ROSS v1.0.0")
    if manifest.get("license") != "Apache-2.0":
        fail("plugin license must be Apache-2.0")
    author = manifest.get("author")
    if not isinstance(author, dict) or author != {
        "name": "TRUSTGRAPHED SYSTEMS PRIVATE LIMITED",
        "email": AUTHORIZED_PUBLIC_CONTACT,
        "url": "https://trustgraphed.com",
    }:
        fail("plugin author metadata is inconsistent")
    interface = manifest.get("extensions", {}).get("com.openai", {}).get("interface")
    if not isinstance(interface, dict):
        fail("plugin OpenAI interface metadata is missing")
    single_line_limits = {
        "displayName": 30,
        "shortDescription": 30,
        "developerName": 80,
    }
    for field, limit in single_line_limits.items():
        value = interface.get(field)
        if not isinstance(value, str) or not value or "\n" in value or len(value) > limit:
            fail(f"plugin interface {field} violates the directory limit")
    long_description = interface.get("longDescription")
    if not isinstance(long_description, str) or not long_description or len(long_description) > 4000:
        fail("plugin long description violates the directory limit")
    valid_categories = {
        "Productivity", "Creativity", "Developer Tools", "Business & Operations",
        "Data & Analytics", "Communication", "Education & Research", "Security",
        "Finance", "Healthcare", "Travel", "Entertainment", "Other",
    }
    if interface.get("category") not in valid_categories:
        fail("plugin category is not supported")
    prompts = interface.get("defaultPrompt")
    if not isinstance(prompts, list) or not 1 <= len(prompts) <= 3:
        fail("plugin must provide one to three starter prompts")
    normalized_prompts = {" ".join(prompt.split()) for prompt in prompts if isinstance(prompt, str)}
    if len(normalized_prompts) != len(prompts) or any(
        not isinstance(prompt, str) or not prompt or len(prompt) > 128 or "\n" in prompt or "@" in prompt
        for prompt in prompts
    ):
        fail("plugin starter prompts violate directory limits")
    if "screenshots" in interface or "apps" in manifest or "mcpServers" in manifest:
        fail("skills-only plugin declares an excluded capability")

    for field in ("composerIcon", "logo"):
        value = interface.get(field)
        if not isinstance(value, str) or not value.startswith("./") or ".." in Path(value).parts:
            fail(f"plugin {field} path is unsafe")
        asset = plugin / value[2:]
        data = asset.read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
            fail(f"plugin {field} is not a readable PNG")
        width, height = struct.unpack(">II", data[16:24])
        if width != height or not 48 <= width <= 4096:
            fail(f"plugin {field} dimensions are invalid")

    runtime = plugin / "skills" / "ross"
    release = runtime / "RELEASE"
    expected_release = f"version=1.0.0\ntag=v1.0.0\nsha={ACCEPTED_RUNTIME_SHA}\n"
    if release.read_text(encoding="utf-8") != expected_release:
        fail("plugin runtime release identity is not the accepted v1.0.0 commit")
    sums_path = runtime / "SHA256SUMS"
    if sha256(sums_path) != ACCEPTED_RUNTIME_SUMS_SHA256:
        fail("plugin runtime checksum manifest differs from the published release")
    listed: set[str] = set()
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            fail("plugin runtime checksum manifest is malformed")
        digest, relative = match.groups()
        item = Path(relative)
        if item.is_absolute() or ".." in item.parts or relative in listed:
            fail("plugin runtime checksum manifest contains an unsafe path")
        candidate = runtime / item
        if not candidate.is_file() or candidate.is_symlink() or sha256(candidate) != digest:
            fail(f"plugin runtime integrity failed: {relative}")
        listed.add(relative)
    actual = {
        path.relative_to(runtime).as_posix()
        for path in runtime.rglob("*")
        if path.is_file()
    }
    if actual != listed | {"SHA256SUMS"}:
        fail("plugin runtime contains a missing or unexpected file")

    cases = json.loads(
        (ROOT / "distribution" / "openai" / "portal" / "test-cases.json").read_text(encoding="utf-8")
    )
    if set(cases) != {"positive", "negative"} or len(cases["positive"]) != 5 or len(cases["negative"]) != 3:
        fail("submission tests must contain five positive and three negative cases")
    all_cases = cases["positive"] + cases["negative"]
    if len({case.get("id") for case in all_cases}) != 8:
        fail("submission test case IDs must be unique")
    required_positive = {"id", "prompt", "expected_behavior", "expected_result_shape", "fixture_data"}
    required_negative = {"id", "prompt", "expected_behavior", "why_not"}
    if any(set(case) != required_positive for case in cases["positive"]):
        fail("positive submission test case shape is invalid")
    if any(set(case) != required_negative for case in cases["negative"]):
        fail("negative submission test case shape is invalid")


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
        validate_openai_distribution()
        validate_profile()
        validate_runtime_manifest()
        count = validate_evals()
        print(f"PASS: frontmatter, links, structure, whitespace, privacy, secrets, OpenAI distribution, profile, runtime manifest, {count} eval cases")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
