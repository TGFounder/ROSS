"""Anthropic Messages API adapter (standard library HTTP). The API key is read from ANTHROPIC_API_KEY at call time and is
never stored, logged or placed in prompts. Facts verified in docs/PROVIDER-FACTS.md."""
import json
import os
import urllib.error
import urllib.request

from ..core.models import Usage
from .base import Capabilities, ModelResponse, Provider, ProviderError

API_VERSION = "2023-06-01"
DEFAULT_BASE = "https://api.anthropic.com"
MODELS = {"claude-sonnet-5-5": (1_000_000, 64_000), "claude-opus-5-5": (1_000_000, 64_000), "claude-haiku-4-5": (200_000, 64_000)}


class AnthropicProvider(Provider):
    def __init__(self, model="claude-sonnet-5-5", base_url=None, timeout=600):
        self.model = model
        # Only an explicit ROSS setting changes the endpoint; a host's own proxy variables are never borrowed.
        self.base = (base_url or os.environ.get("ROSS_ANTHROPIC_BASE_URL") or DEFAULT_BASE).rstrip("/")
        self.timeout = timeout

    @property
    def capabilities(self):
        ctx, out = next((v for k, v in MODELS.items() if self.model.startswith(k)), (200_000, 8_192))
        return Capabilities(provider="anthropic", model=self.model, context_window=ctx, max_output=out, token_counting="exact",
                            usage_breakdown=True, prompt_caching="explicit+auto", cache_ttls=("5m", "1h"), min_cacheable_tokens=512,
                            max_cache_breakpoints=4, native_compaction=True, context_editing=True, deferred_tools=True,
                            structured_output=True, pricing_key="anthropic")

    # ------------------------------------------------------------ request mapping
    def body(self, request, for_count=False):
        tools = [{"name": t["name"], "description": t["description"], "input_schema": t["schema"]} for t in request.tools]
        system = [{"type": "text", "text": request.system}]
        messages = [{"role": m["role"], "content": [self._block(b) for b in m["content"]]} for m in request.messages]
        body = {"model": self.model, "system": system, "messages": messages}
        if tools:
            body["tools"] = tools
        if for_count:
            return body
        body["max_tokens"] = request.max_output
        mode = request.cache.get("mode")
        if mode == "auto":
            body["cache_control"] = {"type": "ephemeral"}
        elif mode == "explicit":
            cc = {"type": "ephemeral"} if request.cache.get("stable_ttl", "5m") == "5m" else {"type": "ephemeral", "ttl": "1h"}
            system[-1]["cache_control"] = cc  # end of the stable prefix (tools + system): reused across sessions
            if request.cache.get("rolling") and messages:
                last = messages[-1]["content"][-1]
                last["cache_control"] = {"type": "ephemeral"}
        if request.context_edits:
            body["context_management"] = {"edits": request.context_edits}
        return body

    @staticmethod
    def _block(b):
        if b["type"] == "text":
            return {"type": "text", "text": b["text"]}
        if b["type"] == "tool_use":
            return {"type": "tool_use", "id": b["id"], "name": b["name"], "input": b.get("input") or {}}
        if b["type"] == "tool_result":
            return {"type": "tool_result", "tool_use_id": b["tool_use_id"], "content": b["content"], "is_error": bool(b.get("is_error"))}
        raise ValueError(f"unknown block type {b['type']}")

    @staticmethod
    def usage(u):
        cc = u.get("cache_creation") or {}
        return Usage(uncached_input=u.get("input_tokens", 0) or 0, cache_write=u.get("cache_creation_input_tokens", 0) or 0,
                     cache_read=u.get("cache_read_input_tokens", 0) or 0, output=u.get("output_tokens", 0) or 0,
                     cache_write_1h=cc.get("ephemeral_1h_input_tokens", 0) or 0)

    @staticmethod
    def content(blocks):
        out = []
        for b in blocks or []:
            if b.get("type") == "text":
                out.append({"type": "text", "text": b.get("text", "")})
            elif b.get("type") == "tool_use":
                out.append({"type": "tool_use", "id": b["id"], "name": b["name"], "input": b.get("input") or {}})
        return out

    # ------------------------------------------------------------ transport
    def _post(self, path, body, beta=None):
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderError("ANTHROPIC_API_KEY is not set; orchestrated mode needs the user's own API key", retryable=False)
        headers = {"x-api-key": key, "anthropic-version": API_VERSION, "content-type": "application/json"}
        if beta:
            headers["anthropic-beta"] = beta
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:300]
            raise ProviderError(f"HTTP {e.code}: {msg}", status=e.code, retryable=e.code in self.capabilities.retryable_status,
                                maybe_billed=False) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # the request may have reached the provider: the budget counts its worst case
            raise ProviderError(f"transport error: {e}", retryable=True, maybe_billed=True) from None

    def count_tokens(self, request):
        beta = "context-management-2025-06-27" if request.context_edits else None
        body = self.body(request, for_count=True)
        if request.context_edits:
            body["context_management"] = {"edits": request.context_edits}
        return int(self._post("/v1/messages/count_tokens", body, beta)["input_tokens"])

    def create(self, request):
        beta = "context-management-2025-06-27" if request.context_edits else None
        j = self._post("/v1/messages", self.body(request), beta)
        return ModelResponse(content=self.content(j.get("content")), stop_reason=j.get("stop_reason") or "end_turn",
                             usage=self.usage(j.get("usage") or {}), raw_usage=j.get("usage") or {}, request_id=j.get("id", ""))
