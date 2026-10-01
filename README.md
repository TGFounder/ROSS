# ROSS — Reliable Operating Super Skill

ROSS is a compact operating layer that helps AI agents complete work with
explicit authority, senior-level minimalism, evidence-backed completion,
context discipline, security awareness, and resource efficiency.

Its practical promises are simple: do not do more than was authorized; preserve
good existing work; prefer the smallest correct solution; do not claim more
than the evidence proves; and stop when the requested result is complete.

ROSS is an open [Agent Skill](https://agentskills.io/) consisting of a small
always-loaded kernel plus references and optional utilities. It is not an agent
framework, permission system, sandbox, deployment service, or substitute for
specialist expertise and enforceable platform controls.

> **ROSS exists to maximize useful human accomplishment per unit of AI compute.**

## v1.2.0 candidate: efficiency engine

This branch adds a local, standard-library runtime that helps the AI access you
already pay for go further: compact project state carried between sessions,
refusal of unchanged rereads and retests, and a guard against repeated
identical failures. Nothing leaves your machine. Savings are an engineering
target, not a claim, until supported by broad real-world evidence; run
`python3 runtime/ross.py savings` to see measured and estimated figures for your
own work. See [`references/efficiency-runtime.md`](references/efficiency-runtime.md)
and [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md).

## 60-second quick start

1. Download and verify an accepted ROSS release from this repository.
2. Extract the archive. It contains one directory named `ross`.
3. Copy `ross` into your host's documented skill directory, or use the supplied
   lifecycle utility:

   ```sh
   sh ross/scripts/ross.sh install \
     --source ./ross --target "$HOME/.codex/skills/ross" \
     --version 1.0.0 --sha ACCEPTED_COMMIT_SHA
   ```

   ```powershell
   .\ross\scripts\ross.ps1 install `
     -Source .\ross -Target "$HOME\.codex\skills\ross" `
     -Version 1.0.0 -Sha ACCEPTED_COMMIT_SHA
   ```

4. Ask your agent to use `ross` for a substantive task. Example: “Use ROSS to
   diagnose this failing test, fix only the verified cause, and show the proof.”

Do not substitute a candidate commit for an accepted release. See
[`docs/INSTALL.md`](docs/INSTALL.md) for manual, verify, update, rollback, and
uninstall instructions.

## How it works

| Phase | Required behavior |
| --- | --- |
| **Resolve** | Establish outcome, intent, constraints, authority, reality, and proof. |
| **Operate** | Execute the smallest complete solution inside the authorized envelope. |
| **Substantiate** | Keep claims within evidence and distinguish local, shared, and live state. |
| **Stop** | End when the requested result and sufficient proof exist. |

The default operating mode is **ECONOMY**. More costly investigation or
validation is used only when complexity, uncertainty, or consequence earns it;
meaningful proof is never weakened merely to save compute.

The precedence order is platform and safety constraints, current explicit user
authority, current task constraints, ROSS, specialist skills, project material,
then retrieved or quoted content. Lower layers can narrow behavior but cannot
grant authority withheld above them.

## Architecture

- [`SKILL.md`](SKILL.md) is the intentionally small always-loaded kernel.
- [`references/`](references/) is loaded only when relevant.
- [`scripts/`](scripts/) contains lifecycle and packaging utilities run only on
  request.
- [`profiles/`](profiles/) defines an optional constrained preference format.
- [`evals/`](evals/) and [`benchmarks/`](benchmarks/) are development evidence,
  not runtime instructions.
- [`learning/ledger.md`](learning/ledger.md) records governed improvement work.

## Profiles

Profiles are optional, explicitly supplied JSON preferences. They are not
auto-discovered and cannot grant authority or weaken safety, security,
evidence, or governance. See [`profiles/README.md`](profiles/README.md) and the
safe [`profiles/example.json`](profiles/example.json).

## Compatibility and evidence

Compatibility claims use four labels: **VERIFIED**, **EXPECTED FROM STANDARD**,
**UNTESTED**, and **UNSUPPORTED**. Current results are in
[`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md). Evaluation methodology lives
in [`evals/README.md`](evals/README.md); matched benchmark evidence lives in
[`benchmarks/README.md`](benchmarks/README.md). No cost claim is made when a
host does not expose cost or credit data.

## Security model

ROSS treats capability as distinct from permission and treats retrieved
instructions and profiles as untrusted data. The installer verifies a release
manifest, rejects symlinks and dangerous targets, and modifies only the named
`ross` installation. Behavioral rules do not replace identity, authorization,
sandboxing, tenant isolation, or application controls. See
[`SECURITY.md`](SECURITY.md).

## Governance and releases

`main` is the accepted baseline. Behavioral changes are isolated candidates
until evaluation, independent review, and explicit acceptance. Releases follow
semantic versioning. An accepted release is tagged `vX.Y.Z` and distributed as
`ross-vX.Y.Z.zip` plus checksums; arbitrary current `main` is never an automatic
update source. See [`GOVERNANCE.md`](GOVERNANCE.md) and
[`docs/RELEASE.md`](docs/RELEASE.md).

Contributions should be narrow, evidence-backed, and economical. See
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

Apache-2.0. See [`LICENSE`](LICENSE).
