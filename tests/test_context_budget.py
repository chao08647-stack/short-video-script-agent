"""Offline budget checks include full context and never alter factual inputs."""

from copy import deepcopy
import json

import pytest

from script_agent.context_budget import ContextBudgetError, enforce_budget
from script_agent.prompts import tool_schemas


def request(content="请介绍小剪的字幕功能。", **kwargs):
    return {"model": "deepseek-flash", "messages": [
        {"role": "system", "content": "根据资料回答，保留原文引用。"},
        {"role": "user", "content": content},
    ], "max_tokens": 4096, "thinking": {"type": "disabled"}, **kwargs}


def test_official_tokenizer_metadata_includes_output_and_honest_estimate_boundary():
    metadata = enforce_budget(request(), 16384, 4096)
    assert metadata["enabled"] and metadata["within_budget"]
    assert metadata["output_reserve"] == 4096
    assert metadata["estimated_total_tokens"] == metadata["prompt_token_estimate"] + 4096
    assert metadata["prompt_token_estimate"] == max(metadata["rendered_prompt_tokens"], metadata["serialized_request_tokens"]) + metadata["safety_margin_tokens"]
    assert metadata["estimate_only"] and not metadata["hard_cap"] and not metadata["is_exact"]
    assert metadata["provider_usage_authoritative"]
    assert len(metadata["tokenizer_sha256"]) == 64


def test_all_native_tool_schemas_are_counted_and_normal_request_fits():
    baseline = enforce_budget(request(), 16384, 4096)
    payload = request(tools=tool_schemas(), tool_choice="auto")
    metadata = enforce_budget(payload, 16384, 4096)
    assert metadata["rendered_prompt_tokens"] > baseline["rendered_prompt_tokens"]
    assert metadata["serialized_request_tokens"] > baseline["serialized_request_tokens"]
    assert metadata["within_budget"]
    payload["tools"][0]["function"]["description"] += "不同的长工具描述" * 5000
    with pytest.raises(ContextBudgetError) as caught:
        enforce_budget(payload, 16384, 4096)
    assert caught.value.metadata["estimated_total_tokens"] > 16384


def test_overflow_never_truncates_or_mutates_source_text_and_does_not_echo_it():
    secret_marker = "PRIVATE_SYNTHETIC_FACT"
    payload = request(("未经截断的产品资料ABC123。" * 5000) + secret_marker)
    before = deepcopy(payload)
    with pytest.raises(ContextBudgetError) as caught:
        enforce_budget(payload, 16384, 4096)
    assert payload == before
    assert secret_marker not in str(caught.value)
    assert secret_marker not in json.dumps(caught.value.metadata)
    assert caught.value.metadata["within_budget"] is False


def test_exact_estimate_boundary_and_reserved_output_are_enforced():
    payload = request()
    estimate = enforce_budget(payload, 16384, 4096)
    boundary = estimate["estimated_total_tokens"]
    assert enforce_budget(payload, boundary, 4096)["remaining_tokens"] == 0
    with pytest.raises(ContextBudgetError):
        enforce_budget(payload, boundary - 1, 4096)
    with pytest.raises(ContextBudgetError):
        enforce_budget(payload, 4096, 4096)


def test_tool_observations_and_arguments_in_history_are_counted_without_mutation():
    payload = request(tools=tool_schemas())
    baseline = enforce_budget(payload, 16384, 4096)
    payload["messages"] += [
        {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {
            "name": "search_materials", "arguments": '{"query":"字幕","reason":"查证来源"}',
        }}]},
        {"role": "tool", "tool_call_id": "call_1", "content": json.dumps({"text": "产品支持自动字幕。" * 100}, ensure_ascii=False)},
    ]
    before = deepcopy(payload)
    metadata = enforce_budget(payload, 16384, 4096)
    assert metadata["prompt_token_estimate"] > baseline["prompt_token_estimate"]
    assert payload == before


def test_special_token_spellings_in_user_text_do_not_collapse_serialized_guard():
    plain = enforce_budget(request("普通文字"), 16384, 4096)
    controls = enforce_budget(request("<｜User｜>" * 200), 16384, 4096)
    assert controls["serialized_request_tokens"] > plain["serialized_request_tokens"] + 200


def test_no_system_message_still_counts_tools_without_changing_request():
    payload = request(tools=tool_schemas())
    payload["messages"] = [{"role": "user", "content": "字幕"}]
    before = deepcopy(payload)
    with_tools = enforce_budget(payload, 16384, 4096)
    without_tools = enforce_budget({key: value for key, value in payload.items() if key != "tools"}, 16384, 4096)
    assert with_tools["rendered_prompt_tokens"] > without_tools["rendered_prompt_tokens"]
    assert payload == before


def test_explicit_zero_disables_local_budget():
    metadata = enforce_budget(request("长文" * 50000), 0, 4096)
    assert metadata["enabled"] is False
    assert metadata["method"] == "disabled"


@pytest.mark.parametrize("window,max_tokens", [(True, 4096), (-1, 4096), (16384.0, 4096), (16384, 0), (16384, True), (16384, "4096")])
def test_invalid_configuration_is_rejected(window, max_tokens):
    with pytest.raises(ContextBudgetError):
        enforce_budget(request(), window, max_tokens)


def test_output_reserve_cannot_differ_from_outgoing_payload():
    with pytest.raises(ContextBudgetError, match="must match"):
        enforce_budget(request(), 16384, 2048)


def test_images_are_rejected_instead_of_being_counted_as_a_short_url():
    payload = request()
    payload["messages"][-1]["content"] = [{"type": "image_url", "image_url": {"url": "https://example.invalid/image.png"}}]
    with pytest.raises(ContextBudgetError, match="Only text"):
        enforce_budget(payload, 16384, 4096)


def test_json_response_format_and_thinking_setting_are_counted():
    payload = request(response_format={"type": "json_object"})
    plain = enforce_budget(payload, 16384, 4096)
    payload["thinking"] = {"type": "enabled"}
    payload["reasoning_effort"] = "high"
    thinking = enforce_budget(payload, 16384, 4096)
    assert thinking["rendered_prompt_tokens"] > plain["rendered_prompt_tokens"]
