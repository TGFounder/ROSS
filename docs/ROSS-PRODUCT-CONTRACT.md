# ROSS product contract

Locked decisions. Later sessions implement these; they do not reinterpret them.
Changing one requires an explicit Founder decision recorded here.

1. **One ROSS core.** State, memory, evidence, security, authority, budget,
   cache economics and telemetry live in one shared core (`ross/core`).
2. **Two execution modes.** Host efficiency mode (plugin inside Claude Code,
   Codex and compatible hosts) and orchestrated mode (ROSS owns the model
   loop). They are siblings over the same core.
3. **Subscription users are first-class.** Host mode serves people who already
   pay for a host; it is never abandoned or made to depend on API credits.
4. **Plugin mode and API orchestration are different things.** Their economics
   are measured and reported separately (Track A host, Track B orchestrated).
   A host-versus-orchestrator difference is never reported as ROSS savings.
5. **Plugin mode never calls a second model to implement ROSS.** No double
   inference.
6. **Orchestrated mode directly owns provider inference** through provider
   adapters (Anthropic API first; OpenAI adapter kept compatible).
7. **Local-first.** Everything runs on the user's machine except the user's
   chosen model API and tools the user explicitly authorizes.
8. **No mandatory cloud backend.** No TrustGraphed service is required.
9. **No transcript-as-memory.** ROSS stores the result of history (goals,
   decisions, constraints, verified evidence, next steps), never transcripts
   or chain-of-thought.
10. **SQLite structured state for orchestrated mode** at `.ross/ross.db`,
    versioned with `PRAGMA user_version`; large content stays in
    `.ross/artifacts/`. The plugin champion keeps its JSON state until a
    migration independently passes its own regression gate.
11. **Provenance and invalidation for durable facts.** Every item records scope,
    type, provenance class (USER_DECISION, USER_CONSTRAINT, DERIVED_STATE,
    VERIFIED_EVIDENCE, MODEL_SUMMARY) and, where applicable, the fingerprint it
    is valid against. Stale facts are never presented as current.
12. **Cache economics are first-class.** Uncached input, cache writes, cache
    reads, output and calls are tracked separately; prompts separate a stable
    prefix from a dynamic suffix; compaction happens only when it pays.
13. **Hard user budgets are first-class.** Spend, calls and output caps are
    enforced locally before every request, from a conservative worst case.
14. **Security and authority are hard constraints.** Enforced in code before
    any tool runs; authority comes only from the user, platform and local
    policy, never from repository, tool or web content, skills or the model.
15. **Provider-specific behavior stays behind adapters** exposing capabilities;
    core logic never branches on provider names.
16. **The core efficiency engine stays open source** (Apache-2.0).
17. **TG OS later consumes ROSS as a library;** TG OS is not built here.
18. **Public 50% claims require actual matched evidence** on representative
    work, with equal or better success, quality and security.
