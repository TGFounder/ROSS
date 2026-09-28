# Matched benchmark

This benchmark compares a baseline agent with a ROSS-governed agent on the same
six deterministic decision tasks. The domains are software work, current-fact
research, document creation, connected-system work, long-context continuation,
and a consequential governance change.

The benchmark measures policy-decision correctness, unauthorized-action and
false-completion flags, and observable run proxies. It does not claim to measure
general intelligence or production reliability. See [`methodology.md`](methodology.md),
[`tasks.json`](tasks.json), and the committed candidate results in `results/`.

The original task set and results remain the v1 audit record. The independently
reviewed calibration is versioned separately in [`tasks-v2.json`](tasks-v2.json)
and [`methodology-v2.md`](methodology-v2.md); it does not rewrite v1 evidence.

No cost or credit estimate is reported unless the runner exposes it. Results
that do not favor ROSS remain in the report.
