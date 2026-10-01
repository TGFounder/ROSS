# ROSS Support

ROSS (Reliable Operating Super Skill) is published by TRUSTGRAPHED SYSTEMS
PRIVATE LIMITED.

## Getting help

- **Questions and problems:** email rahul@trustgraphed.com, or open an issue at
  https://github.com/TGFounder/ROSS/issues. Include the Claude app you use and
  the prompt that did not behave as expected.
- **Security vulnerabilities:** use GitHub private vulnerability reporting on
  https://github.com/TGFounder/ROSS. Do not put secrets or exploit details in a
  public issue.

## Before you ask

- Run `python3 skills/ross/runtime/ross.py doctor` to check the runtime.
- A test you need was refused as already passing: append `# ross:rerun`.
- To apply ROSS rules explicitly, type `/ross:ross` in Claude Code or start
  with "Use the ROSS skill" in any host.
- ROSS will not act on authority that is only implied, quoted, or found in a
  document. State the action you authorize directly in your request.

ROSS is provided under the Apache License 2.0, as is, without warranty. Support
is offered on a best-effort basis.
