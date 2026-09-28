# Improvement governance

ROSS improves through a controlled loop:

`baseline -> observation -> hypothesis -> candidate -> evaluation -> independent review -> accept or reject`

Optimize behavior, not instruction count. Prefer generalizing, replacing,
consolidating, simplifying, or deleting rules over permanently appending one for
every failure. A candidate that helps one case but adds recurring context or
compute cost must justify that permanent tax.

Record only meaningful experiments in [`../learning/ledger.md`](../learning/ledger.md),
including the observed failure, hypothesis, candidate change, evidence,
tradeoffs, reviewer, and disposition. Record rejections so they are not
repeated. Keep this history outside the runtime kernel.

## Protected governance

Changes to authority, precedence, security, compute discipline, evidence,
completion, or self-governance remain candidates until independently reviewed.
The author cannot be the sole verifier. Independent review receives the goal,
constraints, raw diff, and evidence—not a requested verdict.

A material objection blocks acceptance when it identifies:

- failure of an agreed adversarial scenario;
- weakened or ambiguous authority or precedence;
- weakened security or evidence truthfulness;
- weakened compute, context, or cost discipline without equivalent protection;
- a contradiction likely to produce materially different behavior between
  competent agents.

Resolve objections by evidence. Only explicit user instruction can accept a
candidate into the protected baseline. Candidate evaluation, review, commit, or
push does not itself constitute acceptance, installation, release, or deployment.
