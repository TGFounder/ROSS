# ROSS v1.3.0 candidate (Efficiency Engine v2): review package

Status: **CANDIDATE — AWAITING INDEPENDENT REVIEW AND FOUNDER ACCEPTANCE.**
Branch `candidate/ross-efficiency-engine-v2`, started from `a7affe44` (the
measured v1.2.0 candidate, left untouched). Not merged, tagged or released.
`v1.0.0` (5e54f13) untouched. ROSS governed this build; it does not accept it.

## Objective

Same real work in fewer model calls and with less new context, on the Claude
Code host. Stretch target for this build: 35% fewer total model tokens with no
quality loss. Mission target unchanged at 50%.

## What changed

1. **Turn reduction.** Kernel rule 3 now states the cost model (every step
   re-sends the context) and asks for one step of parallel safe reads and
   checks, then all edits plus the verifying run in one step; never batching
   irreversible, consequential or unclearly authorized actions. Turns are
   counted per session (inspection-only, implementation, verification,
   recovery, calls to first action, implementation and verified completion)
   from the host transcript, with no model call. After two consecutive
   inspection-only turns, one line is injected once per session.
2. **Shell file reads.** Plain `cat`/`nl` of project files is served by the
   runtime: unchanged-since-seen files are not repeated, changed files come as a
   diff against the version seen (from git), files over 24 KB come as an
   outline plus 80 lines. `# ross:full` bypasses everything. Pipelines, globs,
   redirects and `sed`/`head`/`tail` ranges are left alone.
3. **Progressive context.** Level 0 for non-coding prompts (no state created).
   Level 1 on "Continue" (goal, next step or blocker, last result, branch and
   commit, changed files, test status). Level 2 only for files or symbols the
   task names: small files whole, large files as outlines, files named by a
   named plan document as outlines or whole if small, exact symbol ranges;
   budget about 2,300 tokens; never twice per session. Level 3 only via
   `ross context --deep`. The automatic repository map was removed.
4. **Output compression.** Failures grouped by root error with location and
   code (pytest), plus eslint, package installs, git log, grep/rg, listings and
   JSON parsers; generic fallback kept. A pure test command trimmed with
   `| tail`/`| head` is served as root errors plus summary instead of an
   arbitrary slice. Test results are keyed independently of output trimming.
   **Defect fixed from v1.2.0:** a compound command that read files and ran a
   heavy command (for example `cat a.py && pytest | tail`) had its whole output
   compressed, hiding the file contents and costing the agent an extra call.
   Commands that read files are now never compressed.
5. **Automatic memory.** At session end: next step from an explicit `Next:` line
   or a deferral sentence in the agent's own final message, explicit blocker,
   branch and commit, changed files, tests and results. Resume header states
   that continuing means carrying on with unfinished or explicitly deferred
   work. No model call, no transcript stored.

Kernel: 633 to 572 tokens total, 499 to 462 body (characters/4 estimate for
both; the v1.2.0 report used a different count). Skill description shortened.

## Host findings (Claude Code 2.1.286)

- `num_turns` counts each parallel tool result, so it over-counts batched
  steps. This report uses distinct model calls (API requests), the unit of
  prefix replay, and shows `num_turns` alongside.
- `PostToolUse` `additionalContext` is applied (nudge observed in a probe).
- The Edit tool requires a prior Read of the file, so injected file text cannot
  remove a Read when the agent edits with Edit; in practice agents here edited
  through shell scripts.
- About 29,300 tokens of host system prompt and tool definitions are re-read
  on every call.

## Acceptance workload (new)

`shipq`, an unfamiliar shipping-quote library: 8 modules including a
1,736-line generated zone table, 44 tests. Session A prompt: multi-parcel
quotes look wrong and the suite fails (two root causes: postcode key
normalisation and per-parcel volumetric weight); fix, add `--json`, add tests;
"the next piece of work is in ROADMAP.md; we'll do that in the next session".
Process exits. Session B prompt exactly `Continue.` (Phase 2 in ROADMAP.md:
remote-area surcharge, not-serviceable carriers, CLI changes). Hidden
acceptance tests per phase. Sonnet 5.5, same settings, fresh repos, natural
completion (80-call cap never reached), 3 chains per condition, one run.
Development used three single-chain probes; the matched run was done once.

## Matched results (provider-reported usage)

All sessions (A+B, 3 chains each):

| Metric | Base | ROSS | Change |
|---|---|---|---|
| Sessions passing hidden tests | 4/6 | 6/6 | ROSS +2 |
| Chains fully passing | 1/3 | 3/3 | |
| Model calls | 34 | 36 | +5.9% |
| Host `num_turns` | 34 | 39 | +14.7% |
| Uncached input | 68 | 72 | +5.9% |
| Cache read | 1,215,921 | 1,332,872 | +9.6% |
| Cache write | 69,986 | 79,610 | +13.8% |
| Output | 12,924 | 19,150 | +48.2% |
| Total tokens | 1,298,899 | 1,431,704 | **+10.2%** |
| Cost (USD) | 0.6558 | 0.7799 | **+18.9%** |
| Tool calls | 28 | 33 | +17.9% |
| Tool-result bytes | 65,193 | 52,090 | −20.1% |
| File-content bytes | 44,341 | 20,640 | −53.5% |
| Full / partial file reads | 8 / 1 | 4 / 6 | |
| Test runs | 15 | 18 | +20.0% |

Primary metrics:

| | Base | ROSS | Change |
|---|---|---|---|
| Tokens per successful session | 324,725 | 238,617 | −26.5% |
| Cost per successful session | $0.1639 | $0.1300 | −20.7% |
| Tokens per fully successful chain | 1,298,899 | 477,235 | −63.3% |
| Cost per fully successful chain | $0.6558 | $0.2600 | −60.4% |

Why raw totals rose: in 2 of 3 base chains, "Continue." found no record of the
deferred work, reported the state and asked what to do (Phase 2 not done:
hidden tests failed). Those sessions were cheap because they did no work.
ROSS did Phase 2 in all three. The per-chain figure is dominated by that
quality gap at n=3 and should not be read as a general saving.

Session A only (same work, both 3/3): base 734,775 tokens / $0.369 / 19 calls;
ROSS 784,447 / $0.369 / 20 calls (**+6.8% tokens, cost equal**). File-content
bytes −62.8%, tool-result bytes −21.8%. No turn reduction was demonstrated.

Session B, successful sessions only: base 1 session, 277,553 tokens, $0.154,
7 calls, implementation first at call 5; ROSS mean of 3, 215,752 tokens,
$0.137, 5.3 calls, implementation first at call 2.3 (−22% tokens, −11% cost
against a single base sample).

Noise disclosed: the agent sometimes mangled the scratch path in a first `cd`
command, wasting about two calls (base 1 session, ROSS 3 sessions). This is a
harness artifact affecting both conditions; results above are unadjusted.

Short question (3 runs each): base 68,815 to 68,926 tokens; ROSS 69,038 to
69,172 (**+0.34%**, the plugin's skill listing); cost +0.6% to +1.3%; 2 calls
each; no state created, nothing injected or wrapped.

## Host ceiling analysis (from the observed breakdown)

- Host-controlled: about 29,300 tokens of fixed prefix per call. Base: 34 calls
  x 29,294 = 76.7% of all tokens; ROSS: 73.7%.
- Directly controllable by ROSS: what enters the conversation (tool results,
  injected context) and is then re-read on each later call. Together with
  output this is 23 to 26% of tokens. Removing all of it is impossible; a
  realistic cut is a third to a half, worth 8 to 13% of total.
- Influenced through turns: each avoided call saves about 38,000 to 40,000
  tokens here. Observed floors: about 4 calls for Session A (read and test,
  fix and test, feature and test, report) against 6.3 observed; 3 to 4 for
  Session B against 7 for the successful base run.
- Realistic plugin ceiling for efficient Sonnet sessions on this host: about
  25 to 40% on resumed multi-step work, near 0 on short tasks. 50% is not
  reachable as a plugin when the model is already efficient; it needs fewer
  host-prefix tokens per call, which only ROSS-controlled API orchestration
  (own system prompt, own tool set, own caching) can provide.

## Limitations

- n=3 per condition; one run. Session-level differences are within model
  variance except the resume quality gap.
- Level 2 hydration fired here because the prompt named ROADMAP.md; a prompt
  naming no files gets none.
- Large-file `cat` outline did not fire live (agents used `sed -n` ranges).
- The batching nudge fired in probes; its effect on call count is unmeasured.
- Codex behaviour is static-only (`additionalContext`, `updatedInput`).

## Next highest-leverage opportunity

A consented first-step bundle: on a coding prompt in a repository, run the
project's read-only status checks (git status, file list, and with explicit
user opt-in the test command) before the first model call and inject the
grouped result. Every observed session spent its first call on exactly this.
Beyond that, API-level orchestration to shrink the 77% host prefix.

## Privacy

Local only; no network, telemetry, accounts or extra models. New stored data:
which files were shown in the session (hash and git blob id), turn counts,
nudge flags. Named file text is passed to the agent as if read, never stored.
`forget --project` / `--everything` delete all.

## OpenAI

Packages regenerated from the same canonical files; static checks pass.
No Codex-specific changes. Live economics test not run (not in scope).
