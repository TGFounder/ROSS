# ROSS Privacy Policy

Effective date: 1 October 2026

This policy covers the ROSS (Reliable Operating Super Skill) plugin published
by TRUSTGRAPHED SYSTEMS PRIVATE LIMITED ("TrustGraphed", "we") through
Anthropic's Claude directory and at https://github.com/TGFounder/ROSS.

## What ROSS is

ROSS is a set of written instructions plus a small local runtime (one
standard-library Python file) that the host runs through hooks. This policy
covers the v1.1.0 candidate.

## What ROSS collects

ROSS sends nothing anywhere. It has no telemetry, makes no network requests,
creates no accounts and calls no additional model.

On your own machine, in `<project>/.ross/` (private file permissions,
git-ignored), it stores compact working state: goals, decisions, constraints,
blockers and next actions that the agent records; content fingerprints of
files that were read; pass or fail results of commands with the fingerprint
they ran against; and token counts totalled from the host's local session
transcript. It does not store conversations, file contents or command output,
and it redacts common secret formats before writing. You can inspect it with
`ross status` and delete it with `ross forget --project` or
`ross forget --everything`.

Your conversations, files and tool results otherwise stay within your AI host
and are handled under that provider's terms, not by TrustGraphed.

## What we may receive

- **Directory usage figures.** Anthropic's developer portal shows publishers
  statistics about a published plugin, such as install counts, versions in
  use, how often its skill runs, and error rates. We use these only to
  understand adoption and reliability. We do not receive your conversation
  content or files through ROSS.
- **Support messages.** If you email us or open a GitHub issue, we receive what
  you send, including your email address or GitHub username. We use it only to
  respond to you and to improve ROSS. GitHub's privacy policy governs data you
  submit on GitHub.

We do not sell personal data or use it for advertising.

## Retention

We keep support correspondence only as long as needed to resolve your request
and maintain a record of it. ROSS retains no data.

## Your choices

You can stop using ROSS at any time by disabling or uninstalling the plugin.
To ask about, correct, or delete support correspondence we hold, email
rahul@trustgraphed.com.

## Children

ROSS is intended for adults doing professional work and is not directed at
people under 18.

## Changes

We will update this file and its effective date if our practices change.

## Contact

TRUSTGRAPHED SYSTEMS PRIVATE LIMITED
Email: rahul@trustgraphed.com
Website: https://trustgraphed.com
