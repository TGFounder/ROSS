# Efficiency runtime

The ROSS runtime keeps compact, verified working state in `<project>/.ross/`
so later turns and sessions do not rediscover the project. It is local only,
standard-library Python, and makes no network requests.

## What is automatic (when host hooks are installed)

- **Session start:** a short state block (goal, next action, blockers,
  constraints, decisions, still-valid test results, git state) is injected.
- **Reads:** rereading a file that is unchanged since it was read in the same
  session is refused with a pointer to the content already in context.
- **Tests:** rerunning a test command that passed against identical inputs is
  refused. Any change to tracked or untracked files invalidates the result.
  Append `# ross:rerun` to force a run.
- **Failures:** a third attempt of a command that failed twice with identical
  inputs and the same error is refused until something changes.
- **Usage:** provider-reported token usage is read from the host transcript.

## What you record

Only semantic facts the runtime cannot derive, and only when they change:

    python3 runtime/ross.py note goal "Ship iOS release"
    python3 runtime/ross.py note decision "Keep current backend"
    python3 runtime/ross.py note constraint "Do not touch Android production"
    python3 runtime/ross.py note blocker "App Store metadata"
    python3 runtime/ross.py note --remove blocker "App Store metadata"
    python3 runtime/ross.py checkpoint --next "Prepare submission"

An unchanged note writes nothing.

## Inspect and control

    python3 runtime/ross.py status      # state and counters
    python3 runtime/ross.py context     # what would be injected
    python3 runtime/ross.py savings     # measured vs estimated savings
    python3 runtime/ross.py forget blocker "App Store metadata"
    python3 runtime/ross.py forget --project      # delete this project's state
    python3 runtime/ross.py forget --everything   # delete all local ROSS state
    python3 runtime/ross.py doctor

Without hooks (skill-only hosts) the same commands work manually; nothing is
automatic and cross-session memory exists only where the host keeps a
writable project directory.
