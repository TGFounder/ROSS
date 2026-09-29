# ROSS profiles

Profiles let a user supply conservative working preferences without changing
ROSS. They are optional JSON documents validated by `profile.schema.json`.

Profiles are deliberately not auto-discovered. Supply a profile explicitly to
the agent or host for a substantive task. This avoids recurring file reads and
prevents an untrusted repository from silently selecting user policy.

Allowed preferences are bounded values for cost sensitivity, autonomy,
reporting detail, coding minimalism, and preferred tool names. Free-form
instructions are not accepted. Preferences are defaults only: they cannot
grant authority, change scope, weaken safety or security, lower evidence
requirements, or alter protected ROSS governance.

To validate a profile, use any JSON Schema Draft 2020-12 validator against
`profile.schema.json`. Repository CI validates the included example and rejects
unknown fields. Agents should ignore an invalid profile and report why.
