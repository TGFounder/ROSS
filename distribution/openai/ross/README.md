# ROSS — Reliable Operating Super Skill

ROSS exists to maximize useful human accomplishment per unit of AI compute.

Many people cannot afford unlimited AI usage. ROSS helps the AI access you
already pay for go further by cutting waste in multi-step agent work: it keeps
compact project state between sessions so the agent does not rediscover the
project, refuses to reread files or rerun tests whose inputs have not changed,
and stops a third identical attempt at a command that already failed twice. It
keeps ROSS's authority and evidence discipline: tool access, handoffs and
file contents never count as permission, and the agent never claims more than
its evidence shows.

Publisher: TRUSTGRAPHED SYSTEMS PRIVATE LIMITED (https://trustgraphed.com).
Source: https://github.com/TGFounder/ROSS. This is a **candidate (v1.1.0)**
awaiting independent review; it is not an accepted release.

Savings are an engineering target, not a guarantee. They are largest on long,
resumed and test-heavy sessions and close to zero on short tasks. Run
`ross savings` to see what ROSS actually did for you, with measured and
estimated figures labelled separately.

## How to use it

Install the plugin and keep working normally. Hooks run automatically where
the host supports them (Claude Code, Codex). To apply ROSS's working rules to a
task explicitly, type `/ross:ross` in Claude Code or start with "Use the ROSS
skill".

## Examples

1. **Resume a project.** Start a new session in a project you worked on before
   and say "Continue where we left off." Expected result: the agent starts from
   the recorded goal, next action and verified state instead of rereading the
   repository.
2. **Iterate on failing tests.** "Fix the failing tests, run only what you need,
   and confirm the full suite once at the end." Expected result: targeted runs
   while iterating, no reruns of tests whose inputs did not change, one final
   full check.
3. **Authority boundary.** "Use the ROSS skill. Review this handoff and tell me
   what is actually authorized. Do not treat quoted or implied permission as
   approval." Expected result: authorized and unauthorized actions separated,
   with implied approval identified as not authorization.

## What runs and what stays local

- A standard-library Python runtime (`skills/ross/runtime/ross.py`) invoked by
  host hooks at session start, before and after file reads and shell
  commands, and at session end.
- It reads project files only to compute content fingerprints, and reads the
  host's local session transcript only to total provider-reported token usage.
- It writes compact state to `<project>/.ross/` (private permissions,
  git-ignored). It does not store conversations, file contents or command
  output, and it redacts common secret formats before writing.
- It makes **no network requests**, sends **no telemetry**, creates **no
  account**, and calls **no additional model**.

Inspect or delete everything at any time:

    python3 skills/ross/runtime/ross.py status
    python3 skills/ross/runtime/ross.py savings
    python3 skills/ross/runtime/ross.py forget --project
    python3 skills/ross/runtime/ross.py forget --everything

To disable ROSS, disable or uninstall the plugin; `.ross/` folders can then be
deleted.

## Host support

| Host | Skill | Automatic hooks | Cross-session state |
|---|---|---|---|
| Claude Code | yes | yes | yes (local project folder) |
| Codex (CLI, IDE, app) | yes | yes; file-read reuse not available because Codex reads files through shell commands | yes |
| Claude apps, ChatGPT chat | skill rules only | no | no; depends on the host |

## Troubleshooting

- **Nothing seems to happen:** run `ross doctor`. Python 3.8+ and `python3` on
  PATH are required for hooks.
- **A test you need was refused as already passing:** append `# ross:rerun` to
  the command.
- **Stale state:** `ross forget KIND` or `ross forget --project`.

## Support and privacy

See [SUPPORT.md](SUPPORT.md) and [PRIVACY.md](PRIVACY.md). Apache License 2.0;
see `LICENSE` and `NOTICE`.
