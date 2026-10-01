"""Provider adapters: request mapping, cache placement, usage normalization, credential handling (no network)."""
import io
import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ross.core.budget import Budget, BudgetExceeded, Governor  # noqa: E402
from ross.orchestration.profile import Profile, system_prompt  # noqa: E402
from ross.orchestration.tools import SCHEMAS  # noqa: E402
from ross.providers.anthropic import AnthropicProvider  # noqa: E402
from ross.providers.base import ModelRequest, ProviderError  # noqa: E402
from ross.providers.openai import OpenAIProvider  # noqa: E402

KEY = "anthropic-unit-test-credential-000111"


def req(mode="explicit"):
    msgs = [{"role": "user", "content": [{"type": "text", "text": "fix it"}]},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "run", "input": {"command": "ls"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "a.py", "is_error": False}]}]
    cache = {"mode": mode, "stable_ttl": "5m", "rolling": True} if mode == "explicit" else {"mode": mode}
    return ModelRequest(system=system_prompt(Profile.ross()), tools=SCHEMAS, messages=msgs, max_output=1000, cache=cache)


class Fake:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return io.BytesIO(json.dumps(self.payload).encode())

    def __exit__(self, *a):
        return False


class Anthropic(unittest.TestCase):
    def test_explicit_cache_breakpoints_and_auto_mode(self):
        p = AnthropicProvider()
        b = p.body(req("explicit"))
        self.assertEqual(b["system"][-1]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(b["messages"][-1]["content"][-1]["cache_control"], {"type": "ephemeral"})
        self.assertNotIn("cache_control", b)
        a = p.body(req("auto"))
        self.assertEqual(a["cache_control"], {"type": "ephemeral"})
        self.assertNotIn("cache_control", a["system"][-1])
        self.assertEqual([t["name"] for t in b["tools"]], ["inspect", "apply_patch", "run", "artifact"])
        self.assertNotIn("max_tokens", p.body(req(), for_count=True))

    def test_usage_normalization(self):
        u = AnthropicProvider.usage({"input_tokens": 10, "cache_creation_input_tokens": 300, "cache_read_input_tokens": 2000,
                                     "output_tokens": 50, "cache_creation": {"ephemeral_1h_input_tokens": 100}})
        self.assertEqual((u.uncached_input, u.cache_write, u.cache_read, u.output, u.cache_write_1h, u.total), (10, 300, 2000, 50, 100, 2360))

    def test_create_and_count_with_key_from_env_only(self):
        sent = []

        def fake_open(r, timeout=None):
            sent.append(r)
            if r.full_url.endswith("count_tokens"):
                return Fake({"input_tokens": 1234})
            return Fake({"id": "msg_1", "stop_reason": "tool_use", "usage": {"input_tokens": 5, "output_tokens": 7},
                         "content": [{"type": "text", "text": "hi"}, {"type": "tool_use", "id": "x", "name": "run", "input": {"command": "ls"}}]})
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": KEY}), mock.patch("urllib.request.urlopen", fake_open):
            p = AnthropicProvider()
            self.assertEqual(p.count_tokens(req()), 1234)
            r = p.create(req())
        self.assertEqual(r.stop_reason, "tool_use")
        self.assertEqual(r.content[1]["name"], "run")
        self.assertEqual(sent[1].headers["X-api-key"], KEY)
        self.assertTrue(sent[1].full_url.startswith("https://api.anthropic.com/v1/messages"))
        self.assertNotIn(KEY, sent[1].data.decode())  # never in the request body

    def test_missing_key_and_host_proxy_not_borrowed(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_BASE_URL": "http://host-proxy.invalid"}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            p = AnthropicProvider()
            self.assertEqual(p.base, "https://api.anthropic.com")
            with self.assertRaises(ProviderError) as e:
                p.create(req())
            self.assertFalse(e.exception.retryable)

    def test_errors_classified_for_retry_and_budget(self):
        def http429(r, timeout=None):
            raise urllib.error.HTTPError(r.full_url, 429, "rate", {}, io.BytesIO(b"slow down"))

        def drop(r, timeout=None):
            raise urllib.error.URLError("reset")
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": KEY}):
            with mock.patch("urllib.request.urlopen", http429), self.assertRaises(ProviderError) as e:
                AnthropicProvider().create(req())
            self.assertTrue(e.exception.retryable and not e.exception.maybe_billed)
            with mock.patch("urllib.request.urlopen", drop), self.assertRaises(ProviderError) as e:
                AnthropicProvider().create(req())
            self.assertTrue(e.exception.maybe_billed)
            self.assertNotIn(KEY, str(e.exception))


class OpenAI(unittest.TestCase):
    def test_static_mapping_usage_and_no_live_calls(self):
        p = OpenAIProvider()
        b = p.body(req())
        self.assertEqual(b["instructions"], req().system)
        self.assertEqual([i.get("type") for i in b["input"]], [None, "function_call", "function_call_output"])
        self.assertEqual(b["tools"][0]["type"], "function")
        u = p.usage({"input_tokens": 1000, "output_tokens": 20, "input_tokens_details": {"cached_tokens": 800, "cache_write_tokens": 100}})
        self.assertEqual((u.uncached_input, u.cache_read, u.cache_write, u.output), (100, 800, 100, 20))
        with self.assertRaises(ProviderError):
            p.create(req())
        with self.assertRaises(BudgetExceeded):  # no verified pricing: no guaranteed dollar cap
            Governor(Budget(max_usd=3), "openai", p.model)


if __name__ == "__main__":
    unittest.main()
