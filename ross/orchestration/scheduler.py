"""Model-call scheduler: decide locally what does not need model intelligence. No model is ever called to route or summarize."""
import re

TEST_RE = re.compile(r"(^|[\s;&|(])(pytest|py\.test|python3? -m (pytest|unittest)|npm (run )?test|pnpm (run )?test|yarn test|go test|cargo test|tox)\b")


def test_key(cmd):
    c = re.sub(r"\s+2>&1", "", " ".join(str(cmd).split()))
    return re.sub(r"\s*\|\s*(tail|head)(\s+-n)?(\s+-?\d+)?\s*$", "", c)


class Scheduler:
    def __init__(self, ctx):
        self.ctx = ctx
        self.seen = {}  # rel path -> content hash shown whole in this session

    def seen_unchanged(self, rel, h):
        if self.seen.get(rel) == h:
            self.ctx.telemetry("dup_read_avoided", 1, "COUNTED")
            return f"[{rel} is unchanged since you read it earlier in this session; use that content.]"
        return None

    def mark_seen(self, rel, h):
        self.seen[rel] = h

    def forget_seen(self, rel):
        self.seen.pop(rel, None)

    def reuse_test(self, cmd):
        """A test that passed on identical inputs (verified evidence, still current) is reported, not rerun."""
        c = self.ctx
        if not c.profile.on("memory") or not TEST_RE.search(cmd) or "|" in test_key(cmd):
            return None
        cur, _ = c.memory.recall(c.scopes, types=("test_result",))
        for item in cur:
            if item.key == test_key(cmd):
                c.telemetry("test_reused", 1, "COUNTED")
                return f"exit code 0\n[ROSS: `{item.key}` already passed on identical files ({item.value}); not rerun.]"
        return None

    def record_run(self, cmd, code, out):
        c = self.ctx
        if c.memory is None or not TEST_RE.search(cmd):
            return
        key = test_key(cmd)
        if code == 0 and not re.search(r"\b\d+ failed\b|\berror\b", out[-500:], re.I):
            summary = next((l.strip() for l in out.splitlines()[::-1] if re.search(r"passed|Ran \d+|OK", l)), "passed")[:120]
            c.memory.remember("project", c.project_id, "test_result", f"`{key}`: {summary}", "VERIFIED_EVIDENCE", key=key, fp_kind="inputs")
        else:
            for item in c.store.active("project", c.project_id, ("test_result",)):
                if item.key == key:
                    c.store.supersede(item.id)
