"""One place where SUNO calls Claude.

Every call: Claude Opus 5.5, adaptive thinking, a JSON-schema structured output
from schemas/, a cached stable prefix (prompt file + roster/taxonomy), and the
server-side refusal fallback. The response is checked against the same schema
in code before anyone uses it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import jsonschema
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# List prices per million tokens (claude-opus-5-5, Oct 2026): input, output, cache write, cache read.
PRICE_PER_MTOK = {"input": 4.00, "output": 20.00, "cache_write": 5.00, "cache_read": 0.20}


class ClaudeOutputError(RuntimeError):
    """Claude declined, was cut off, or returned something that fails the schema."""


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0

    def add(self, u) -> None:
        self.input_tokens += u.input_tokens
        self.output_tokens += u.output_tokens
        self.cache_write_tokens += u.cache_creation_input_tokens or 0
        self.cache_read_tokens += u.cache_read_input_tokens or 0

    @property
    def usd(self) -> float:
        p = PRICE_PER_MTOK
        return (self.input_tokens * p["input"] + self.output_tokens * p["output"]
                + self.cache_write_tokens * p["cache_write"] + self.cache_read_tokens * p["cache_read"]) / 1e6


def load_prompt(name: str) -> str:
    return (ROOT / "prompts" / name).read_text()


def load_schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / name).read_text())


_client = None


def client():
    """The SDK is imported on first use: it is the slowest import, and a free 0.1-CPU instance
    should answer its health check before anyone has asked Claude anything."""
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    return _client


def call_structured(*, prompt: str, schema: dict, stable_context: str, request: str,
                    effort: str = "high", max_tokens: int = 32000, usage: Usage | None = None) -> dict:
    """Ask Claude for JSON matching `schema`. `stable_context` is cached across calls."""
    with client().beta.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        system=[
            {"type": "text", "text": prompt},
            {"type": "text", "text": stable_context, "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{"role": "user", "content": request}],
        betas=[FALLBACK_BETA],
        fallbacks="default",
    ) as stream:
        resp = stream.get_final_message()
    if usage is not None:
        usage.add(resp.usage)
    if resp.stop_reason == "refusal":
        raise ClaudeOutputError(f"declined ({getattr(resp.stop_details, 'category', None)})")
    if resp.stop_reason == "max_tokens":
        raise ClaudeOutputError("output cut off at max_tokens")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        data = json.loads(text)
        jsonschema.validate(data, schema)
    except (json.JSONDecodeError, jsonschema.ValidationError) as e:
        raise ClaudeOutputError(f"schema check failed: {e}") from e
    return data
