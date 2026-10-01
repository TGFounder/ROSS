# Compatibility

Status meanings:

- **VERIFIED** — exercised in the named environment with recorded evidence.
- **EXPECTED FROM STANDARD** — conforms to the open Agent Skills format but was
  not exercised in that host.
- **UNTESTED** — no current execution evidence.
- **UNSUPPORTED** — intentionally outside scope.

| Surface | Status | Evidence or limit |
| --- | --- | --- |
| Open Agent Skills directory format | VERIFIED | The packaged skill passed the official pinned `skills-ref` validator. |
| Local Codex | VERIFIED | Accepted v0.1.0 discovery and invocation were verified; the v1.0 candidate is tested only in a clean temporary skill root until acceptance. |
| macOS lifecycle utility | VERIFIED | POSIX lifecycle and clean-room tests run on macOS. |
| Linux lifecycle utility | VERIFIED | The Ubuntu lifecycle job passed in the hosted candidate run. |
| Windows PowerShell lifecycle utility | VERIFIED | The Windows PowerShell lifecycle job passed in the hosted candidate run. |
| OpenAI Agent Skills-compatible API/sandbox | UNTESTED | Requires an accessible environment that supports skill installation and invocation. |
| ChatGPT native Skills installation | UNTESTED | Availability depends on the connected account and supported product surface. |
| Other Agent Skills hosts | EXPECTED FROM STANDARD | Host-specific discovery, permissions, and tool behavior must be tested separately. |
| Automatic remote update | UNSUPPORTED | ROSS never fetches or trusts arbitrary `main`; users select an accepted release explicitly. |

Candidate results must not be represented as accepted runtime compatibility.

## v1.1.0 candidate efficiency runtime

| Host | Skill | Runtime hooks | Cross-session state | Status |
|---|---|---|---|---|
| Claude Code | yes | SessionStart, PreToolUse, PostToolUse(+Failure), Stop, SessionEnd | yes, `<project>/.ross/` | VERIFIED (live sessions) |
| Codex CLI / IDE / app | yes | same handler and JSON protocol; file-read reuse not applicable (no Read tool) | yes | EXPECTED FROM SPEC (static package tests; no live OpenAI run) |
| Claude apps, ChatGPT chat | skill rules only | no | no | Degrades to kernel rules |
| OpenAI API (direct) | n/a | n/a | via CLI commands | Not built; no live economics test |

Hooks invoke `python3`; Windows users need `python3` on PATH (or the `py`
launcher alias). The runtime itself is portable and tested on all three OSes
in CI. A pure skill cannot guarantee persistent memory on hosted chat
surfaces.
