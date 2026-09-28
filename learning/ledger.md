# Improvement ledger

This append-only decision record stores meaningful ROSS experiments outside the
always-loaded kernel. Valid dispositions are **CANDIDATE**, **ACCEPTED**, and
**REJECTED**. Only explicit user acceptance after independent review can produce
**ACCEPTED**.

## Candidate 0.1 — progressive ROSS kernel

- **Observation:** the source operating standard contains strong authority,
  preservation, quality, cost, security, evidence, continuity, and completion
  rules, but loading all detailed guidance for every task would create a
  recurring context cost.
- **Hypothesis:** a constitutional ROSS loop with deterministic routing can
  preserve those protections while loading deeper rules only when relevant.
- **Candidate:** compact `SKILL.md`, five routed references, one adversarial
  scenario table, and this ledger.
- **Evaluation:** author trace passes 14/14 scenarios in
  `evals/scenarios.md`; frontmatter, structure, whitespace, and relative-link
  validation passed on 2026-09-28.
- **Tradeoff:** routing requires an extra read for consequential work, avoiding
  a larger cost on simple invocations.
- **Independent review:** the original 12 scenarios passed, but review found two
  material objections: ambiguity between DRAFT content generation and external
  persistence, and the absence of an explicit governance-isolation requirement.
  The candidate remained unmerged and unaccepted.
- **Corrective patch:** clarified the DRAFT persistence boundary, required
  isolated governance staging and an exact baseline diff, and added scenarios
  13 and 14 for re-review.
- **Independent re-review:** confirmed the original two objections were resolved,
  but found one residual routing-level ambiguity because the DRAFT persistence
  rule existed only in an optionally loaded reference.
- **Kernel correction:** moved the essential DRAFT persistence boundary into the
  always-loaded `SKILL.md`.
- **Final independent review:** **PASS** — no remaining material objections.
- **Acceptance:** explicitly accepted by the user as ROSS v0.1 on 2026-09-28.
- **Disposition:** **ACCEPTED** — v0.1 baseline authorized for merge, tag, and
  installation by explicit user instruction.

## Entry template

```text
Date and candidate commit:
Observation and evidence:
Hypothesis:
Candidate change:
Evaluation and regressions:
Context/compute/security tradeoff:
Independent reviewer and objections:
Disposition and accepting authority:
```
