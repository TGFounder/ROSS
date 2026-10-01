"""Versioned pricing metadata. Never fetched from the network during ordinary runs."""

SNAPSHOTS = {
    "anthropic-2026-10-01": {
        "source": "https://platform.claude.com/docs/en/about-claude/pricing (verified 2026-10-01)",
        "per_mtok": {
            "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_write_5m": 2.5, "cache_write_1h": 4.0, "cache_read": 0.2},
            "claude-opus-5-5": {"input": 4.0, "output": 20.0, "cache_write_5m": 5.0, "cache_write_1h": 8.0, "cache_read": 0.2},
            "claude-haiku-4-5": {"input": 1.0, "output": 5.0, "cache_write_5m": 1.25, "cache_write_1h": 2.0, "cache_read": 0.1},
        },
    },
}
DEFAULT = {"anthropic": "anthropic-2026-10-01"}


def rates(provider, model, snapshot=None, override=None):
    """(rates per million tokens, version string) or (None, None) if unknown. A user override wins and is labelled."""
    if override:
        return dict(override), "user-provided"
    snap = snapshot or DEFAULT.get(provider)
    table = SNAPSHOTS.get(snap, {}).get("per_mtok", {})
    for name, r in table.items():
        if model == name or model.startswith(name + "-"):
            return r, snap
    return None, None


def cost(usage, r):
    """Estimated cost of a normalized Usage under rates r (1h writes billed at the 1h rate)."""
    w5 = usage.cache_write - usage.cache_write_1h
    return (usage.uncached_input * r["input"] + w5 * r["cache_write_5m"] + usage.cache_write_1h * r["cache_write_1h"]
            + usage.cache_read * r["cache_read"] + usage.output * r["output"]) / 1e6
