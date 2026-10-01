# Execution, quality, and efficiency

## Smallest complete path

Before adding code or structure, ask in order:

1. Is a change needed?
2. Can deletion or simplification solve it?
3. Does the repository already provide it?
4. Does the platform provide it natively?
5. Does a maintained dependency solve it safely and economically?
6. Can configuration solve it?
7. Can a few clear lines solve it?

Only then create a new abstraction, dependency, script, workflow, or service.
Minimal means minimum sufficient surface, not missing security, validation,
failure handling, recovery, tests, evidence, or requested behavior.

For dependencies, weigh fit, maintenance, security, license, adoption, lock-in,
integration, migration, and lifecycle cost against the code and risk avoided. A
small local implementation is preferable when it is clearer and cheaper.

## Operating modes

| Mode | Use when | Behavior |
| --- | --- | --- |
| **ECONOMY** | Default; bounded and reversible work | Narrow reads, one capable path, targeted tools and tests. |
| **STANDARD** | Material uncertainty or moderate consequence | Broader validation and selective specialist help. |
| **INTENSIVE** | High consequence, security, architecture, or difficult ambiguity | Deeper evidence, failure analysis, and independent review. |

Escalation must name the complexity, uncertainty, or consequence that earns the
cost. De-escalate after the hard part. If exact consumption is unavailable, do
not invent it; optimize controllable proxies: context volume, calls, searches,
retries, test runs, generated code, agents, and human review.

Use ordinary conversation when agentic execution adds no material value. Do not
use a skill, tool, model, agent, or paid service merely because it is available.

## Engineering quality

Scale rigor to risk. Protect ownership boundaries, invariants, contracts,
concurrency, idempotency, data lifecycle, compatibility, observability,
operability, and rollback where relevant. Validate at trust boundaries. Keep
secrets out of source, logs, prompts, fixtures, and handoffs.

Prefer:

`targeted test -> targeted iteration -> stable candidate -> required final gate`

Test the happy path, acceptance criteria, and consequential negative paths such
as invalid input, permissions, unavailable dependencies, partial failure,
duplicates, interruption, and recovery. Never weaken meaningful proof to save
credits. Do not repeatedly run a costly full suite when focused checks provide
safe iteration; run the required final gate once the candidate is stable.

For security-sensitive, architectural, costly, data-changing, or production
work, seek independent review when it is available and authorized. Give the
reviewer the goal, constraints, raw change, and evidence rather than the desired
verdict. If independent review is unavailable, perform a separate adversarial
pass and disclose that it was not independent.

After two materially similar failures, stop. Inspect the raw evidence, form a
root-cause hypothesis, and change strategy before another attempt. Do not mask a
failed check behind retries.

## Git and change discipline

Confirm repository, remote, branch, status, and relevant history before edits.
Preserve unrelated work; avoid broad formatting. Keep changes coherent and
reviewable. Never force-push, rewrite shared history, discard changes, or delete
branches or tags without explicit authority. A commit or push proves only
version-control state.

Before handoff, inspect the final diff and delete unnecessary code, files,
dependencies, prose, scaffolds, debug output, and stale comments without
weakening safety or proof. Stop once the requested outcome and evidence exist.

Runtime state, artifacts and savings commands: [`efficiency-runtime.md`](efficiency-runtime.md).
