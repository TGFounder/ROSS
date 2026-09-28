# Governance

`main` is the accepted ROSS baseline. Develop governance and behavioral changes
on an isolated candidate branch or equivalent staging surface, preserve the
accepted baseline, and review the exact diff against it.

The acceptance sequence is:

`observation -> hypothesis -> candidate -> evaluation -> independent review -> explicit acceptance or rejection`

The author cannot be the sole reviewer. A material objection blocks acceptance
when it identifies an adversarial-scenario failure, weakened authority,
security, evidence or efficiency discipline, or a consequential ambiguity.
Acceptance, merging, tagging, publishing, and installation are distinct actions
and require the authority applicable to each.

Release versioning follows SemVer. Patch releases correct accepted behavior,
minor releases add backward-compatible capability, and major releases may
change public behavior or interfaces. The detailed release procedure is in
[`docs/RELEASE.md`](docs/RELEASE.md).
