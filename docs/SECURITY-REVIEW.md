# Public-release security review

Scope: POSIX and PowerShell lifecycle utilities, release packaging, profile
handling, CI dependencies, public content, and the ROSS trust model.

## Resolved findings

1. **Unexpected empty-directory deletion:** verification originally enumerated
   only files, so an untracked empty directory could pass verification and be
   removed with the runtime during uninstall. Both implementations now compare
   the complete expected and actual file-and-directory sets. POSIX and Windows
   regression tests cover this case.
2. **Dirty-source release identity:** a test-only packaging option originally
   allowed a dirty tree to claim a supplied commit SHA. The option was removed.
   Packaging now always requires a clean checkout and exact `HEAD`/SHA match.

## Reviewed controls

- target must be absolute, end in `ross`, have a non-root existing parent, and
  cross no symlink or Windows reparse point;
- source and every copied path reject symlinks/reparse points;
- manifest paths reject absolute paths, parent traversal, duplicates, and the
  manifest itself;
- file hashes and the complete file/directory set are verified before install,
  after staging, and after replacement;
- update and rollback require an explicitly selected local accepted source and
  restore the prior runtime if replacement verification fails;
- uninstall refuses a changed or ambiguous directory and selects only the exact
  `ross` target;
- lifecycle utilities do not fetch content, evaluate manifest text, or execute
  package files;
- profiles reject unknown fields and free-form instructions, remain untrusted
  preferences, and cannot grant authority;
- CI actions and the official reference validator are pinned to immutable
  commits; runtime utilities add no third-party dependency;
- public validation scans for common secrets, private profile markers, and
  personal absolute paths.

## Residual boundaries

ROSS cannot establish the trustworthiness of the channel from which an archive
was obtained. Users must verify the separately published archive checksum and
accepted tag/commit. Behavioral instructions do not replace OS permissions,
sandboxing, identity, authorization, tenant isolation, or application controls.

No unresolved material finding remains in the reviewed candidate code. Final
Windows and Linux claims still depend on the final candidate CI commit passing,
not only the earlier checkpoint.
