# ROSS v1.1.0 candidate: review package

Status: **CANDIDATE — AWAITING INDEPENDENT REVIEW AND FOUNDER ACCEPTANCE.**
Not accepted, not released. `v1.0.0` (5e54f13) is untouched.

## Architecture

- **Kernel:** `SKILL.md` body about 600 tokens (v1.0.0: about 1,440). Conditional
  rules stay in `references/`, loaded only when relevant.
- **Runtime:** `runtime/ross.py`, one standard-library file, no network imports.
  State in `<project>/.ross/` (0700/0600, git-ignored): `state.json` (semantic
  state, delta-written), `deltas.jsonl`, `checkpoints.jsonl` (written only on
  change), `reads.json` (content hashes), `commands.json` (test result +
  inputs fingerprint), `failures.json`, `metrics.jsonl`, `sessions.json`
  (provider-reported usage from the host transcript).
- **Hooks:** SessionStart (rules digest + budgeted state), PreToolUse (refuse
  same-session unchanged reread; refuse passing test on identical inputs;
  refuse third identical failure), PostToolUse/Failure (record), Stop and
  SessionEnd (usage, derived checkpoint). One handler for Claude Code and
  Codex (same JSON protocol).
- **Packaging:** `distribution/build.py` generates `distribution/claude/ross`
  and `distribution/openai/ross` from canonical files and fails on drift.

## Verification

- 14 runtime unit tests: restart persistence, delta-only writes, budgeted
  hydration, reread refusal and change invalidation, test reuse and
  invalidation, failed tests never reused, failure-loop stop, secret
  redaction, permissions, forget, gitignore, hook robustness, no network
  imports. 4 package tests (Claude and OpenAI manifest, skill and hooks
  conformance; kernel size; reference resolution). Repository validator,
  `claude plugin validate --strict`: pass.
- Live Claude Code smoke: all four mechanisms fired as designed.

## Matched acceptance test (Claude Code, Sonnet 5.5, provider-reported usage)

Three-task chains, each task in a fresh session on the same evolving repo
(3 chains per condition), plus a short Q&A task (3 runs). Quality judged by
hidden acceptance tests plus the full visible suite.

| Metric (9 sessions) | Base | ROSS v1.1 skill-invoked | ROSS v1.1 hooks-first (committed) |
|---|---|---|---|
| Tasks passed | 9/9 | 9/9 | 9/9 |
| Total tokens | 1,715,496 | 1,784,674 (+4.0%) | 1,659,253 (**−3.3%**) |
| Cost (USD) | 0.916 | 0.840 (−8.4%) | 0.828 (−9.6%) |
| Turns | 74 | 89 (+20%) | 103 (+39%) |
| Shell/test executions | 27 | 13 (**−52%**) | 13 (**−52%**) |
| Short task tokens / cost | 206,624 / 0.109 | +0.4% / +1.8% | +1.2% / +6.9% |

- **50% token and cost target: NOT achieved.** Achieved about 3% fewer tokens.
  The cost difference is within noise (one baseline session cost 2.7x the
  others).
- 93% of tokens were host cache reads of its own per-turn prefix; total cost
  tracks turn count, and these sessions contained little rediscovery waste.
- The runtime's refusals did not trigger in the acceptance runs (agents did
  not reread unchanged files or rerun passing tests); the agents recorded no
  semantic notes, so later sessions were hydrated with derived state only.

## OpenAI

Static package conformance against current OpenAI plugin documentation:
pass. **OPENAI LIVE ECONOMICS TEST PENDING AUTHORIZATION.** No OpenAI claim is
made from Claude results.

## Privacy

Local only. No network requests, telemetry, accounts or extra model calls.
Reads project files only to hash them and the host transcript only to total
token usage. Stores no conversation, file content or command output; redacts
common secret formats. `forget --project` / `--everything` delete state.

## Unresolved risks

1. The headline savings target is unmet; the mechanisms work but the tested
   workload had little of the waste they remove.
2. Turn count rose; the digest or kernel may prompt extra checking turns.
3. The `# ross:rerun` override can be used by an agent to bypass refusals.
4. Hooks call `python3`; Windows needs `python3` on PATH.
5. A whole-tree fingerprint can invalidate test reuse on unrelated edits
   (safe, but reduces reuse); very large repos skip fingerprinting.
6. Codex hooks and the OpenAI package are untested live.

## Smallest next steps

1. Independent review of this candidate.
2. Measure on genuinely long sessions (30+ turns, repeated test loops,
   multi-day resumes) where rereads and reruns actually occur.
3. Reduce turn overhead: make state recording automatic at session end
   instead of agent-invoked.
