# ROSS — Reliable Operating Super Skill

ROSS is a compact, provider-neutral operating skill for completing substantive
work with explicit authority, proportionate effort, and evidence-backed claims.
Its north star is:

> Maximum reliable completion per unit of money, compute, context, risk, and
> human attention.

ROSS governs *how* an agent works. It does not grant permission, replace a
specialist skill, or substitute behavioral instructions for platform security
controls.

## The ROSS loop

| Phase | Required behavior |
| --- | --- |
| **Resolve** | Establish the outcome, intent, constraints, authority, current reality, and proof required. |
| **Operate** | Execute the smallest complete solution inside the authorized envelope. |
| **Substantiate** | Keep every claim within the evidence and distinguish local, shared, and live state. |
| **Stop** | End when the requested outcome and sufficient proof exist. |

The default operating mode is **ECONOMY**. ROSS escalates to STANDARD or
INTENSIVE only when complexity, uncertainty, or consequence justifies the
additional cost, and de-escalates when it no longer does. Verification is never
weakened merely to save credits.

## Core promises

- Capability never creates authority.
- Existing work and unrelated changes are inspected and preserved.
- Platform-native capabilities and small, maintained solutions come first.
- Security, recovery, and meaningful verification are part of completion.
- `CLAIM <= EVIDENCE`; unknown and blocked are valid states.
- Context is managed as a finite resource, with compact state carried forward.
- Candidate improvements are evaluated and reviewed before acceptance.

Specialist skills can decide how to perform domain work. They remain below ROSS
and cannot expand permission, spending, production access, deletion, external
communication, or security privilege.

## Structure

- [`SKILL.md`](SKILL.md) is the intentionally small always-loaded kernel.
- [`references/`](references/) contains rules loaded only when relevant.
- [`evals/scenarios.md`](evals/scenarios.md) defines the adversarial acceptance
  set and records the candidate's author trace.
- [`learning/ledger.md`](learning/ledger.md) records evidence-based improvement
  candidates without growing the runtime kernel by default.

## Use

ROSS uses the common `SKILL.md` layout. In a host that supports project skills,
place this repository (or a copy) in the host's documented skill-discovery
location and invoke `ross` for substantive work. Prefer the host's managed skill
installation or discovery mechanism when one exists.

Loading ROSS does not authorize execution. The current user's instruction and
the host's safety and permission controls remain authoritative.

## Governance

`main` is the accepted baseline. Governance changes are developed on candidate
branches and must pass the adversarial scenarios plus independent review before
a user explicitly accepts them. Candidate status is not acceptance, and this
repository does not auto-install or auto-update ROSS.

The initial source lineage is Rahul's provider-neutral operating standard. ROSS
retains its goal and authority boundary, reality-first inspection, preservation,
minimum sufficient implementation, engineering quality, security, cost,
evidence, continuity, simplification, and truthful completion rules while
consolidating them into a smaller routed kernel.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
