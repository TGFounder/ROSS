# v1.3.0 candidate matched acceptance

- `shipq_fixture.py`: workload (repository, prompts, hidden acceptance tests).
- `acceptance3.py`: runner. Needs `ACC_ROOT`, `ACC_CFG` (isolated Claude config
  dir), `ROSS_PLUGIN` (path to `distribution/claude/ross`). Usage:
  `python3 acceptance3.py REPS WORKERS chain,short`.
- `results.jsonl`: the single matched run reported in
  `docs/REVIEW-v1.3.0-candidate.md` (final agent messages removed).
- `analyse3.py results.jsonl`: recomputes every figure in the review.
- `inputs.sha256`: hashes of the evaluated runtime, kernel, runner and fixture.
