"""Offline preflight budget using the pinned official DeepSeek V4.1 reference.

The cloud service's reported usage remains authoritative. This module gates an
application budget estimate; it does not claim a server-enforced context limit.
No request data is shortened, no environment files are read, and no network is
used. Official sources and asset checksums are in vendor/deepseek/provenance.json.
"""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from tokenizers import Tokenizer

from .vendor.deepseek.encoding import encode_messages


_ASSETS = Path(__file__).parent / "vendor" / "deepseek"


class ContextBudgetError(ValueError):
    """The request cannot be admitted by the configured preflight policy."""

    def __init__(self, message: str, metadata: dict | None = None):
        super().__init__(message)
        self.metadata = metadata or {}


@lru_cache(maxsize=1)
def _counters() -> tuple[Tokenizer, Tokenizer, dict]:
    provenance = json.loads((_ASSETS / "provenance.json").read_text(encoding="utf-8"))
    for record in provenance["files"]:
        actual = hashlib.sha256((_ASSETS / record["file"]).read_bytes()).hexdigest()
        if actual != record["sha256"]:
            raise ContextBudgetError(f"Pinned tokenizer asset checksum mismatch: {record['file']}")
    text = (_ASSETS / "tokenizer.json").read_text(encoding="utf-8")
    regular = Tokenizer.from_str(text)
    # Literal control-token spellings in user data must not make the serialized
    # guard artificially cheap. The template counter still recognizes controls.
    plain_config = json.loads(text)
    plain_config["added_tokens"] = []
    plain = Tokenizer.from_str(json.dumps(plain_config, ensure_ascii=False))
    for tokenizer in (regular, plain):
        tokenizer.no_truncation()
        tokenizer.no_padding()
    return regular, plain, provenance


def _render(payload: dict) -> str:
    messages = deepcopy(payload.get("messages"))
    if not isinstance(messages, list) or not messages:
        raise ContextBudgetError("Context budgeting requires a non-empty messages list.")
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {"system", "user", "assistant", "tool"}:
            raise ContextBudgetError("Unsupported message structure for text context budgeting.")
        if message.get("content") is not None and not isinstance(message["content"], str):
            raise ContextBudgetError("Only text messages are supported by this context budget; images/files need a separate counter.")
        if "content_blocks" in message:
            raise ContextBudgetError("content_blocks are unsupported by this text-only context budget.")
    # The official reference expects request-level definitions on the first
    # system message. Synthesize an empty one only in the local counting copy.
    if messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": ""})
    if payload.get("tools"):
        messages[0]["tools"] = deepcopy(payload["tools"])
    if payload.get("response_format"):
        messages[0]["response_format"] = deepcopy(payload["response_format"])
    thinking = payload.get("thinking") or {}
    effort = payload.get("reasoning_effort")
    thinking_enabled = thinking.get("type") != "disabled" if thinking else effort != "none"
    return encode_messages(messages, thinking_mode="thinking" if thinking_enabled else "chat",
                           drop_thinking=False, reasoning_effort=effort if thinking_enabled else None)


def enforce_budget(payload: dict, context_window: int, max_tokens: int) -> dict:
    """Check messages + tools + framing allowance + full output reservation.

    ``context_window=0`` explicitly disables the local policy. Otherwise both
    limits must be positive integers; max_tokens must match the outgoing request
    when present. An excess raises ContextBudgetError with count metadata, never
    with the source text. The caller should additionally audit actual API usage.
    """
    if type(context_window) is not int or context_window < 0:
        raise ContextBudgetError("context_window must be a non-negative integer.")
    if type(max_tokens) is not int or max_tokens <= 0:
        raise ContextBudgetError("max_tokens must be a positive integer.")
    if not isinstance(payload, dict):
        raise ContextBudgetError("payload must be a request object.")
    if "max_tokens" in payload and (type(payload["max_tokens"]) is not int or payload["max_tokens"] != max_tokens):
        raise ContextBudgetError("Output reservation must match payload.max_tokens.")
    if context_window == 0:
        return {"enabled": False, "context_window": 0, "output_reserve": max_tokens,
                "method": "disabled", "estimate_only": True, "hard_cap": False}
    try:
        regular, plain, provenance = _counters()
        rendered = _render(payload)
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        rendered_tokens = len(regular.encode(rendered, add_special_tokens=False).ids)
        serialized_tokens = len(plain.encode(serialized, add_special_tokens=False).ids)
    except ContextBudgetError:
        raise
    except Exception as exc:
        # Do not echo request data through tokenizer/renderer exception messages.
        raise ContextBudgetError(f"Context budget could not count this request ({type(exc).__name__}); request not sent.") from exc
    base = max(rendered_tokens, serialized_tokens)
    margin = math.ceil(base * 0.10) + 128
    prompt_estimate = base + margin
    total = prompt_estimate + max_tokens
    metadata = {
        "enabled": True, "context_window": context_window, "output_reserve": max_tokens,
        "method": "deepseek_v41_reference_plus_serialized_guard", "estimate_only": True,
        "is_exact": False, "hard_cap": False, "provider_usage_authoritative": True,
        "rendered_prompt_tokens": rendered_tokens, "serialized_request_tokens": serialized_tokens,
        "safety_margin_tokens": margin, "prompt_token_estimate": prompt_estimate,
        "estimated_total_tokens": total, "remaining_tokens": context_window - total,
        "within_budget": total <= context_window,
        "includes": ["messages", "tool_schemas", "response_format", "framing_allowance", "output_reserve"],
        "tokenizer_revision": provenance["revision"],
        "tokenizer_sha256": next(record["sha256"] for record in provenance["files"] if record["file"] == "tokenizer.json"),
        "note": "Local reference estimate; cloud prompt formatting may differ. Actual API usage must be audited; no source text was truncated.",
    }
    if total > context_window:
        raise ContextBudgetError(
            f"Context budget exceeded: estimated input {prompt_estimate} + reserved output {max_tokens} "
            f"= {total} > application budget {context_window}; request not sent and no content truncated.", metadata)
    return metadata


__all__ = ["ContextBudgetError", "enforce_budget"]
