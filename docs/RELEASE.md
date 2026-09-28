# Release process

1. Start from the accepted tag and develop on an isolated candidate branch.
2. Validate the skill, profiles, links, privacy, lifecycle utilities, evals, and
   reproducible packaging.
3. Run the matched benchmark and focused security review; preserve raw evidence.
4. Obtain independent review of the exact diff and evidence.
5. After explicit acceptance only, merge the accepted commit and tag `vX.Y.Z`.
6. Build twice from that exact commit with:

   ```sh
   python3 scripts/package.py --version X.Y.Z --sha COMMIT_SHA --output dist
   ```

7. Confirm byte-identical archives and publish only the ZIP, its `.sha256`
   checksum, and concise release notes.
8. Clean-install from the published artifact, verify identity and contents, run
   representative activation and negative-activation checks, then uninstall.

The packaging utility refuses a dirty checkout by default, a non-40-character
SHA, symlinks, missing runtime files, or a version mismatch with `SKILL.md`.
Generated archives belong in `dist/` and are not committed.
