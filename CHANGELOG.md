# Changelog

## 1.1.0 — candidate (not accepted)

ROSS exists to maximize useful human accomplishment per unit of AI compute.

- Shrink the always-loaded kernel from about 1,440 to about 600 body tokens;
  conditional rules stay behind references loaded only when relevant.
- Add a local, standard-library efficiency runtime (`runtime/ross.py`):
  delta-only operational state, budgeted context hydration, same-session
  duplicate-read refusal, test reuse keyed to an inputs fingerprint, a
  repeated-failure guard, provider-reported usage from host transcripts,
  inspect and forget commands, and secret redaction. No network access.
- One hook handler serves Claude Code and Codex; `distribution/build.py`
  generates both host packages from canonical source and fails on drift.
- Savings are an engineering target until supported by broad evidence.

Status: CANDIDATE — AWAITING INDEPENDENT REVIEW AND FOUNDER ACCEPTANCE.

## 1.0.0 — 2026-09-29

- Add standard-compatible public metadata and an optional constrained profile.
- Add secure macOS/Linux and Windows lifecycle utilities.
- Add reproducible ZIP packaging and checksum manifests.
- Add deterministic evaluation fixtures, matched benchmark evidence, public
  security guidance, compatibility status, and lightweight CI.

Accepted by explicit user instruction after independent re-review passed with
no remaining material objections.

## 0.1.0 — 2026-09-28

- Add the compact ROSS kernel and progressive reference routing.
- Define deterministic authority precedence and completion states.
- Add ECONOMY-first compute, context, testing, and stop discipline.
- Add structural security and evidence requirements.
- Add adversarial scenarios and a controlled improvement ledger.
- Close independently reviewed DRAFT-persistence and governance-staging findings.

Accepted by explicit user instruction after independent review.
