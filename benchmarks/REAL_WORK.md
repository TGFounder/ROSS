# ROSS Reality Bench: three real coding tasks (candidate)

This is a **small, free, reproducible real-work benchmark**, not a claim that
ROSS has improved coding outcomes. It is deliberately separate from the
six hypothetical policy questions in the original benchmark.

Task list: [real-work-tasks.json](real-work-tasks.json). Verifier and disposable
workspace generator: [real_tasks.py](real_tasks.py).

## What is measured

| Task | Required result | Separate regression tests |
| --- | --- | --- |
| csv-parser | Quoted commas, escaped quotes and blank rows work | Four checks |
| idempotent-send | Same request sends only once; errors remain retryable | Four checks |
| currency-rounding | Exact half-up monetary rounding with valid inputs | Five checks |

Each task includes an unrelated user-edited file that must survive unchanged.
**No external email, payment, server or network access is required.**
Acceptance tests stay outside the generated workspace. The local CI confirms
that original starter code fails and a correct implementation passes. Those
reference fixes are test fixtures, **not model benchmark results**.

## Run a matched A/B comparison

Generate a randomized, reproducible plan:

```sh
python3 benchmarks/field.py plan \
  --tasks benchmarks/real-work-tasks.json \
  --repeats 3 --seed 20261010 --output trial-plan.json
```

For each planned trial, create a **new isolated workspace**:

```sh
python3 benchmarks/real_tasks.py prepare \
  --task csv-parser --workspace /path/to/disposable/unique-trial
```

Give the coding agent **only the generated workspace and TASK.md**, not the
repository with withheld verification tests. Use the task and test ordering in
the pre-registered plan, preserving the seed. Baseline: do not load ROSS.
ROSS condition: activate the exact accepted version explicitly and verify the
host activation through a native trace. Don't infer activation merely because
the agent says so. Keep the **same model, version, reasoning level, isolation,
timeout, permissions and resource cap** for each paired comparison.

After the agent stops, independently check its completed workspace:

```sh
python3 benchmarks/real_tasks.py verify \
  --task csv-parser --workspace /path/to/disposable/unique-trial \
  --output /path/to/private-evidence/verification.json
```

**Safety:** Verification imports and runs code written by the agent. Python's
`-I` flag and a shortened environment are NOT a security sandbox. Run trials
only inside a disposable container/VM without secrets, host files, network
access, privileged accounts or production credentials. The verifier uses a
15-second wall-time timeout, not a CPU or memory quota. Use the outer sandbox
for all resource and security limits. Do not execute unknown agent code on a
personal computer or GitHub Actions runner without isolation.

Store independent verifier outputs and native skill-loading traces outside the
agent workspace. Apply the plan/observation format of
[FIELD.md](FIELD.md) with the verifier's `passed` result and evidence reference;
verify any unauthorized actions and false-completion claims separately using
real host logs. The field-trial reporter requires checked evidence files
and explicitly reported activation, and does **not** certify their semantics.

## Publication gate

Do not claim ROSS improves outcomes until repeated **real model** runs exist
on both conditions, with all outputs retained (including failures), matching
settings, validated activation, independent review of traces, and complete cost
measurements when available. Include negative and neutral findings.

If no coding-agent CLI is installed, **STOP at prepared fixtures**. Do not
substitute authored example fixes, simulated transcripts or CI itself for model
runs. The benchmark suite is zero-cost until an external model is deliberately
invoked, which requires separate spend authority.

## Local regression check

```sh
python3 -m unittest discover -s tests -p 'test_real_tasks.py'
```

The candidate does not change ROSS's skill instructions, installed runtime
manifest, accepted release or host settings.
