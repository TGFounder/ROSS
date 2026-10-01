"""OpenAI Responses API adapter: request and usage mapping only. Live execution is not enabled in this build (no OpenAI
credits are spent); the live matched test happens separately under a hard ROSS budget."""
from ..core.models import Usage
from .base import Capabilities, Provider, ProviderError


class OpenAIProvider(Provider):
    def __init__(self, model="gpt-5.6"):
        self.model = model

    @property
    def capabilities(self):
        return Capabilities(provider="openai", model=self.model, context_window=400_000, max_output=64_000, token_counting="exact",
                            usage_breakdown=True, prompt_caching="explicit+auto", cache_ttls=("30m",), min_cacheable_tokens=1024,
                            max_cache_breakpoints=4, native_compaction=True, context_editing=False, deferred_tools=True,
                            structured_output=True, pricing_key=None)  # no verified pricing snapshot: no guaranteed dollar cap

    def body(self, request):
        items = []
        for m in request.messages:
            for b in m["content"]:
                if b["type"] == "text":
                    items.append({"role": m["role"], "content": b["text"]})
                elif b["type"] == "tool_use":
                    import json
                    items.append({"type": "function_call", "call_id": b["id"], "name": b["name"], "arguments": json.dumps(b.get("input") or {})})
                elif b["type"] == "tool_result":
                    items.append({"type": "function_call_output", "call_id": b["tool_use_id"], "output": b["content"]})
        body = {"model": self.model, "instructions": request.system, "input": items, "max_output_tokens": request.max_output,
                "tools": [{"type": "function", "name": t["name"], "description": t["description"], "parameters": t["schema"]}
                          for t in request.tools]}
        if request.cache.get("mode") == "explicit":
            body["prompt_cache_options"] = {"mode": "explicit"}
        return body

    @staticmethod
    def usage(u):
        d = u.get("input_tokens_details") or {}
        read, write = d.get("cached_tokens", 0) or 0, d.get("cache_write_tokens", 0) or 0
        return Usage(uncached_input=max(0, (u.get("input_tokens", 0) or 0) - read - write), cache_write=write, cache_read=read,
                     output=u.get("output_tokens", 0) or 0)

    def count_tokens(self, request):
        raise ProviderError("OpenAI token counting (POST /v1/responses/input_tokens) is not enabled in this build")

    def create(self, request):
        raise ProviderError("OpenAI live execution is not enabled in this build; OpenAI validation happens separately")
