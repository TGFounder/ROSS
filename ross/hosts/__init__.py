"""Host efficiency mode. The proven plugin runtime (runtime/ross.py, packaged in distribution/claude and distribution/openai)
is the host-mode champion and is not modified here. Hosts own their system prompt, tools, model calls and cached prefix;
ROSS uses only the controls each host exposes (hooks, skills, plugin packaging) and never calls a second model."""

HOSTS = {
    "claude-code": {"entry": "runtime/ross.py hook EVENT", "controls": ["SessionStart", "UserPromptSubmit", "PreToolUse updatedInput",
                    "PostToolUse", "Stop", "SessionEnd"], "owns_inference": "host"},
    "codex": {"entry": "runtime/ross.py hook EVENT", "controls": ["same hook JSON protocol (static validation only)"], "owns_inference": "host"},
}
