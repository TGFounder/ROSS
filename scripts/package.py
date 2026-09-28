#!/usr/bin/env python3
"""Build a deterministic ROSS release archive from an exact checkout."""

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import zipfile


VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def die(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def frontmatter_version(skill: Path) -> str:
    text = skill.read_text(encoding="utf-8")
    match = re.search(r'^  version: "([^"]+)"$', text, re.MULTILINE)
    if not match:
        die("SKILL.md metadata.version is missing")
    return match.group(1)


def runtime_paths(source: Path) -> list[PurePosixPath]:
    manifest = source / "release" / "runtime-files.txt"
    if not manifest.is_file():
        die("release/runtime-files.txt is missing")
    paths: list[PurePosixPath] = []
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        item = PurePosixPath(value)
        if item.is_absolute() or ".." in item.parts or str(item) != value:
            die(f"unsafe runtime path: {value}")
        if item in paths:
            die(f"duplicate runtime path: {value}")
        paths.append(item)
    return sorted(paths, key=str)


def assert_clean(source: Path) -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=source,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    if result.stdout:
        die("checkout is dirty; commit the candidate before packaging")


def assert_commit(source: Path, expected_sha: str) -> None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    if result.stdout.strip().lower() != expected_sha:
        die("sha does not match the source checkout HEAD")


def zip_entry(archive: zipfile.ZipFile, name: str, data: bytes, mode: int) -> None:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.create_system = 3
    info.external_attr = (mode & 0xFFFF) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("dist"))
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    version = args.version
    commit_sha = args.sha.lower()
    if not VERSION_RE.fullmatch(version):
        die("version must use X.Y.Z")
    if not SHA_RE.fullmatch(commit_sha):
        die("sha must be a full 40-character hexadecimal commit SHA")
    if frontmatter_version(source / "SKILL.md") != version:
        die("version does not match SKILL.md metadata.version")
    assert_clean(source)
    assert_commit(source, commit_sha)

    paths = runtime_paths(source)
    for item in paths:
        candidate = source.joinpath(*item.parts)
        if not candidate.is_file() or candidate.is_symlink():
            die(f"runtime file is missing or is a symlink: {item}")
        parent = candidate.parent
        while parent != source:
            if parent.is_symlink():
                die(f"runtime path crosses a symlink: {item}")
            parent = parent.parent

    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / f"ross-v{version}.zip"
    checksum_path = output / f"ross-v{version}.zip.sha256"
    with tempfile.TemporaryDirectory(prefix="ross-package-") as temporary:
        root = Path(temporary) / "ross"
        root.mkdir()
        for item in paths:
            destination = root.joinpath(*item.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source.joinpath(*item.parts), destination)

        release = root / "RELEASE"
        release.write_text(
            f"version={version}\ntag=v{version}\nsha={commit_sha}\n",
            encoding="utf-8",
        )
        payload = paths + [PurePosixPath("RELEASE")]
        sums = "".join(
            f"{sha256(root.joinpath(*item.parts))}  {item}\n" for item in sorted(payload, key=str)
        )
        (root / "SHA256SUMS").write_text(sums, encoding="utf-8")

        entries = [PurePosixPath("RELEASE"), PurePosixPath("SHA256SUMS")] + paths
        directories = {PurePosixPath("ross")}
        for item in entries:
            parent = PurePosixPath("ross") / item.parent
            while str(parent) not in (".", ""):
                directories.add(parent)
                if parent == PurePosixPath("ross"):
                    break
                parent = parent.parent

        with zipfile.ZipFile(archive_path, "w") as archive:
            for directory in sorted(directories, key=str):
                zip_entry(archive, f"{directory}/", b"", 0o40755)
            for item in sorted(entries, key=str):
                mode = 0o100755 if item == PurePosixPath("scripts/ross.sh") else 0o100644
                zip_entry(archive, f"ross/{item}", root.joinpath(*item.parts).read_bytes(), mode)

    archive_hash = sha256(archive_path)
    checksum_path.write_text(
        f"{archive_hash}  {archive_path.name}\n", encoding="utf-8"
    )
    print(f"PASS: {archive_path}")
    print(f"SHA256: {archive_hash}")


if __name__ == "__main__":
    main()
