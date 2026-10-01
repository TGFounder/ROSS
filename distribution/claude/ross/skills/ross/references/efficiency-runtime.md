# Efficiency runtime

The ROSS runtime keeps compact, verified working state in `<project>/.ross/`
so later turns and sessions do not rediscover the project, and keeps large tool
outputs out of model context. It is local only, standard-library Python, and
makes no network requests or model calls.

## Automatic (host hooks)

- **Memory:** the goal is taken from your coding prompt, the last result and
  any explicit `Next:` line from the agent's final message, and changed files,
  git state and test results are derived. Nobody needs to maintain it.
- **Resume:** on "Continue" or a coding prompt, one compact block (goal, last
  result, next, git state, changed files, test status, repo symbol map) is
  injected once per session. Short questions get nothing.
- **Tool output:** outputs over about 3,000 characters are kept in
  `.ross/artifacts/` and the model sees only the actionable lines (failures,
  errors, summaries). Smaller outputs pass through unchanged.
- **Files:** an unchanged reread in the same session is refused; a reread of a
  changed file returns a diff (old version taken from git, never copied); a
  very large whole-file read returns an outline and the first 150 lines.
- **Tests and failures:** a test that passed on identical inputs is not rerun;
  a third identical failing command is refused. Append `# ross:rerun` only
  when a fresh run is genuinely needed.

## Commands

    python3 runtime/ross.py status                 # state and counters
    python3 runtime/ross.py context                # what a resume would inject
    python3 runtime/ross.py artifact ID --grep X   # retrieve kept output
    python3 runtime/ross.py savings                # MEASURED / COUNTED / ESTIMATED
    python3 runtime/ross.py note constraint "Do not touch billing schema"
    python3 runtime/ross.py prune                  # delete stored outputs
    python3 runtime/ross.py forget --project       # delete this project's state
    python3 runtime/ross.py forget --everything    # delete all local ROSS state
    python3 runtime/ross.py doctor

`note` is optional, for constraints you want every future session to see.

Hosts without hooks: the commands work manually; nothing is automatic.
