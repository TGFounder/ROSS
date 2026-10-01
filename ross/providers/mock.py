"""Scripted provider for offline tests and fixtures. Usage follows a simple, documented cache model so cache policy and
budget accounting can be exercised without a live model."""
import json

from ..core.models import Usage
from .base import Capabilities, ModelResponse, Provider, estimate_tokens


class MockProvider(Provider):
    def __init__(self, script, model="claude-sonnet-5-5", caching="explicit+auto"):
        """script: list of callables(request) -> list of content blocks (or ModelResponse)."""
        self.script, self.model, self.caching = list(script), model, caching
        self.requests, self._cached = [], set()

    @property
    def capabilities(self):
        return Capabilities(provider="mock", model=self.model, context_window=200000, max_output=32000, token_counting="estimate",
                            usage_breakdown=True, prompt_caching=self.caching, cache_ttls=("5m", "1h"), min_cacheable_tokens=512,
                            max_cache_breakpoints=4, pricing_key="anthropic")

    def create(self, request):
        self.requests.append(request)
        step = self.script.pop(0)
        out = step(request)
        if isinstance(out, ModelResponse):
            return out
        prefix = json.dumps([request.system, request.tools, request.messages[:-1]])
        total = estimate_tokens(request)
        hit = request.cache.get("mode") != "none" and prefix in self._cached
        read = (len(prefix) // 3) if hit else 0
        self._cached.add(json.dumps([request.system, request.tools, request.messages]))
        written = 0 if request.cache.get("mode") == "none" else max(0, total - read)
        usage = Usage(uncached_input=0 if written else total - read, cache_write=written, cache_read=read,
                      output=sum(len(json.dumps(b)) for b in out) // 4)
        stop = "tool_use" if any(b["type"] == "tool_use" for b in out) else "end_turn"
        return ModelResponse(content=out, stop_reason=stop, usage=usage)


def text(t):
    return lambda req: [{"type": "text", "text": t}]


def tool(name, _id="t1", say="", **inp):
    return lambda req: ([{"type": "text", "text": say}] if say else []) + [{"type": "tool_use", "id": _id, "name": name, "input": inp}]


def tools(*calls, say=""):
    """Several tool calls in one model step: calls are (name, id, input-dict)."""
    return lambda req: ([{"type": "text", "text": say}] if say else []) + [
        {"type": "tool_use", "id": i, "name": n, "input": inp} for n, i, inp in calls]
