# Provider implementation facts

Verified once from official documentation on 2026-10-01. Only facts the
orchestrator uses. Re-verify before relying on them after this date.

## Anthropic (platform.claude.com)

- Prompt caching: `cache_control: {"type": "ephemeral"}` (5 minute TTL) or
  `{"type": "ephemeral", "ttl": "1h"}` on tool, system or message blocks;
  at most 4 breakpoints; prefix order tools, system, messages; a change
  invalidates its level and everything after it. Top-level `cache_control`
  enables automatic caching (breakpoint on the last cacheable block). Reads
  look back at most 20 blocks from a breakpoint. Minimum cacheable prompt
  for Sonnet 5.5: 512 tokens.
- Usage: `input_tokens` (after the last breakpoint),
  `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`,
  `cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens`.
- Price multipliers on base input: 5m write 1.25x, 1h write 2x, read 0.1x.
  Sonnet 5.5 per million tokens: input $2, output $10, 5m write $2.50, 1h
  write $4, read $0.20.
- Token counting: `POST /v1/messages/count_tokens` (model, system, messages,
  tools); returns `input_tokens`; free, separately rate limited; an estimate.
- Context editing: beta `context-management-2025-06-27`, request
  `context_management.edits` with `clear_tool_uses_20250919` (trigger, keep,
  clear_at_least, exclude_tools, clear_tool_inputs). Clearing invalidates the
  cached prefix from the cleared point.
- Compaction: server-side `compact_20260112`, beta. Not used by default.
- Tool search: `tool_search_tool_regex_20251119` / `_bm25_20251119` with
  `defer_loading: true`; recommended at 10 or more tools or more than 10k
  tokens of definitions. Not worth it for a 4-tool surface.

## OpenAI (developers.openai.com)

- Prompt caching is automatic from 1,024 input tokens; optional
  `prompt_cache_key`; usage in `usage.input_tokens_details.cached_tokens` and
  `cache_write_tokens`; GPT-5.6 and later: read 0.1x, write 1.25x; explicit
  breakpoints via `prompt_cache_breakpoint: {"mode": "explicit"}` with
  `prompt_cache_options.mode = "explicit"`.
- Input token counting: `POST /v1/responses/input_tokens`, returns
  `input_tokens`.
- Compaction: `context_management: [{"type": "compaction", "compact_threshold": N}]`
  in the Responses API, or stateless `POST /responses/compact`; the compaction
  item is opaque and must be passed back unmodified.
