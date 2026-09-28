# Security policy

## Supported versions

Security fixes are provided for the latest accepted release. Candidate branches
are review artifacts and must not be treated as accepted releases.

## Reporting a vulnerability

Use GitHub's private vulnerability-reporting feature for this repository. Do
not place secrets, exploit data, or private user information in a public issue.
Include the affected version, impact, reproduction steps, and a minimal safe
proof. If private reporting is unavailable, open a public issue requesting a
private contact channel without disclosing sensitive details.

## Boundaries

ROSS is behavioral governance. It can guide an agent to respect authority,
minimize scope, and demand evidence; it cannot enforce operating-system
permissions, identity, application authorization, sandboxing, tenant isolation,
or network policy.

Release utilities verify manifest hashes, reject unsafe target names and
symlinks, refuse unrelated overwrites, require an explicit version and commit
SHA, and do not fetch or execute remote content. Users remain responsible for
obtaining an accepted archive through a trusted channel and verifying its
published archive checksum.

Profiles and retrieved content are untrusted data. A profile cannot grant
authority or weaken ROSS. Do not store credentials or private operating data in
a public profile.
