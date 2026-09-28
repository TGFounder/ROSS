# Compatibility

Status meanings:

- **VERIFIED** — exercised in the named environment with recorded evidence.
- **EXPECTED FROM STANDARD** — conforms to the open Agent Skills format but was
  not exercised in that host.
- **UNTESTED** — no current execution evidence.
- **UNSUPPORTED** — intentionally outside scope.

| Surface | Status | Evidence or limit |
| --- | --- | --- |
| Open Agent Skills directory format | EXPECTED FROM STANDARD | Standard frontmatter and one-level relative references; reference validator is part of the release gate. |
| Local Codex | VERIFIED | Accepted v0.1.0 discovery and invocation were verified; the v1.0 candidate is tested only in a clean temporary skill root until acceptance. |
| macOS lifecycle utility | VERIFIED | POSIX lifecycle and clean-room tests run on macOS. |
| Linux lifecycle utility | UNTESTED | CI is configured for Ubuntu; status becomes VERIFIED only after a passing hosted run. |
| Windows PowerShell lifecycle utility | UNTESTED | CI is configured for Windows; no local PowerShell runtime is assumed. |
| OpenAI Agent Skills-compatible API/sandbox | UNTESTED | Requires an accessible environment that supports skill installation and invocation. |
| ChatGPT native Skills installation | UNTESTED | Availability depends on the connected account and supported product surface. |
| Other Agent Skills hosts | EXPECTED FROM STANDARD | Host-specific discovery, permissions, and tool behavior must be tested separately. |
| Automatic remote update | UNSUPPORTED | ROSS never fetches or trusts arbitrary `main`; users select an accepted release explicitly. |

Candidate results must not be represented as accepted runtime compatibility.
