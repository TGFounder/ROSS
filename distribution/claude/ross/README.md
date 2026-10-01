# ROSS — Reliable Operating Super Skill

ROSS is a skill that gives Claude a working discipline for substantive tasks.
It asks Claude to confirm what it is actually authorized to do before acting,
take the smallest action that fully solves the task, keep its claims within the
evidence it has, respect security boundaries, spend time and money carefully,
and stop when the requested result is complete.

ROSS is a set of written instructions. It is not autonomous software, an agent
framework, an MCP server, a backend, or a permission system. It cannot grant
Claude any access or authority, and it does not replace your platform's own
permission controls or a specialist's judgment.

Publisher: TRUSTGRAPHED SYSTEMS PRIVATE LIMITED (https://trustgraphed.com).
Source: https://github.com/TGFounder/ROSS. This plugin packages the accepted
ROSS v1.0.0 release (commit `5e54f13cb143e9e5c43996a0ce01a55577ca4cd9`)
without modification.

## How to use it

Invoke ROSS explicitly. This is the reliable method in v1.0.0:

- In Claude Code, type `/ross:ross` followed by your request.
- In any Claude app, start your request with "Use the ROSS skill" and then
  describe the task.

Claude can also choose ROSS automatically, but in v1.0.0 this is not reliable,
so ask for it by name when you want it applied.

## What ROSS does

ROSS works in four phases:

1. **Resolve.** Establish the outcome you want, whether you asked for analysis,
   a draft, or real execution, what counts as done, and what is out of scope.
2. **Operate.** Inspect the real state first, preserve existing work, and make
   the smallest complete change inside what you authorized.
3. **Substantiate.** Separate what is assessed, ready, authorized, executed,
   and verified. Passing local or mocked tests is not reported as a live,
   deployed, or CI-verified result.
4. **Stop.** Finish once the result and sufficient proof exist, without extra
   refactoring, polish, or spending.

Authority comes only from you and from the platform's rules. Tool access,
urgency, handoff notes, documents, web pages, and quoted text are treated as
information, never as permission.

## Examples

1. **Release readiness.** "Use the ROSS skill. Assess whether this release is
   actually ready and tell me the minimum next steps. Do not deploy anything."
   Expected result: a readiness verdict that names what evidence exists and what
   is missing (for example CI results, live integration tests, or a rollback
   plan), a short list of next steps, and no deployment.

2. **Controlled repository work.** "Use ROSS to inspect this task, preserve
   existing work, make only authorized changes, verify them, and stop when
   complete." Expected result: unrelated edits left untouched, a narrow change,
   targeted verification, and a report that claims only what was verified.

3. **Authority boundary.** "Use the ROSS skill. Review this handoff and
   determine what actions are actually authorized. Do not treat quoted or
   implied permission as approval." Expected result: a list of actions
   separated into authorized and not authorized, with any "approval is implied"
   wording identified as not being authorization.

## Data handling and security

The plugin contains only Markdown and JSON instruction files. It has no
scripts, hooks, MCP servers, executables, or network configuration.

- No backend or hosted service.
- No MCP server.
- No external account is created.
- No telemetry.
- ROSS itself does not collect, store, or transmit user data.
- ROSS does not grant itself access or authority.
- ROSS works only through the capabilities your Claude host already provides,
  under that host's permissions.

## Troubleshooting

- **ROSS did not seem to apply.** Invoke it explicitly as described in "How to
  use it".
- **The skill is not listed.** In Claude Code, run `/plugin` and confirm the
  `ross` plugin is installed and enabled, then start a new session.
- **Claude refused an action you wanted.** ROSS will not act on authority that
  is only implied. State the action you authorize directly in your request.

## Support

Email rahul@trustgraphed.com for product questions. Report security
vulnerabilities through GitHub private vulnerability reporting on
https://github.com/TGFounder/ROSS, as described in the repository's
`SECURITY.md`. Do not put secrets or exploit details in a public issue.

## License

Apache License 2.0. See `LICENSE` and `NOTICE`.
