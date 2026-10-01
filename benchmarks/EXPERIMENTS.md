# ROSS experiment ledger

Institutional memory: what was tried, what it measured, and whether it was kept.
Primary KPI: cost and provider-reported model resource per successful task, with
equal or better success, quality and security. Track A = host plugin, Track B =
orchestrated (API). Results from the two tracks are never combined.

| # | Track | Experiment | Hypothesis | Result | Decision |
|---|---|---|---|---|---|
| 1 | A | v1.1.0 runtime candidate (`4497770`) | delta state, read and test reuse cut rework | −3.3% tokens, +39% turns, protections never fired | superseded |
| 2 | A | v1.2.0 efficiency engine (`a7affe4`) | automatic memory, exec-wrapper output compression, resume block | −20.6% tokens, −21.7% calls, −10.5% cost, 6/6 vs 6/6; resume −29.6% tokens | **KEEP: host-mode champion** |
| 3 | A | v1.3.0 engine v2 (`9ba2daf`) | progressive hydration, shell-read dedup, grouped test output, nudges | +10.2% tokens, +18.9% cost, +5.9% calls on raw totals; Session A +6.8% tokens; continuity 6/6 vs 4/6 | **REVERT** (economics regressed; continuity gain noted) |
| 4 | A | host-CLI orchestration (`08d8bf9`, preserved branch `candidate/ross-orchestration-runtime`) | replacing the host system prompt and tool set via headless flags removes most of the 29.3K-token prefix | not measured (usage limit hit before the first probe) | not promoted; candidate idea for a future host-mode challenger |
| 5 | B | orchestrator v0.1 (`candidate/ross-orchestrator-v0.1`) | ROSS owning inference (small stable prefix, memory, reduction, preflight, stop policy) halves cost per success against a competent same-model baseline | **not yet run**: no Anthropic API key in the build environment | pending live smoke |

## Lessons carried forward

- About 80% of host-mode tokens (36% of cost) is the host's fixed prefix
  re-read on every call (29,294 tokens on Claude Code 2.1.286). A plugin
  cannot change it; the champion already averages 3 calls per session, so the
  plugin-only ceiling is roughly 30% tokens and 20% cost.
- Context injected at session start is re-read on every later call; it pays
  only when it removes a call (experiment 3).
- Never compress output the agent explicitly asked to read; it causes re-reads
  (defect found in experiment 3, present in the champion).
- A baseline that does no work is not an equivalent completion; report
  continuity success and equivalent-completion economics separately.
- `num_turns` in Claude Code counts parallel tool results; count distinct model
  calls instead.
