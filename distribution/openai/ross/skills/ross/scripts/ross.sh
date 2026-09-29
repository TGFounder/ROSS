#!/bin/sh
set -u

usage() {
  printf '%s\n' 'usage: ross.sh {install|verify|update|rollback|uninstall} --target ABSOLUTE/ross --version X.Y.Z --sha FULL_SHA [--source EXTRACTED/ross]'
}

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    return 1
  fi
}

assert_identity() {
  identity_root=$1
  expected_version=$2
  expected_sha=$3
  release_file=$identity_root/RELEASE
  [ -f "$release_file" ] && [ ! -L "$release_file" ] || {
    printf '%s\n' 'missing regular RELEASE file' >&2
    return 1
  }
  actual_version=$(sed -n 's/^version=//p' "$release_file")
  actual_tag=$(sed -n 's/^tag=//p' "$release_file")
  actual_sha=$(sed -n 's/^sha=//p' "$release_file")
  [ "$actual_version" = "$expected_version" ] || {
    printf 'version mismatch: expected %s, found %s\n' "$expected_version" "$actual_version" >&2
    return 1
  }
  [ "$actual_tag" = "v$expected_version" ] || {
    printf 'tag mismatch: expected v%s, found %s\n' "$expected_version" "$actual_tag" >&2
    return 1
  }
  [ "$actual_sha" = "$expected_sha" ] || {
    printf 'SHA mismatch: expected %s, found %s\n' "$expected_sha" "$actual_sha" >&2
    return 1
  }
}

verify_root() {
  verify_path=$1
  verify_version=$2
  verify_sha=$3
  [ -d "$verify_path" ] && [ ! -L "$verify_path" ] || {
    printf 'not installed as a regular directory: %s\n' "$verify_path" >&2
    return 1
  }
  if find "$verify_path" -type l -print | grep . >/dev/null 2>&1; then
    printf '%s\n' 'symlink found in ROSS directory' >&2
    return 1
  fi
  assert_identity "$verify_path" "$verify_version" "$verify_sha" || return 1
  manifest=$verify_path/SHA256SUMS
  [ -f "$manifest" ] && [ ! -L "$manifest" ] || {
    printf '%s\n' 'missing regular SHA256SUMS file' >&2
    return 1
  }
  expected=$(mktemp "${TMPDIR:-/tmp}/ross-expected.XXXXXX") || return 1
  actual=$(mktemp "${TMPDIR:-/tmp}/ross-actual.XXXXXX") || {
    rm -f "$expected"
    return 1
  }
  expected_dirs=$(mktemp "${TMPDIR:-/tmp}/ross-dirs.XXXXXX") || {
    rm -f "$expected" "$actual"
    return 1
  }
  manifest_ok=1
  while IFS= read -r line || [ -n "$line" ]; do
    hash=${line%%  *}
    path=${line#*  }
    if ! printf '%s' "$hash" | grep -Eq '^[0-9a-f]{64}$'; then
      printf 'invalid checksum line: %s\n' "$line" >&2
      manifest_ok=0
      break
    fi
    case "$path" in
      ''|/*|../*|*/../*|*/..|*//*|SHA256SUMS)
        printf 'unsafe checksum path: %s\n' "$path" >&2
        manifest_ok=0
        break
        ;;
    esac
    file=$verify_path/$path
    if [ ! -f "$file" ] || [ -L "$file" ]; then
      printf 'missing file: %s\n' "$path" >&2
      manifest_ok=0
      break
    fi
    found=$(hash_file "$file") || {
      printf '%s\n' 'no SHA-256 utility found' >&2
      manifest_ok=0
      break
    }
    if [ "$found" != "$hash" ]; then
      printf 'changed file: %s\n' "$path" >&2
      manifest_ok=0
      break
    fi
    printf '%s\n' "$path" >>"$expected"
  done <"$manifest"
  if [ "$manifest_ok" -eq 1 ]; then
    LC_ALL=C sort "$expected" -o "$expected"
    if [ -n "$(uniq -d "$expected")" ]; then
      printf '%s\n' 'duplicate checksum path' >&2
      manifest_ok=0
    fi
  fi
  if [ "$manifest_ok" -eq 1 ]; then
    while IFS= read -r path; do
      case "$path" in
        */*)
          directory=${path%/*}
          while [ -n "$directory" ]; do
            printf '%s/\n' "$directory" >>"$expected_dirs"
            case "$directory" in
              */*) directory=${directory%/*} ;;
              *) break ;;
            esac
          done
          ;;
      esac
    done <"$expected"
    printf '%s\n' SHA256SUMS >>"$expected"
    cat "$expected_dirs" >>"$expected"
    LC_ALL=C sort -u "$expected" -o "$expected"
    (
      cd "$verify_path" || exit 1
      find . -type f -print | sed 's#^\./##'
      find . -type d ! -name . -print | sed 's#^\./##; s#$#/#'
    ) | LC_ALL=C sort >"$actual"
    if ! diff -u "$expected" "$actual" >/dev/null; then
      printf '%s\n' 'unexpected or missing files or directories:' >&2
      diff -u "$expected" "$actual" >&2 || true
      manifest_ok=0
    fi
  fi
  rm -f "$expected" "$actual" "$expected_dirs"
  [ "$manifest_ok" -eq 1 ] || return 1
  printf 'PASS: %s (v%s %s)\n' "$verify_path" "$verify_version" "$verify_sha"
}

assert_target() {
  case "$TARGET" in
    /*) ;;
    *) fail 'target must be an absolute path' ;;
  esac
  [ "${TARGET##*/}" = ross ] || fail 'target final component must be exactly ross'
  parent=${TARGET%/*}
  [ -n "$parent" ] || parent=/
  [ -d "$parent" ] && [ ! -L "$parent" ] || fail 'target parent must be an existing regular directory'
  logical_parent=$(cd "$parent" && pwd -L) || fail 'cannot resolve target parent'
  physical_parent=$(cd "$parent" && pwd -P) || fail 'cannot resolve target parent'
  [ "$logical_parent" = "$physical_parent" ] || fail 'target path must not cross a symlink'
  [ "$physical_parent" != / ] || fail 'target parent must not be the filesystem root'
  TARGET=$physical_parent/ross
  [ ! -L "$TARGET" ] || fail 'target must not be a symlink'
}

assert_source() {
  [ -n "$SOURCE" ] || fail 'source is required for install, update, and rollback'
  [ -d "$SOURCE" ] && [ ! -L "$SOURCE" ] || fail 'source must be a regular directory'
  logical_source=$(cd "$SOURCE" && pwd -L) || fail 'cannot resolve source'
  physical_source=$(cd "$SOURCE" && pwd -P) || fail 'cannot resolve source'
  [ "$logical_source" = "$physical_source" ] || fail 'source path must not cross a symlink'
  SOURCE=$physical_source
  [ "$SOURCE" != "$TARGET" ] || fail 'source and target must differ'
  verify_root "$SOURCE" "$VERSION" "$SHA" >/dev/null || fail 'source verification failed'
}

replace_target() {
  operation=$1
  assert_source
  stage=$(mktemp -d "$parent/.ross-stage.XXXXXX") || fail 'cannot create staging directory'
  if ! cp -R "$SOURCE/." "$stage/"; then
    rm -rf "$stage"
    fail 'copy to staging failed'
  fi
  if ! verify_root "$stage" "$VERSION" "$SHA" >/dev/null; then
    rm -rf "$stage"
    fail 'staged copy verification failed'
  fi
  if [ "$operation" = install ]; then
    if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
      rm -rf "$stage"
      fail 'ROSS target already exists'
    fi
    mv "$stage" "$TARGET" || {
      rm -rf "$stage"
      fail 'install move failed'
    }
  else
    [ -d "$TARGET" ] && [ ! -L "$TARGET" ] || {
      rm -rf "$stage"
      fail 'existing ROSS installation is required'
    }
    current_version=$(sed -n 's/^version=//p' "$TARGET/RELEASE")
    current_sha=$(sed -n 's/^sha=//p' "$TARGET/RELEASE")
    verify_root "$TARGET" "$current_version" "$current_sha" >/dev/null || {
      rm -rf "$stage"
      fail 'existing installation is not intact'
    }
    backup=$(mktemp -d "$parent/.ross-backup.XXXXXX") || {
      rm -rf "$stage"
      fail 'cannot reserve backup path'
    }
    rmdir "$backup" || {
      rm -rf "$stage" "$backup"
      fail 'cannot prepare backup path'
    }
    mv "$TARGET" "$backup" || {
      rm -rf "$stage"
      fail 'cannot move existing installation to backup'
    }
    if ! mv "$stage" "$TARGET"; then
      mv "$backup" "$TARGET" || true
      rm -rf "$stage"
      fail 'replacement move failed; previous installation restored if possible'
    fi
    if ! verify_root "$TARGET" "$VERSION" "$SHA" >/dev/null; then
      rm -rf "$TARGET"
      mv "$backup" "$TARGET" || true
      fail 'replacement verification failed; previous installation restored if possible'
    fi
    rm -rf "$backup"
  fi
  verify_root "$TARGET" "$VERSION" "$SHA" >/dev/null || fail 'installed runtime verification failed'
  printf 'PASS: %s v%s at %s\n' "$operation" "$VERSION" "$TARGET"
}

[ "$#" -gt 0 ] || {
  usage
  exit 2
}
ACTION=$1
shift
SOURCE=
TARGET=
VERSION=
SHA=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source) [ "$#" -ge 2 ] || fail 'missing --source value'; SOURCE=$2; shift 2 ;;
    --target) [ "$#" -ge 2 ] || fail 'missing --target value'; TARGET=$2; shift 2 ;;
    --version) [ "$#" -ge 2 ] || fail 'missing --version value'; VERSION=$2; shift 2 ;;
    --sha) [ "$#" -ge 2 ] || fail 'missing --sha value'; SHA=$2; shift 2 ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[ -n "$TARGET" ] || fail 'target is required'
printf '%s' "$VERSION" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || fail 'version must use X.Y.Z'
printf '%s' "$SHA" | grep -Eq '^[0-9a-f]{40}$' || fail 'sha must be a full lowercase 40-character hexadecimal commit SHA'
assert_target

case "$ACTION" in
  install|update|rollback) replace_target "$ACTION" ;;
  verify)
    verify_root "$TARGET" "$VERSION" "$SHA" || fail 'verification failed'
    ;;
  uninstall)
    verify_root "$TARGET" "$VERSION" "$SHA" >/dev/null || fail 'refusing to uninstall a changed or ambiguous directory'
    rm -rf "$TARGET" || fail 'uninstall failed'
    printf 'PASS: uninstalled %s; neighboring files were not selected\n' "$TARGET"
    ;;
  *) usage; fail "unknown action: $ACTION" ;;
esac
