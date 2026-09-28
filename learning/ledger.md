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
- **Evaluation:** author trace passes 12/12 scenarios in
  `evals/scenarios.md`; frontmatter, structure, whitespace, and relative-link
  validation passed on 2026-09-28.
- **Tradeoff:** routing requires an extra read for consequential work, avoiding
  a larger cost on simple invocations.
- **Independent reviewer:** pending.
- **Disposition:** **CANDIDATE** — not accepted, installed, released, or merged.

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
