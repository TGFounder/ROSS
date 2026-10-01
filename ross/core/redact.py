"""Known-secret redaction. Useful, but not a complete secret-safety system: sensitive operations are also not persisted."""
import os
import re

SECRET_RES = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(sk|rk|pk)[-_](live|test|proj|ant)?[-_]?[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
]
KEYVAL_RE = re.compile(r"(?i)\b((?:api[_-]?key|secret|token|passwd|password|pwd|auth)\w*\s*[:=]\s*)[\"']?[^\s\"',;]{6,}")
CREDENTIAL_ENV = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ROSS_API_KEY")


def live_credentials():
    """Values of provider credentials in this process's environment (never stored, only used to scrub)."""
    return [v for v in (os.environ.get(k) for k in CREDENTIAL_ENV) if v and len(v) >= 8]


def redact(text):
    if not isinstance(text, str):
        return text
    for cred in live_credentials():
        text = text.replace(cred, "[REDACTED]")
    for rx in SECRET_RES:
        text = rx.sub("[REDACTED]", text)
    return KEYVAL_RE.sub(lambda m: m.group(1) + "[REDACTED]", text)
