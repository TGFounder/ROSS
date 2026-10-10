# ROSS Activation Candidate v0

ROSS can be present on disk and still never activate. A host must discover the
skill metadata, the model must choose it, and any consent steps must succeed.
None of those facts follows from the existence of `SKILL.md`.

## What this candidate changes

- Sharper **candidate** `SKILL.md` description with concrete work types and explicit
  exclusions. Accepted `main` and released v1.0.0 remain untouched.
- Read-only `activation.py doctor` for likely user/workspace skill directories.
- A versioned corpus with explicit-invocation, implicit-invocation and negative
  controls. Repeatable shuffled plans and conservative results.
- No API, paid usage, host settings modifications, hooks, or unconditional
  prompt injection. It does not secretly force skills into every conversation.

## 1. Check installation layout (read-only)

```sh
python3 benchmarks/activation.py doctor --host codex
python3 benchmarks/activation.py doctor --host claude
python3 benchmarks/activation.py doctor --host gemini
```

Use `--home` and `--workspace` to inspect specific test roots.

A `found-on-disk` result **does not prove** that the host discovered,
activated, or followed ROSS. Multiple skills with the same name may shadow one
another. Restart or reload the host as appropriate and confirm which version
is active.

Host-specific cross-checks:

- **Codex:** Inspect the skills list in a new session and explicitly invoke
  `$ross` first. Implicit activation depends on description matching; the
  host may truncate long descriptions if many skills are available.
- **Claude Code:** Confirm the skill appears among available skills and
  explicitly request ROSS before testing automatic discovery. Do not infer
  activation from an assistant's statement alone.
- **Gemini CLI:** Use `/skills list` and `/skills reload`. When the agent
  selects a skill through `activate_skill`, consent may be required. Declined
  consent is not an activation success.

Host documentation and available trace formats change. Verify all instructions
against the installed host version. This tool reports candidate filesystem
locations, not a definitive host registry.

## 2. Measure trigger behavior (separate host runs)

```sh
python3 benchmarks/activation.py plan \
  --cases benchmarks/activation-cases.json \
  --host claude --repeats 3 --seed 20261010 \
  --output activation-plan.json
```

Run each case in a **new clean session** in a disposable, isolated environment.
Keep model, version, permissions, installed skills and other conditions equal.
Do not put a global "always use ROSS" rule in the trial environment: that would
make *implicit* activation results meaningless.

Use the plan's trial IDs to create `observations.json`:

```json
[
  {
    "trial_id": "implicit-repair--1",
    "outcome": "activated",
    "trace": "sessions/implicit-repair-1.jsonl"
  }
]
```

The above is a **format example, not a measured result**. Record every run,
including failures. `outcome` is `activated`, `not-activated`, or `unknown`.
Use `unknown` when a host trace cannot establish what actually happened.
Outcomes must be reviewed against native host events: an agent saying "I used
ROSS" is insufficient. For Gemini, tool selection without successful consent
or skill loading is not equivalent to activation. For Codex, just reading a
file isn't automatically proof of the intended skill routing. Distinguish
explicit and implicit successes and count negative-control false positives.

```sh
python3 benchmarks/activation.py score \
  --cases benchmarks/activation-cases.json \
  --plan activation-plan.json \
  --observations observations.json \
  --trace-root ./local-traces \
  --output activation-report.json
```

The score reports recall of triggers and negative controls separately.
References are checked for safe relative paths, regular files and hashed
bytes. Raw trace contents are neither inspected nor uploaded.

- `incomplete`: some planned observations missing
- `inconclusive`: some outcomes unknown
- `evidence-unverified`: traces not locally checked
- `activation-regression`: operator-recorded false positives/negatives
- `operator-reported-pass`: recorded expectations pass with trace files present;
  **not** a certification of activation

The scorer is intentionally strict: **a declared outcome plus a hash is not a
validated host trace**. An independent reviewer must inspect each native
trace, validate actual skill loading, and verify compatibility/version.
An external, consented host run is still required to establish activation
reliability. Never publish synthetic fixture outcomes as real-world results.

Run baseline and candidate metadata under identical host conditions. Report
both missed triggers and unwanted invocations, as well as execution-quality
and token costs, before proposing acceptance. Do not merge or install a
candidate merely because offline tests passed.

## Local checks

```sh
python3 -m unittest discover -s tests -p 'test_activation.py'
```

Relevant external documentation:
- https://developers.openai.com/blog/eval-skills
- https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/skills.md
