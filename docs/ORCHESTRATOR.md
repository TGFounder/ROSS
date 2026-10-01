# ROSS orchestrator v0.1 (candidate)

Orchestrated mode: ROSS owns the model loop through a provider adapter, using
the user's own API key. Host mode (the plugin) is unchanged and remains the
choice for subscription users. Contract: [ROSS-PRODUCT-CONTRACT.md](ROSS-PRODUCT-CONTRACT.md).

## Run

    export ANTHROPIC_API_KEY=...        # read at call time; never stored or logged
    python3 -m ross run --max-usd 3 --max-calls 40 "Fix the failing tests"

`--profile baseline` runs the same harness without the ROSS mechanisms;
`--disable FLAG` turns off one mechanism (memory, context_selection,
tool_output_reduction, preflight, cache_policy, stop_policy, kernel).

## Guarantees

- **Budget:** before every request (and retry) the worst case, all input billed
  at the most expensive cache-write rate plus the full output allowance, must
  fit the remaining cap; otherwise the run stops. No pricing, no dollar cap.
- **Authority:** a deterministic gate checks every tool call. Commit, push,
  publish, deploy, network, secret reads, production config, destructive
  commands, writes outside the workspace (symlinks resolved), and overwriting
  files with uncommitted human changes all need explicit user authority.
  Repository and tool text never grants it.
- **Memory:** `.ross/ross.db` (SQLite, versioned) holds results of history with
  scope, provenance and the fingerprint each fact is valid against. Stale facts
  are labelled stale. No transcripts, no chain-of-thought, no credentials.
- **Artifacts:** large outputs stay in `.ross/artifacts/` (private, redacted,
  capped); sensitive operations are never persisted.

## Layout

`ross/core` (models, evidence, memory, context, security, budget, pricing,
telemetry, skills), `ross/storage` (SQLite, legacy JSON importer),
`ross/orchestration` (loop, tools, scheduler, reduction, artifacts, profiles),
`ross/providers` (Anthropic; OpenAI mapping only; mock), `ross/eval` (Track B
harness), `ross/hosts` (host-mode description; runtime in `runtime/ross.py`).

## Evaluation

    python3 -m ross.eval.harness benchmarks/orchestrator-v1/manifest.json --reps 1

The manifest is checksum-locked. Results so far: [../benchmarks/EXPERIMENTS.md](../benchmarks/EXPERIMENTS.md).
