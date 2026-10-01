#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/ross-posix.XXXXXX")
TMP_ROOT=$(cd "$TMP_ROOT" && pwd -P)
trap 'rm -rf "$TMP_ROOT"' EXIT HUP INT TERM
VERSION=1.2.0
SHA=$(git -C "$ROOT" rev-parse HEAD)

python3 "$ROOT/scripts/package.py" --source "$ROOT" --output "$TMP_ROOT/one" --version "$VERSION" --sha "$SHA" >/dev/null
python3 "$ROOT/scripts/package.py" --source "$ROOT" --output "$TMP_ROOT/two" --version "$VERSION" --sha "$SHA" >/dev/null
cmp "$TMP_ROOT/one/ross-v$VERSION.zip" "$TMP_ROOT/two/ross-v$VERSION.zip"

mkdir "$TMP_ROOT/extracted" "$TMP_ROOT/skills"
unzip -q "$TMP_ROOT/one/ross-v$VERSION.zip" -d "$TMP_ROOT/extracted"
[ -f "$TMP_ROOT/extracted/ross/SKILL.md" ]
[ "$(find "$TMP_ROOT/extracted" -mindepth 1 -maxdepth 1 -type d -print | wc -l | tr -d ' ')" -eq 1 ]

printf '%s\n' keep >"$TMP_ROOT/skills/unrelated.txt"
LIFECYCLE=$TMP_ROOT/extracted/ross/scripts/ross.sh
TARGET=$TMP_ROOT/skills/ross
sh "$LIFECYCLE" install --source "$TMP_ROOT/extracted/ross" --target "$TARGET" --version "$VERSION" --sha "$SHA" >/dev/null
sh "$LIFECYCLE" verify --target "$TARGET" --version "$VERSION" --sha "$SHA" >/dev/null

if sh "$LIFECYCLE" install --source "$TMP_ROOT/extracted/ross" --target "$TARGET" --version "$VERSION" --sha "$SHA" >/dev/null 2>&1; then
  printf '%s\n' 'existing installation was overwritten' >&2
  exit 1
fi

printf '%s\n' tampered >>"$TARGET/SKILL.md"
if sh "$LIFECYCLE" verify --target "$TARGET" --version "$VERSION" --sha "$SHA" >/dev/null 2>&1; then
  printf '%s\n' 'changed file was not detected' >&2
  exit 1
fi
cp "$TMP_ROOT/extracted/ross/SKILL.md" "$TARGET/SKILL.md"
printf '%s\n' extra >"$TARGET/EXTRA"
if sh "$LIFECYCLE" verify --target "$TARGET" --version "$VERSION" --sha "$SHA" >/dev/null 2>&1; then
  printf '%s\n' 'unexpected file was not detected' >&2
  exit 1
fi
rm "$TARGET/EXTRA"
mkdir "$TARGET/EMPTY"
if sh "$LIFECYCLE" verify --target "$TARGET" --version "$VERSION" --sha "$SHA" >/dev/null 2>&1; then
  printf '%s\n' 'unexpected empty directory was not detected' >&2
  exit 1
fi
rmdir "$TARGET/EMPTY"

sh "$LIFECYCLE" update --source "$TMP_ROOT/extracted/ross" --target "$TARGET" --version "$VERSION" --sha "$SHA" >/dev/null
sh "$LIFECYCLE" rollback --source "$TMP_ROOT/extracted/ross" --target "$TARGET" --version "$VERSION" --sha "$SHA" >/dev/null

cp -R "$TMP_ROOT/extracted/ross" "$TMP_ROOT/linked-source"
ln -s "$TMP_ROOT/skills/unrelated.txt" "$TMP_ROOT/linked-source/bad-link"
if sh "$LIFECYCLE" update --source "$TMP_ROOT/linked-source" --target "$TARGET" --version "$VERSION" --sha "$SHA" >/dev/null 2>&1; then
  printf '%s\n' 'symlink source was accepted' >&2
  exit 1
fi
if sh "$LIFECYCLE" verify --target "$TMP_ROOT/skills/not-ross" --version "$VERSION" --sha "$SHA" >/dev/null 2>&1; then
  printf '%s\n' 'ambiguous target was accepted' >&2
  exit 1
fi

sh "$LIFECYCLE" uninstall --target "$TARGET" --version "$VERSION" --sha "$SHA" >/dev/null
[ ! -e "$TARGET" ]
[ "$(sed -n '1p' "$TMP_ROOT/skills/unrelated.txt")" = keep ]
printf '%s\n' 'PASS: reproducible package; install, verify, file/directory mismatch, update, rollback, symlink, target, and uninstall isolation'
