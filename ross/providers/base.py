"""Normalized provider interface. Core logic asks capabilities; it never branches on provider names."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from ..core.models import Usage


@dataclass
class Capabilities:
    provider: str
    model: str
    context_window: int
    max_output: int
    token_counting: str          # "exact" (provider endpoint) or "estimate"
    usage_breakdown: bool        # uncached / cache write / cache read / output reported separately
    prompt_caching: str          # "explicit+auto", "auto" or "none"
    cache_ttls: tuple = ("5m",)
    min_cacheable_tokens: int = 1024
    max_cache_breakpoints: int = 0
    native_compaction: bool = False
    context_editing: bool = False
    deferred_tools: bool = False
    structured_output: bool = False
    pricing_key: Optional[str] = None
    retryable_status: tuple = (429, 500, 502, 503, 529)


@dataclass
class ModelRequest:
    """system: stable prefix text; dynamic context goes in messages. tools: [{name, description, schema}] in a stable order."""
    system: str
    tools: list
    messages: list
    max_output: int = 4096
    cache: dict = field(default_factory=lambda: {"mode": "auto"})  # auto | explicit (stable_ttl, rolling) | none
    context_edits: Optional[list] = None  # provider-native context management, only when the policy enables it


@dataclass
class ModelResponse:
    content: list          # normalized blocks: {"type": "text", "text"} | {"type": "tool_use", "id", "name", "input"}
    stop_reason: str       # end_turn | tool_use | max_tokens | refusal | error
    usage: Usage
    raw_usage: dict = field(default_factory=dict)
    request_id: str = ""


class ProviderError(Exception):
    def __init__(self, message, status=None, retryable=False, maybe_billed=False):
        super().__init__(message)
        self.status, self.retryable, self.maybe_billed = status, retryable, maybe_billed


def estimate_tokens(request):
    """Conservative local estimate (about 3 characters per token) used when no exact counter exists."""
    import json
    size = len(request.system) + len(json.dumps(request.tools)) + len(json.dumps(request.messages))
    return size // 3 + 16


class Provider(ABC):
    @property
    @abstractmethod
    def capabilities(self) -> Capabilities:
        ...

    def count_tokens(self, request) -> int:
        """Most accurate input-token count available; adapters with an exact endpoint override this."""
        return estimate_tokens(request)

    @abstractmethod
    def create(self, request) -> ModelResponse:
        ...
