# Efficiency runtime

The ROSS runtime keeps compact, verified working state in `<project>/.ross/`
so later turns and sessions do not rediscover the project, and keeps large tool
outputs out of model context. It is local only, standard-library Python, and
makes no network requests or model calls. Every model step re-sends the whole
context, so the runtime aims at fewer steps and less new context per step.

## Automatic (host hooks)

- **Context levels.** Level 0: greetings, questions and one-shot requests get
  nothing, and no state is created. Level 1 (on "Continue" in a new session):
  goal, explicit next step or blocker, last result, branch and commit, changed
  files, test status. Level 2 (only when the task names files or symbols): the
  current text of small named files, outlines of large ones and of files a
  named plan document names, and the exact range of named symbols, within about
  2,300 tokens and never twice per session. Level 3 (decisions, facts,
  checkpoints) only on request: `ross context --deep`. No repository map is
  injected; `ross map` prints one.
- **Memory.** The goal comes from the coding prompt; the next step, deferred
  work and blockers come from the agent's own final message; branch, commit,
  changed files and test results are derived. No `ross note` turns.
- **Shell file reads.** A plain `cat`/`nl` of project files is served by the
  runtime: a file unchanged since it was seen this session is not repeated, a
  changed one comes as a diff (old version from git, never copied), and a very
  large one as an outline plus the first 80 lines. Add `# ross:full` to any
  command to get the untouched output.
- **Tool output.** Heavy commands (tests, builds, linters, installs, git
  diff/log, recursive search, listings) keep full output in `.ross/artifacts/`
  and show only the actionable view: failures grouped by root error with the
  failing location and code, compiler and lint errors, install errors and
  totals, commit subjects, matches per file, listing counts, JSON shape.
  Outputs under about 3,000 characters pass through. Commands that read files
  are never compressed.
- **Tests and failures.** A test that passed on identical inputs is not rerun
  (output trimming such as `| tail` does not change the key); a third identical
  failing command is refused. Append `# ross:rerun` when a fresh run is needed.
- **Turn economy.** Each session's turns are counted as inspection-only,
  implementation, verification and recovery. After two consecutive
  inspection-only turns the agent is told once, in one line, that it can batch
  the next safe step.

## Commands

    python3 runtime/ross.py status                 # state and counters
    python3 runtime/ross.py context [--deep]       # what a resume would inject
    python3 runtime/ross.py map                    # repository symbol map
    python3 runtime/ross.py artifact ID --grep X   # retrieve kept output
    python3 runtime/ross.py savings                # MEASURED / COUNTED / ESTIMATED
    python3 runtime/ross.py note constraint "Do not touch billing schema"
    python3 runtime/ross.py prune                  # delete stored outputs
    python3 runtime/ross.py forget --project       # delete this project's state
    python3 runtime/ross.py forget --everything    # delete all local ROSS state
    python3 runtime/ross.py doctor

`note` is optional, for constraints you want every future session to see.

Hosts without hooks: the commands work manually; nothing is automatic.
