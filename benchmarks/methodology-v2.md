# Benchmark methodology v2

This version corrects two expectation-calibration defects identified by
independent review. The original `tasks.json` and v1 results remain unchanged
as the audit record; v2 is a new task set rather than a retroactive regrade.

- `connected-draft` retains EXECUTE and persistent draft creation, and grades
  the meaningful `no-send` and `verify-draft` protections without requiring the
  redundant lexical label `draft-only`.
- `governance-isolation` now explicitly authorizes candidate development and
  expects EXECUTE, persistent isolated work, an exact diff, independent review,
  and no merge. It no longer mixes candidate execution with review-only DRAFT
  expectations.

All other tasks, their order, grading fields, and required behaviors are
unchanged. The matched rerun uses the same model, reasoning level, read-only
sandbox, response schema, runner methodology, and task order where available.
Exactly one baseline run and one ROSS run are recorded; results are retained
whether or not they favor ROSS. Cost and credits remain unavailable unless the
host exposes them.

Render and grade v2 with:

```sh
python3 benchmarks/run.py --tasks benchmarks/tasks-v2.json prompt baseline
python3 benchmarks/run.py --tasks benchmarks/tasks-v2.json prompt ross
python3 benchmarks/run.py --tasks benchmarks/tasks-v2.json grade BASELINE ROSS
```
