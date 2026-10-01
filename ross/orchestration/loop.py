"""The orchestration loop. BASELINE and ROSS run this same code path; the profile only toggles efficiency mechanisms.
Every request is admitted by the budget governor; every tool call passes the security gate."""
import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field

from ..core import context as ctxpol
from ..core import evidence
from ..core.budget import BudgetExceeded, Governor
from ..core.memory import Memory, terms_of
from ..core.models import Usage
from ..core.security import Authority, Gate, Workspace
from ..core.telemetry import Telemetry
from ..providers.base import ModelRequest, ProviderError, estimate_tokens
from ..storage.sqlite import SQLiteStateStore
from .artifacts import Artifacts
from .profile import Profile, system_prompt
from .scheduler import Scheduler
from .tools import SCHEMAS, Tools

NEXT_RE = re.compile(r"(?i)\b(?:next(?: steps?)?|remaining|still to do|todo)\s*:\s*([^\n]+)")
DEFER_RE = re.compile(r"(?i)\b(next session|haven'?t (started|done)|have not (started|done)|not (started|done) yet|deferred|left for)\b")
CONSTRAINT_RE = re.compile(r"(?i)[^.\n]*\b(do not|don't|never|must not)\b[^.\n]*")


@dataclass
class Result:
    status: str                  # done | budget | error | max_calls
    final_text: str
    calls: int
    usage: Usage
    cost_usd: float
    cost_class: str
    tool_calls: int
    tool_result_chars: int
    denied: list = field(default_factory=list)
    detail: str = ""
    messages: list = field(default_factory=list)  # in memory only (evaluation checks); never persisted


class Session:
    def __init__(self, root, provider, profile, budget, user_request, project_id="project", rate_override=None, skills=None,
                 max_output=8192, max_calls_hard=60, keep_messages=False, run_budget=None):
        self.root = evidence.project_root(root)
        self.provider, self.profile, self.prompt, self.project_id = provider, profile, user_request, project_id
        self.caps = provider.capabilities
        self.session_id = uuid.uuid4().hex[:12]
        self.scopes = [("project", project_id), ("session", self.session_id)]
        g = evidence.git_identity(self.root)
        self.start_sha = evidence.git(self.root, "rev-parse", "HEAD")
        self.gate = Gate(Workspace(self.root, g.get("dirty", [])), Authority(user_request))
        self.kind = ctxpol.classify(user_request)
        self._use_store = profile.on("memory") and self.kind != "simple"  # dormant for simple tasks: no state created
        self.store, self.memory = None, None  # opened in run() and always closed there
        self.telemetry = Telemetry(None, self.session_id)
        self.artifacts = Artifacts(self.root)
        self.scheduler = Scheduler(self)
        self.tools = Tools(self)
        self.governor = Governor(budget, self.caps.pricing_key or self.caps.provider, self.caps.model, rate_override,
                                 run_budget=run_budget)
        self.max_output, self.max_calls_hard = max_output, max_calls_hard
        self.skills = skills
        self.keep_messages = keep_messages

    # ------------------------------------------------------------ context
    def _blocks(self):
        if self.profile.name == "baseline" or self.kind == "simple":
            return []
        blocks = []
        if self.profile.on("preflight"):
            blocks.append(ctxpol.preflight(self.root, self.prompt))
        if self.memory:
            if self.kind == "resume":
                blocks.append(self.memory.state_block(self.scopes[:1], terms=terms_of(self.prompt), include_git=not self.profile.on("preflight")))
            else:  # a new instruction: only durable user constraints and decisions travel forward
                cur, _ = self.memory.recall(self.scopes[:1], types=("constraint", "decision"))
                if cur:
                    blocks.append("Standing user constraints and decisions:\n" + "\n".join(f"- {i.value}" for i in cur[:8]))
        if self.skills:
            blocks.append(self.skills.metadata_block())
        return blocks

    def _request(self, messages, max_output):
        prefix_profile = Profile.baseline() if self.kind == "simple" else self.profile  # dormant: no kernel on simple tasks
        req = ModelRequest(system=system_prompt(prefix_profile), tools=SCHEMAS, messages=messages, max_output=max_output,
                           cache=ctxpol.cache_plan(self.caps, self.profile.on("cache_policy")))
        if self.profile.on("context_selection") and self.governor.rates:
            r = self.governor.rates
            cut = ctxpol.reduce_history(messages, self.artifacts, len(json.dumps(messages)) // 3,
                                        r["cache_read"], r["cache_write_5m"])
            if cut:
                self.telemetry("history_chars_replaced", cut, "COUNTED")
        if self.profile.on("native_context_management") and self.caps.context_editing:
            req.context_edits = [{"type": "clear_tool_uses_20250919", "trigger": {"type": "input_tokens", "value": 60000},
                                  "keep": {"type": "tool_uses", "value": 3}, "clear_at_least": {"type": "input_tokens", "value": 10000}}]
        return req

    # ------------------------------------------------------------ loop
    def run(self):
        if self._use_store:
            self.store = SQLiteStateStore(self.root)
            self.memory = Memory(self.store, self.root)
            self.telemetry = Telemetry(self.store, self.session_id)
        try:
            return self._run()
        finally:
            if self.store:
                self.store.close()  # one connection per session; never left open

    def _run(self):
        messages = [{"role": "user", "content": [{"type": "text", "text": ctxpol.first_message(self.prompt, self._blocks())}]}]
        usage, cost, calls, tool_calls, result_chars, denied = Usage(), 0.0, 0, 0, 0, []
        final_text, status, detail = "", "done", ""
        while True:
            if calls >= self.max_calls_hard:
                status, detail = "max_calls", f"stopped after {calls} calls"
                break
            req = self._request(messages, self.max_output)
            try:
                try:
                    n = self.provider.count_tokens(req)
                except ProviderError:
                    n = estimate_tokens(req) * 6 // 5  # no exact count available: a conservative local estimate
                req.max_output = self.governor.admit(n, req.max_output)
            except BudgetExceeded as e:
                status, detail = "budget", str(e)
                break
            try:
                resp = self.provider.create(req)
            except ProviderError as e:
                if e.maybe_billed:
                    self.governor.charge_failed_attempt(n, req.max_output)
                if e.retryable:
                    time.sleep(2)
                    try:
                        req.max_output = self.governor.admit(n, req.max_output)  # retries are admitted like any call
                        resp = self.provider.create(req)
                    except (ProviderError, BudgetExceeded) as e2:
                        status, detail = ("budget" if isinstance(e2, BudgetExceeded) else "error"), str(e2)
                        break
                else:
                    status, detail = "error", str(e)
                    break
            calls += 1
            c = self.governor.charge(resp.usage)
            usage, cost = usage + resp.usage, cost + c
            if self.store:
                self.store.record_usage(dict(run_id=self.session_id, session_id=self.session_id, profile=self.profile.name,
                                             provider=self.caps.provider, model=self.caps.model, call_index=calls,
                                             uncached=resp.usage.uncached_input, cache_write=resp.usage.cache_write,
                                             cache_write_1h=resp.usage.cache_write_1h, cache_read=resp.usage.cache_read,
                                             output=resp.usage.output, cost=c, cost_class="ESTIMATED", price_version=self.governor.version))
            messages.append({"role": "assistant", "content": resp.content})
            text = "\n".join(b["text"] for b in resp.content if b["type"] == "text").strip()
            uses = [b for b in resp.content if b["type"] == "tool_use"]
            if not uses:
                final_text = text
                if resp.stop_reason == "max_tokens":
                    status, detail = "error", "output limit reached"
                break
            results, finals = [], []
            for b in uses:
                out, is_err, meta = self.tools.execute(b["name"], b.get("input") or {})
                tool_calls += 1
                result_chars += len(out)
                if out.startswith("ROSS policy:"):
                    denied.append(f"{b['name']}: {out[13:120]}")
                results.append({"type": "tool_result", "tool_use_id": b["id"], "content": out, "is_error": bool(is_err)})
                if meta.get("final"):
                    finals.append(meta)
            messages.append({"role": "user", "content": results})
            if (self.profile.on("stop_policy") and finals and text and all(f.get("exit") == 0 for f in finals)
                    and not any(r["is_error"] for r in results)):
                # Stop policy: the answer arrived with the final verifying command and that command passed locally.
                final_text = text + "\n\nVerified locally: " + "; ".join(f"`{f['command']}` exit 0" for f in finals)
                self.telemetry("calls_saved_by_stop_policy", 1, "COUNTED")
                break
        self._remember(final_text, status)
        return Result(status, final_text, calls, usage, round(cost, 6), "ESTIMATED from " + str(self.governor.version), tool_calls,
                      result_chars, denied, detail, messages if self.keep_messages else [])

    # ------------------------------------------------------------ memory: the result of history, never the transcript
    def _remember(self, final_text, status):
        m = self.memory
        if not m:
            return
        pid = self.project_id
        if self.kind == "coding":
            m.remember("project", pid, "goal", self.prompt[:400], "USER_DECISION")
            for old in m.store.active("project", pid, ("next",)):  # a new instruction supersedes the old next step
                m.store.supersede(old.id)
            for x in CONSTRAINT_RE.finditer(self.prompt):
                sent = x.group(0).strip()
                m.remember("project", pid, "constraint", sent[:300], "USER_CONSTRAINT", key=hashlib.sha256(sent.encode()).hexdigest()[:12])
        if final_text:
            m.remember("project", pid, "last_result", final_text[-500:], "MODEL_SUMMARY")
            nx = NEXT_RE.search(final_text)
            nxt = nx.group(1).strip() if nx else next((s.strip(" -*") for s in re.split(r"(?<=[.!?])\s+|\n+", final_text) if DEFER_RE.search(s)), None)
            if nxt:
                m.remember("project", pid, "next", nxt[:300], "MODEL_SUMMARY")
        changed = set(evidence.git(self.root, "diff", "--name-only", self.start_sha).splitlines()) if self.start_sha else set()
        changed |= set(evidence.git_identity(self.root).get("dirty", []))
        if changed:
            m.remember("project", pid, "changed", ", ".join(sorted(changed)[:30]), "DERIVED_STATE")
        m.remember("session", self.session_id, "status", status, "DERIVED_STATE")


def summarize(result):
    u = result.usage
    return json.dumps({"status": result.status, "calls": result.calls, "uncached": u.uncached_input, "cache_write": u.cache_write,
                       "cache_read": u.cache_read, "output": u.output, "total": u.total, "cost_usd": result.cost_usd,
                       "cost_class": result.cost_class, "tool_calls": result.tool_calls, "denied": result.denied, "detail": result.detail})
