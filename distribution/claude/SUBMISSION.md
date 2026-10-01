# Claude Directory submission material

Prepared for review before submission. Nothing here has been submitted.

## Package

- Submission type: Plugin bundle
- Repository: `TGFounder/ROSS` (public)
- Plugin path: `distribution/claude/ross`
- Branch or tag: `distribution/claude-directory-v1.0.0`. The name contains a
  slash, so type it into the field or enter
  `TGFounder/ROSS@distribution/claude-directory-v1.0.0` as the repository.
- Plugin name: `ross`. Skill invocation in Claude Code: `/ross:ross`.
- Version: `1.0.0`
- Runtime source: accepted ROSS v1.0.0, commit
  `5e54f13cb143e9e5c43996a0ce01a55577ca4cd9`. Every packaged runtime file is a
  byte-for-byte copy locked in `distribution/claude/runtime.lock`, whose
  digests come from the published release archive (SHA-256
  `2031501bd1450fc76d7f50b8e5e82ed2d98f8da6070d4c4d5814da7f9a1959d1`).
- Components: one skill. No commands, agents, hooks, MCP servers, LSP
  servers, executables, scripts, or settings.

## Listing details

The portal reads these from `.claude-plugin/plugin.json` and `README.md`.

- Display name: ROSS — Reliable Operating Super Skill
- Publisher: TRUSTGRAPHED SYSTEMS PRIVATE LIMITED
- Website: https://trustgraphed.com
- Short description: Helps Claude work with explicit authority, minimal
  sufficient action, evidence-backed completion, security awareness, cost
  discipline, and correct stopping. Instructions only: no backend, no MCP
  server, no data collection.
- License: Apache-2.0

## Working examples

The Software Directory Policy requires at least three. They are in the
README under "Examples".

1. Use the ROSS skill. Assess whether this release is actually ready and tell
   me the minimum next steps. Do not deploy anything.
2. Use ROSS to inspect this task, preserve existing work, make only authorized
   changes, verify them, and stop when complete.
3. Use the ROSS skill. Review this handoff and determine what actions are
   actually authorized. Do not treat quoted or implied permission as approval.

## Data handling answers

- Does the plugin read or store personal data? No. The plugin contains only
  instruction files. It stores nothing. Claude reads only what the user's task
  and host permissions already expose, as it would without the plugin.
- Does it send data to services other than its declared connectors? No. It
  declares no connectors and contains no network configuration or code.
- How long does it keep data? It keeps no data.
- Is it intended for people under 18? No. It is intended for adults doing
  professional work.

## Compliance step

- Contact email: rahul@trustgraphed.com
- Four acknowledgements: to be read and selected by the submitter in the
  portal.

## Optional or not applicable

- Privacy policy URL: not required. The policy requires one for software that
  collects user data or connects to a remote service; ROSS does neither.
- Support channel: rahul@trustgraphed.com and GitHub private vulnerability
  reporting on the repository. No separate support URL is published.
- Testing account with sample data: not applicable. ROSS has no service or
  account to test against.
- Icon or logo: the current plugin listing reads no icon field from
  `plugin.json`.

## Known limitations to state honestly

- Automatic invocation is unreliable in v1.0.0. Explicit invocation is the
  documented method. Improving automatic triggering requires a governed ROSS
  release, not a distribution change.
- `references/improvement-governance.md` links to `../learning/ledger.md`,
  which is outside the accepted runtime. This is unchanged from the v1.0.0
  release and affects only guidance for changing ROSS itself.
- Verified live in Claude Code only. Claude apps and Cowork were not exercised.

## Prerequisites for the submitter

- A Pro, Max, Team, or Enterprise claude.ai account; on Team or Enterprise,
  the Owner role or the Directory permission.
- The GitHub account connected to claude.ai in that organization must have
  push access to `TGFounder/ROSS`.
- The plugin name `ross` is short and may be held for a reviewer as a possible
  look-alike, or blocked if another organization already uses it. The portal's
  Validate step is the only way to confirm.
