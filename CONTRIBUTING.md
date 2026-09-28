# Contributing

Keep proposals small, general, and evidence-backed. Discuss material behavioral
or compatibility changes before implementing them. A pull request should state
the observed need, exact scope, tests run, security and compatibility effects,
and any unresolved limitation.

Run `python3 tests/validate_repo.py` and the applicable lifecycle tests. Do not
include generated archives, local profiles, credentials, absolute personal
paths, benchmark scratch data, or unrelated formatting changes.

Behavioral changes are candidates. They require evaluation, independent review,
and explicit acceptance under [`GOVERNANCE.md`](GOVERNANCE.md); a merged pull
request alone does not self-authorize a release or installation.
