# Installation and lifecycle

Use an accepted release archive and verify its published archive checksum
before extraction. Do not use `curl | sh`. The archive contains one `ross/`
directory with an internal `SHA256SUMS` file and `RELEASE` identity.

## Automated path

On macOS or Linux:

```sh
sh ross/scripts/ross.sh install --source ./ross \
  --target "$HOME/.codex/skills/ross" --version 1.0.0 \
  --sha ACCEPTED_COMMIT_SHA
```

On Windows PowerShell 5.1 or later:

```powershell
.\ross\scripts\ross.ps1 install -Source .\ross `
  -Target "$HOME\.codex\skills\ross" -Version 1.0.0 `
  -Sha ACCEPTED_COMMIT_SHA
```

The target must be an absolute path whose final component is exactly `ross`.
The source and target must not contain symlinks. Installation refuses an
existing target and modifies no neighboring skill.

Use `verify` with the same target, version, and SHA for read-only integrity
checking. It reports missing, changed, and unexpected files and never repairs
them.

Use `update` only with an explicitly selected, extracted accepted release.
`rollback` uses the same verified operation with a previously accepted release;
it does not guess or download a version. Both replace only the `ross` target
transactionally and restore the previous directory if final verification fails.

Use `uninstall` to remove a verified, unmodified ROSS installation. It refuses a
symlink, corrupt manifest, changed file, or unexpected file so unrelated data is
not deleted.

## Manual fallback

After verifying the archive checksum, extract it and independently verify every
entry in `ross/SHA256SUMS`. Confirm `ross/RELEASE` matches the accepted tag and
commit. Copy the complete `ross/` directory to the host's documented skill
location without merging it into an existing directory. Re-run manifest
verification on the copy. Remove only that exact directory to uninstall.

Host discovery paths differ; consult the host's current documentation. An
installed directory does not by itself prove that a host discovered or invoked
the skill.
