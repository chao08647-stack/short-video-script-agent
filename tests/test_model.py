import json
import hashlib

import httpx
import pytest

from script_agent.model import ContextLimitError, ModelClient, ModelError, Settings
from script_agent.prompts import build_messages, skill_instructions, state_prompt, system_prompt, tool_schemas, tools_for_phase, tools_for_state


@pytest.fixture(autouse=True)
def isolate_model_configuration(monkeypatch):
    """Never read workstation credentials when running simulated HTTP tests."""
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda **_: False)
    for name in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "LLM_TIMEOUT_SECONDS", "LLM_MAX_TOKENS",
                 "LLM_ACTION_PROTOCOL", "LLM_THINKING", "LLM_CONTEXT_WINDOW"):
        monkeypatch.delenv(name, raising=False)


def response(message, **extra):
    return httpx.Response(200, json={"choices": [{"message": message, "finish_reason": "stop"}], **extra})


def test_native_tool_protocol_and_no_key_header():
    def handle(request):
        assert request.url.path == "/v1/chat/completions"
        assert "authorization" not in request.headers
        body = json.loads(request.content)
        assert body["tool_choice"] == "auto"
        assert body["parallel_tool_calls"] is False
        assert "response_format" not in body
        assert "thinking" not in body
        return response({"role": "assistant", "content": None, "reasoning": "private", "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "estimate_duration", "arguments": "{}"}}]}, usage={"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15, "reasoning": "private"})

    with ModelClient(Settings(), transport=httpx.MockTransport(handle)) as client:
        result = client.chat([{"role": "user", "content": "test"}], tool_schemas())
        assert result["tool_calls"][0]["function"]["name"] == "estimate_duration"
        assert "reasoning" not in result
        assert client.last_usage == {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}
        assert client.request_count == client.last_request_count == 1


def test_http_failure_is_visible_redacted_and_not_retried():
    seen = []

    def handle(request):
        seen.append(request)
        assert request.headers["authorization"] == "Bearer test-secret-123"
        return httpx.Response(400, json={"error": {"message": "Rejected key test-secret-123; Bearer other-secret"}})

    with ModelClient(Settings(api_key="test-secret-123"), transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ModelError) as error:
            client.chat([{"role": "user", "content": "test"}])
        assert "HTTP 400" in str(error.value)
        assert "test-secret-123" not in str(error.value)
        assert "other-secret" not in str(error.value)
        assert len(seen) == client.request_count == 1


@pytest.mark.parametrize("payload", [
    {},
    {"choices": []},
    {"choices": [{"message": {"role": "assistant", "content": "partial"}, "finish_reason": "length"}]},
    {"choices": [{"message": {"role": "assistant", "content": None}}]},
])
def test_invalid_completion_never_succeeds(payload):
    with ModelClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
        with pytest.raises(ModelError):
            client.chat([])


MATERIALS = [{"source_id": "P01", "text": "支持自动生成字幕。"}]
SCRIPT = {"title": "字幕教程", "scenes": [], "claims": [{"text": "支持自动生成字幕", "source_id": "P01", "quote": "支持自动生成字幕。", "scene_id": "S1"}]}


def verification_client(report):
    def handle(request):
        body = json.loads(request.content)
        assert "tools" not in body
        assert "独立" in body["messages"][0]["content"]
        return response({"role": "assistant", "content": "```json\n" + json.dumps(report, ensure_ascii=False) + "\n```"})
    return ModelClient(transport=httpx.MockTransport(handle))


def test_verifier_accepts_supported_claim_and_counts_request():
    report = {"passed": True, "issues": [], "claims": [{**SCRIPT["claims"][0], "status": "supported", "reason": "原文直接支持"}]}
    with verification_client(report) as client:
        result = client.verify_script(SCRIPT, MATERIALS)
        assert result["passed"] is True
        assert client.request_count == 1


def test_verifier_requests_full_script_ui_and_independent_citation_audit():
    """Assert the sent contract, not a claim that a real judge follows it."""
    script = {
        "title": "字幕教程",
        "scenes": [{"scene_id": "S1", "visual": "真实录屏：点击导出按钮，进度条走完。",
                    "narration": "自动生成，再手动改一改", "subtitle": "", "source_ids": ["P01", "P02"]}],
        "claims": [
            {"text": "自动生成，再手动改一改", "source_id": "P01", "quote": "支持自动生成字幕。", "scene_id": "S1"},
            {"text": "手动改一改", "source_id": "P02", "quote": "支持手动修改字幕。", "scene_id": "S1"},
        ],
    }
    materials = MATERIALS + [{"source_id": "P02", "text": "支持手动修改字幕。"}]
    report = {
        "passed": False,
        "issues": [{"code": "missing_citation", "message": "visual 中导出按钮和进度条无原文支持", "scene_id": "S1"}],
        "claims": [
            {**script["claims"][0], "status": "unsupported", "reason": "P01 不独立支持手动修改，应拆开引用"},
            {**script["claims"][1], "status": "supported", "reason": "P02 支持手动修改"},
            {"text": script["scenes"][0]["visual"], "source_id": "", "quote": "", "status": "unsupported", "reason": "未声明的具体 UI 和导出操作缺少来源"},
        ],
    }

    def handle(request):
        body = json.loads(request.content)
        instructions = body["messages"][0]["content"]
        assert "不能只检查claims清单" in instructions
        assert "标题、画面visual、旁白narration、字幕subtitle" in instructions
        assert all(term in instructions for term in ("按钮", "进度条", "滑块", "导出", "不得把未知UI写成真实录屏"))
        assert "每条claim的完整text必须独立由该条source_id的原文和quote支持" in instructions
        assert "不能借其他claim或其他来源补齐复合事实" in instructions
        assert "不能因同镜头另有P02就把该条判为supported" in instructions
        assert "抽象示意镜头" in instructions
        assert "写“示意”不能豁免未证实的功能、操作或效果承诺" in instructions
        submitted = json.loads(body["messages"][1]["content"])
        assert submitted["script"] == script
        assert {item["source_id"] for item in submitted["materials"]} == {"P01", "P02"}
        assert "tools" not in body
        return response({"role": "assistant", "content": json.dumps(report, ensure_ascii=False)})

    with ModelClient(Settings(), transport=httpx.MockTransport(handle)) as client:
        result = client.verify_script(script, materials)
        assert result["passed"] is False
        assert [claim["status"] for claim in result["claims"]] == ["unsupported", "supported", "unsupported"]
        assert result["issues"][0]["scene_id"] == "S1"
        assert client.request_count == 1


def test_planner_prompt_distinguishes_illustrations_from_unverified_product_ui():
    instructions = system_prompt([])
    assert "每条 claim 的完整 text 必须独立由自己的 source_id 和 quote 支持" in instructions
    assert "不能借其他 claim 或来源补齐复合事实" in instructions
    assert "分别截取“自动生成”和“手动改一改”引用各自原文" in instructions
    assert "包括未在 claims 声明的产品操作和具体 UI 结构" in instructions
    assert all(term in instructions for term in ("按钮", "进度条", "滑块", "导出"))
    assert "不能把未知 UI 写成真实录屏" in instructions
    assert "抽象示意动画：字幕文字浮现" in instructions
    assert "加“示意”标签不能豁免未证实的功能、操作和承诺" in instructions


def test_verifier_cannot_pass_omitted_claims():
    with verification_client({"passed": True, "issues": [], "claims": []}) as client:
        result = client.verify_script(SCRIPT, MATERIALS)
        assert result["passed"] is False
        assert result["issues"][0]["code"] == "unchecked_claim"


@pytest.mark.parametrize("status,quote", [("uncertain", "支持自动生成字幕。"), ("supported", "提高效率80%。")])
def test_verifier_cannot_pass_uncertainty_or_fabricated_quote(status, quote):
    report = {"passed": True, "issues": [], "claims": [{**SCRIPT["claims"][0], "quote": quote, "status": status, "reason": "需要补证"}]}
    with verification_client(report) as client:
        assert client.verify_script(SCRIPT, MATERIALS)["passed"] is False


def test_verifier_malformed_json_is_an_error_not_a_pass():
    with ModelClient(transport=httpx.MockTransport(lambda _: response({"content": "looks fine"}))) as client:
        with pytest.raises(ModelError, match="valid JSON"):
            client.verify_script(SCRIPT, MATERIALS)


def test_state_context_excludes_unretrieved_materials():
    context = state_prompt({"materials": [{"text": "DO_NOT_EXPOSE"}], "retrieved_materials": [{"text": "visible"}], "loaded_skills": {}})
    assert "DO_NOT_EXPOSE" not in context
    assert "visible" in context


def test_tool_schema_allows_only_current_script_checks():
    schemas = {tool["function"]["name"]: tool["function"] for tool in tool_schemas()}
    assert len(schemas) == 10
    for tool in ("estimate_duration", "check_rules"):
        properties = schemas[tool]["parameters"]["properties"]
        assert "reason" in properties
        assert not {"script", "estimated_seconds", "target_seconds"}.intersection(properties)
    assert "fields" in schemas["ask_user"]["parameters"]["properties"]
    assert set(schemas["ask_user"]["parameters"]["properties"]["fields"]["items"]["enum"]) == {"topic", "audience", "platform", "target_seconds", "style"}


def test_settings_rejects_url_embedded_secrets():
    with pytest.raises(ModelError, match="credentials"):
        Settings(base_url="https://user:secret@example.com/v1")


def test_phase_schemas_keep_relevant_controls_only():
    direction = {t["function"]["name"] for t in tools_for_phase("direction")}
    final = {t["function"]["name"] for t in tools_for_phase("final")}
    assert "submit_direction" in direction and "submit_script" not in direction
    assert "submit_script" in final and "submit_direction" not in final
    assert {"request_review", "ask_user", "finish_incomplete"}.issubset(direction & final)


def test_skill_body_and_examples_are_preserved_once():
    content = "---\nname: test-skill\ndescription: test\n---\n# 技能\n\n完整操作规则\n\n## 验证示例\n必须保留这个示例。"
    skill = {"name": "test-skill", "version": "1.0", "content": content}
    state = {"phase": "draft", "loaded_skills": {"test-skill": skill, "unused-skill": {"content": "OLD_BODY_SHOULD_NOT_REPEAT"}}, "last_loaded_skill": "test-skill", "messages": [
        {"role": "assistant", "content": None, "tool_calls": [{"id": "a", "type": "function", "function": {"name": "load_skill", "arguments": '{"name":"test-skill"}'}}]},
        {"role": "tool", "tool_call_id": "a", "content": json.dumps(skill, ensure_ascii=False)},
    ]}
    before = json.dumps(state, ensure_ascii=False)
    messages = build_messages(state, [])
    rendered = json.dumps(messages, ensure_ascii=False)
    assert rendered.count("必须保留这个示例") == 1
    # 32k context retains all previously loaded methods, once per body.
    assert rendered.count("OLD_BODY_SHOULD_NOT_REPEAT") == 1
    assert json.dumps(state, ensure_ascii=False) == before
    assert "完整操作规则" in skill_instructions(content)
    assert not skill_instructions(content).startswith("---")


@pytest.mark.parametrize("phase", ["direction", "draft", "final"])
def test_current_draft_not_truncated_and_latest_human_reply_kept(phase):
    narration = "这是完整的用户稿件。" * 100
    script = {"title": "测试稿", "scenes": [{"narration": narration}]}
    state = {"phase": phase, "script": script, "messages": [{"role": "user", "content": "人工补充：请保留结尾。"}]}
    messages = build_messages(state, [])
    assert narration in messages[1]["content"]
    assert any(m["content"] == "人工补充：请保留结尾。" for m in messages)
    assert "当前执行提示" in messages[-1]["content"]


def test_verification_includes_uncited_same_product_and_conflict_partners():
    materials = [
        {"source_id": "P01", "text": "功能说明", "keywords": ["字幕"]},
        {"source_id": "P02", "text": "限制A", "keywords": ["字幕"], "conflict_group": "g"},
        {"source_id": "P03", "text": "限制B", "keywords": ["旧制度"], "conflict_group": "g"},
        {"source_id": "H01", "text": "耳机说明", "keywords": ["耳机"]},
    ]
    script = {"title": "功能", "scenes": [{"source_ids": ["P01"]}], "claims": []}
    selected = ModelClient.verification_materials(script, materials)
    assert {m["source_id"] for m in selected} == {"P01", "P02", "P03"}
    assert all("keywords" not in m for m in selected)
    assert selected[1]["text"] == "限制A"


def test_json_action_protocol_is_explicit_and_preserves_observation():
    captured = []
    raw = '{"action":"search_materials","arguments":{"query":"字幕","reason":"查资料"}}'

    def handle(request):
        body = json.loads(request.content)
        captured.append(body)
        assert "tools" not in body and "tool_choice" not in body and "parallel_tool_calls" not in body
        response_format = body["response_format"]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["strict"] is True
        branches = response_format["json_schema"]["schema"]["anyOf"]
        assert len(branches) == len(tool_schemas())
        arguments_by_name = {
            branch["properties"]["action"]["const"]: branch["properties"]["arguments"]
            for branch in branches
        }
        assert arguments_by_name == {tool["function"]["name"]: tool["function"]["parameters"] for tool in tool_schemas()}
        assert all(branch["required"] == ["action", "arguments"] and branch["additionalProperties"] is False for branch in branches)
        assert '"arguments_schema"' in body["messages"][0]["content"]
        assert '"parameters"' not in body["messages"][0]["content"]
        assert all(m["role"] in {"system", "user", "assistant"} for m in body["messages"])
        assert all("tool_calls" not in m for m in body["messages"])
        assert all(m["role"] != "assistant" for m in body["messages"])
        observations = [json.loads(m["content"]) for m in body["messages"] if m["role"] == "user" and m["content"].startswith('{"observation"')]
        assert observations[0]["observation"]["result"] == {"matches": [], "error": "retry with another query"}
        assert observations[0]["observation"]["tool"] == "search_materials"
        assert observations[0]["observation"]["call_id"] == "old"
        return response({"role": "assistant", "content": raw, "reasoning": "not public"})

    history = [
        {"role": "system", "content": "test"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "old", "type": "function", "function": {"name": "search_materials", "arguments": '{"query":"old","reason":"try"}'}}]},
        {"role": "tool", "tool_call_id": "old", "content": '{"matches":[],"error":"retry with another query"}'},
    ]
    with ModelClient(Settings(action_protocol="json"), transport=httpx.MockTransport(handle)) as client:
        result = client.chat(history, tool_schemas())
        assert result["tool_calls"][0]["id"].startswith("json-")
        assert json.loads(result["tool_calls"][0]["function"]["arguments"])["query"] == "字幕"
        assert client.last_action_protocol == "json"
        assert client.last_public_response == raw
        assert client.last_response_metadata["adapter_generated_call_id"] is True
        assert client.last_response_metadata["max_tokens"] == 2048
        assert client.last_response_metadata["timeout_seconds"] == 60
        assert "not public" not in json.dumps(client.last_response_metadata)
        assert len(captured) == 1


@pytest.mark.parametrize("content", [
    '{"action":"delete_files","arguments":{}}',
    '{"action":"search_materials","arguments":[]}',
    '{"action":"search_materials","arguments":{"query":1,"reason":"test"}}',
    '{"action":"search_materials","arguments":{"query":"x"}}',
    '{"action":"search_materials","arguments":{"query":"x","reason":"test","extra":true}}',
    '{"action":"search_materials","arguments":{"query":"x","reason":"test"},"extra":true}',
    '解释：{"action":"search_materials","arguments":{"query":"x","reason":"test"}}',
    '{"action":"search_materials","arguments":{"query":"x","reason":"test"}} {}',
    '```json\n{"action":"search_materials","arguments":{"query":"x","reason":"test"}}',
    '{"action":"search_materials","action":"load_skill","arguments":{"name":"x","reason":"test"}}',
])
def test_json_protocol_rejects_invalid_actions_without_fallback(content):
    seen = []

    def handle(request):
        seen.append(request)
        return response({"role": "assistant", "content": content})

    with ModelClient(Settings(action_protocol="json"), transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ModelError, match="JSON action"):
            client.chat([], tool_schemas())
        assert len(seen) == 1
        assert client.last_public_response == content


def test_json_protocol_accepts_one_complete_fence():
    raw = '```json\n{"action":"estimate_duration","arguments":{"reason":"estimate"}}\n```'
    with ModelClient(Settings(action_protocol="json"), transport=httpx.MockTransport(lambda _: response({"content": raw}))) as client:
        result = client.chat([], tool_schemas())
        assert result["tool_calls"][0]["function"]["name"] == "estimate_duration"


def test_json_protocol_checks_nested_script_parameters():
    raw = json.dumps({"action": "submit_script", "arguments": {"title": "test", "scenes": [{"scene_id": "S1", "visual": "v", "narration": "n", "subtitle": "s", "source_ids": [], "min_display_seconds": True}], "claims": [], "used_skills": [], "reason": "test"}})
    with ModelClient(Settings(action_protocol="json"), transport=httpx.MockTransport(lambda _: response({"content": raw}))) as client:
        with pytest.raises(ModelError, match="min_display_seconds"):
            client.chat([], tool_schemas())


def test_json_protocol_does_not_change_fact_verifier_requests():
    report = {"passed": True, "issues": [], "claims": [{**SCRIPT["claims"][0], "status": "supported", "reason": "原文支持"}]}

    def handle(request):
        body = json.loads(request.content)
        assert "tools" not in body
        assert "response_format" not in body
        assert "动作协议为 JSON" not in body["messages"][0]["content"]
        assert "独立核验" in body["messages"][0]["content"]
        return response({"content": json.dumps(report, ensure_ascii=False)})

    with ModelClient(Settings(action_protocol="json"), transport=httpx.MockTransport(handle)) as client:
        assert client.verify_script(SCRIPT, MATERIALS)["passed"] is True
        assert client.last_action_protocol == "text"


def test_invalid_action_protocol_setting_is_rejected():
    with pytest.raises(ModelError, match="LLM_ACTION_PROTOCOL"):
        Settings(action_protocol="automatic_fallback")


def test_json_protocol_unsupported_response_format_is_visible_without_retry():
    seen = []

    def handle(request):
        seen.append(request)
        assert json.loads(request.content)["response_format"]["type"] == "json_schema"
        return httpx.Response(400, json={"error": {"message": "response_format unsupported"}})

    with ModelClient(Settings(action_protocol="json"), transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ModelError, match="response_format unsupported"):
            client.chat([], tool_schemas())
        assert len(seen) == 1
        assert client.last_action_protocol == "json"


def test_json_protocol_truncation_keeps_public_evidence_and_actual_request_config():
    raw = '{"action":"submit_script","arguments":'
    payload = {"choices": [{"message": {"content": raw, "reasoning": "private"}, "finish_reason": "length"}]}
    with ModelClient(Settings(action_protocol="json", timeout_seconds=120), transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
        with pytest.raises(ModelError, match="truncated"):
            client.chat([], tool_schemas())
        assert client.last_public_response == raw
        assert client.last_response_metadata["max_tokens"] == 2048
        assert client.last_response_metadata["timeout_seconds"] == 120
        assert "private" not in json.dumps(client.last_response_metadata)


def state_tools(state):
    return {tool["function"]["name"]: tool["function"]["parameters"] for tool in tools_for_state(state)}


def creation_state(phase="draft"):
    return {
        "phase": phase, "brief": {"topic": "subtitle", "audience": "beginner", "platform": "video", "target_seconds": 30, "style": "plain"},
        "script": {"title": "test", "scenes": [{"scene_id": "S1", "narration": "supported text"}]},
        "script_version": 1, "data_hash": "data-v1", "request": {},
        "retrieved_materials": [{"source_id": "P01", "text": "supported text"}],
        "loaded_skills": {"audience-angle": {"content": "method"}},
        "checks": {}, "direction": {"source_ids": ["P01"]},
    }


def attach_check(state, kind, passed=True, issues=None):
    fingerprint = lambda value: hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    state["checks"][kind] = {
        "script_version": state["script_version"], "script_hash": fingerprint(state["script"]),
        "brief_hash": fingerprint(state["brief"]), "data_hash": state["data_hash"],
        "passed": passed, "issues": issues or [],
    }


def test_state_tools_without_evidence_keep_multiple_safe_choices():
    state = creation_state("direction")
    state.update(loaded_skills={}, retrieved_materials=[], direction=None, script=None)
    offered = state_tools(state)
    assert {"search_materials", "ask_user", "finish_incomplete", "load_skill"} == set(offered)
    assert len(offered["load_skill"]["properties"]["name"]["enum"]) == 16
    assert all("used_skills" not in spec["properties"] for spec in offered.values())
    state["loaded_skills"] = {"material-search": {"content": "method"}}
    assert "submit_direction" not in state_tools(state)
    state["retrieved_materials"] = [{"source_id": "P01"}]
    assert "submit_direction" in state_tools(state)
    state["brief"]["audience"] = None
    assert "submit_direction" not in state_tools(state)


def test_state_tools_constrain_skill_loading_and_attribution_without_mutation():
    state = creation_state()
    before = json.dumps(state)
    offered = state_tools(state)
    assert "audience-angle" not in offered["load_skill"]["properties"]["name"]["enum"]
    submitted = offered["submit_script"]["properties"]["used_skills"]
    assert submitted["items"]["enum"] == ["audience-angle"] and submitted["minItems"] == 1
    assert offered["search_materials"]["properties"]["used_skills"]["items"]["enum"] == ["audience-angle"]
    assert json.dumps(state) == before
    all_names = state_tools({})["load_skill"]["properties"]["name"]["enum"]
    state["loaded_skills"] = {name: {} for name in all_names}
    assert "load_skill" not in state_tools(state)
    assert "enum" not in tool_schemas()[0]["function"]["parameters"]["properties"]["name"]


def test_state_tools_need_script_for_checks_and_reenable_after_new_version():
    state = creation_state()
    state["script"] = None
    offered = state_tools(state)
    assert "submit_script" in offered
    assert not {"estimate_duration", "check_rules", "request_review"}.intersection(offered)
    state["script"] = {"title": "new", "scenes": []}
    attach_check(state, "duration", passed=False)
    attach_check(state, "rules")
    offered = state_tools(state)
    assert not {"estimate_duration", "check_rules"}.intersection(offered)
    assert {"submit_script", "request_review", "search_materials", "ask_user", "finish_incomplete"}.issubset(offered)
    state["script_version"] += 1
    offered = state_tools(state)
    assert {"estimate_duration", "check_rules"}.issubset(offered)
    assert "request_review" not in offered


@pytest.mark.parametrize("changed", ["script", "brief", "data_hash"])
def test_state_tools_do_not_reuse_stale_check_hashes(changed):
    state = creation_state("final")
    attach_check(state, "duration")
    attach_check(state, "rules")
    if changed == "data_hash":
        state[changed] = "new-data"
    else:
        state[changed]["extra_change"] = True
    offered = state_tools(state)
    assert {"estimate_duration", "check_rules"}.issubset(offered)
    assert "request_review" not in offered


@pytest.mark.parametrize("error_code", ["semantic_unavailable", "tool_error"])
def test_state_tools_allow_failed_service_retry(error_code):
    state = creation_state("final")
    attach_check(state, "duration")
    attach_check(state, "rules", passed=False, issues=[{"code": error_code}])
    offered = state_tools(state)
    assert "check_rules" in offered and "estimate_duration" not in offered
    assert "request_review" not in offered


def test_state_tools_gate_reviews_and_human_revision():
    state = creation_state("direction")
    assert "request_review" in state_tools(state)
    state["direction"]["source_ids"] = ["unretrieved"]
    assert "request_review" not in state_tools(state)
    state["phase"] = "draft"
    attach_check(state, "duration", passed=False)
    attach_check(state, "rules", passed=False)
    assert "request_review" in state_tools(state)
    state["phase"] = "final"
    assert "request_review" not in state_tools(state)
    attach_check(state, "duration")
    attach_check(state, "rules")
    assert "request_review" in state_tools(state)
    state["revision_required"] = True
    offered = state_tools(state)
    assert "request_review" not in offered and "submit_script" in offered


def test_user_initial_draft_must_be_observed_before_revision():
    state = creation_state()
    state["request"]["initial_script"] = state["script"]
    assert "submit_script" not in state_tools(state)
    attach_check(state, "duration", passed=False)
    assert "submit_script" not in state_tools(state)
    attach_check(state, "rules", passed=False)
    assert "submit_script" in state_tools(state)
    state["script_version"] = 2
    state["checks"] = {}
    assert "submit_script" in state_tools(state)


def test_focus_keeps_actual_failed_timing_and_requires_content_change():
    state = creation_state()
    attach_check(state, "duration", passed=False, issues=[{"code": "TIME_LIMIT_EXCEEDED", "message": "actual timing"}])
    state["checks"]["duration"]["estimated_seconds"] = 32.65
    messages = build_messages(state, [])
    focus = messages[-1]["content"]
    assert "32.65" in focus and "30" in focus
    assert "submit_script" in focus and "重复复制原稿无效" in focus
    assert "不要询问用户是否允许修改" in focus
    assert "真正缺少来源、资料冲突或必须改变硬性要求" in focus
    assert "保留必讲事实与必要限定" in focus
    assert 'ask_user(fields=["target_seconds"])' in focus
    assert "或 finish_incomplete 说明当前实际估时与目标的缺口" in focus
    assert "不必先把其它规则或引用问题修到通过" in focus
    assert "连续收到内容没有变化、技能已加载等结果" in focus
    assert "澄清或结束都是合法选择" in focus
    assert "actual timing" in messages[1]["content"]


def patch_state():
    state = creation_state()
    state["script"] = {
        "title": "subtitle", "scenes": [{"scene_id": "1", "visual": "screen", "narration": "supported text", "subtitle": "supported", "source_ids": ["P01"]}],
        "claims": [{"text": "supported text", "source_id": "P01", "quote": "supported text", "scene_id": "1"}],
    }
    return state


def test_patch_schema_lists_only_existing_zero_based_paths_and_operation_fields():
    state = patch_state()
    edit_schema = state_tools(state)["patch_script"]["properties"]["edits"]
    # One planner tool call may atomically update related text and citations.
    assert edit_schema["maxItems"] == 20
    base = next(tool for tool in tool_schemas() if tool["function"]["name"] == "patch_script")
    assert base["function"]["parameters"]["properties"]["edits"]["maxItems"] == 20
    spec = edit_schema["items"]
    branches = {b["properties"]["op"]["const"]: b for b in spec["anyOf"]}
    replace = branches["replace"]["properties"]["path"]["enum"]
    remove = branches["remove"]["properties"]["path"]["enum"]
    assert "/scenes/0/narration" in replace and "/claims/0/text" in replace
    assert "/scenes/0/source_ids/0" in replace
    assert not any(path.startswith("/scenes/1/") for path in replace)
    assert remove == ["/scenes/0/source_ids/0", "/claims/0"]
    assert "value" in branches["replace"]["required"]
    assert "value" not in branches["remove"]["properties"]
    context = json.loads(state_prompt(state).split("\n", 1)[1])
    assert context["editable_script_paths"]["replace"]["/scenes/0/narration"] == "supported text"
    assert "降序" in build_messages(state, [])[-1]["content"]


@pytest.mark.parametrize("edit", [
    {"op": "replace", "path": "/scenes/0/narration", "value": "shorter"},
    {"op": "remove", "path": "/scenes/0/source_ids/0"},
])
def test_json_action_accepts_each_patch_union_branch(edit):
    raw = json.dumps({"action": "patch_script", "arguments": {"used_skills": ["audience-angle"], "edits": [edit], "reason": "repair"}})
    with ModelClient(Settings(action_protocol="json"), transport=httpx.MockTransport(lambda _: response({"content": raw}))) as client:
        action = client.chat([], tools_for_state(patch_state()))
        assert json.loads(action["tool_calls"][0]["function"]["arguments"])["edits"] == [edit]


def test_json_patch_accepts_related_fields_as_one_bounded_atomic_action():
    edits = [{"op": "replace", "path": path, "value": "supported"} for path in
             ("/scenes/0/narration", "/scenes/0/subtitle", "/claims/0/text")]
    raw = json.dumps({"action": "patch_script", "arguments": {
        "used_skills": ["audience-angle"], "edits": edits, "reason": "Keep narration, subtitle, and citation aligned"}})
    with ModelClient(Settings(action_protocol="json"), transport=httpx.MockTransport(lambda _: response({"content": raw}))) as client:
        action = client.chat([], tools_for_state(patch_state()))
    assert len(action["tool_calls"]) == 1
    assert json.loads(action["tool_calls"][0]["function"]["arguments"])["edits"] == edits


def test_json_patch_rejects_more_than_twenty_edits():
    edits = [{"op": "replace", "path": "/title", "value": str(index)} for index in range(21)]
    raw = json.dumps({"action": "patch_script", "arguments": {
        "used_skills": ["audience-angle"], "edits": edits, "reason": "Oversized atomic batch"}})
    with ModelClient(Settings(action_protocol="json"), transport=httpx.MockTransport(lambda _: response({"content": raw}))) as client:
        with pytest.raises(ModelError, match="item count"):
            client.chat([], tools_for_state(patch_state()))


def test_human_revision_focus_requires_all_affected_fields_and_current_claims():
    state = patch_state()
    state["revision_required"] = True
    focus = build_messages(state, [])[-1]["content"]
    assert "一次原子调用中修改最多20处" in focus
    assert "同一次 patch 或完整提交中同步修改对应 claims.text/source_id/quote" in focus
    assert "标题、旁白、字幕、画面" in focus
    assert "同时检查第一镜 narration 和 subtitle" in focus
    assert "每轮仍只调用一个工具" in focus


@pytest.mark.parametrize("edit", [
    {"op": "replace", "path": "/scenes/1/narration", "value": "out of bounds"},
    {"op": "remove", "path": "/scenes/0/narration"},
    {"op": "remove", "path": "/claims/0", "value": "extra"},
    {"op": "replace", "path": "/claims/0/text"},
    {"op": "add", "path": "/claims/0/text", "value": "unsupported"},
])
def test_json_patch_rejects_invalid_union_relationships(edit):
    raw = json.dumps({"action": "patch_script", "arguments": {"used_skills": ["audience-angle"], "edits": [edit], "reason": "repair"}})
    with ModelClient(Settings(action_protocol="json"), transport=httpx.MockTransport(lambda _: response({"content": raw}))) as client:
        with pytest.raises(ModelError, match="schema branch"):
            client.chat([], tools_for_state(patch_state()))


def test_unused_union_branch_with_unknown_keyword_is_not_silently_ignored():
    from script_agent.model import _validate_arguments
    schema = {"anyOf": [
        {"type": "string", "const": "valid"},
        {"type": "string", "pattern": "unsupported"},
    ]}
    with pytest.raises(ModelError, match="Unsupported"):
        _validate_arguments("valid", schema)


def test_const_rejects_boolean_equal_to_integer_and_anyof_obeys_outer_type():
    from script_agent.model import _validate_arguments
    with pytest.raises(ModelError, match="constant"):
        _validate_arguments(True, {"const": 1})
    with pytest.raises(ModelError, match="must be object"):
        _validate_arguments("text", {"type": "object", "anyOf": [{"type": "string"}]})


@pytest.mark.parametrize("base_url", ["https://api.deepseek.com", "https://api.deepseek.com/v1"])
def test_deepseek_native_disables_thinking_and_replays_only_public_tool_messages(base_url):
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["thinking"] == {"type": "disabled"}
        assert body["tool_choice"] == "auto"
        assert "parallel_tool_calls" not in body
        assert "response_format" not in body
        if len(requests) == 2:
            assert body["messages"][-1]["role"] == "tool"
            assert body["messages"][-1]["content"] == '{"matches":[]}'
            assert body["messages"][-2]["tool_calls"][0]["id"] == "deepseek-call"
            assert "reasoning_content" not in body["messages"][-2]
        return response({"role": "assistant", "content": None, "reasoning_content": "private reasoning", "tool_calls": [{"id": "deepseek-call", "type": "function", "function": {"name": "search_materials", "arguments": '{"query":"subtitle","reason":"lookup"}'}}]})

    settings = Settings(base_url=base_url, model="deepseek-flash")
    assert settings.thinking == "disabled"
    with ModelClient(settings, transport=httpx.MockTransport(handle)) as client:
        first = client.chat([{"role": "user", "content": "task"}], tool_schemas())
        client.chat([{"role": "user", "content": "task"}, first, {"role": "tool", "tool_call_id": "deepseek-call", "content": '{"matches":[]}'}], tool_schemas())
        assert client.request_count == 2
        assert client.last_response_metadata["provider"] == "deepseek"
        assert "private reasoning" not in json.dumps(client.last_response_metadata)


def test_generic_explicit_thinking_disabled_keeps_native_parameters():
    def handle(request):
        body = json.loads(request.content)
        assert body["thinking"] == {"type": "disabled"}
        assert body["parallel_tool_calls"] is False
        return response({"content": "ok"})

    with ModelClient(Settings(thinking="disabled"), transport=httpx.MockTransport(handle)) as client:
        client.chat([], tool_schemas())
    assert Settings(base_url="https://api.deepseek.com.example.invalid/v1").thinking == "default"


@pytest.mark.parametrize("thinking", ["default", "enabled"])
def test_deepseek_rejects_unsupported_thinking_modes_before_client_creation(thinking):
    with pytest.raises(ModelError, match="THINKING"):
        Settings(base_url="https://api.deepseek.com/v1", thinking=thinking)


def test_deepseek_rejects_json_schema_action_protocol_explicitly():
    with pytest.raises(ModelError, match="json_schema.*native"):
        Settings(base_url="https://api.deepseek.com", action_protocol="json")


def test_deepseek_fact_verifier_also_disables_thinking():
    report = {"passed": True, "issues": [], "claims": [{**SCRIPT["claims"][0], "status": "supported", "reason": "source supports text"}]}

    def handle(request):
        body = json.loads(request.content)
        assert body["thinking"] == {"type": "disabled"}
        assert not {"tools", "parallel_tool_calls", "response_format"}.intersection(body)
        return response({"content": json.dumps(report), "reasoning_content": "private"})

    with ModelClient(Settings(base_url="https://api.deepseek.com"), transport=httpx.MockTransport(handle)) as client:
        assert client.verify_script(SCRIPT, MATERIALS)["passed"] is True
        assert client.last_action_protocol == "text"


@pytest.mark.parametrize("protocol", ["native", "json"])
def test_context_budget_observes_final_payload_before_http(monkeypatch, protocol):
    import script_agent.model as model_module

    observed = []
    budget_metadata = {"enabled": True, "context_window": 16000, "reserved_output_tokens": 4096, "is_exact": False}

    def budget(payload, context_window, max_tokens):
        assert (context_window, max_tokens) == (16000, 4096)
        assert payload["max_tokens"] == 4096
        assert payload["thinking"] == {"type": "disabled"}
        if protocol == "native":
            assert payload["tools"] == tool_schemas()
        else:
            assert payload["response_format"]["type"] == "json_schema"
            assert "arguments_schema" in payload["messages"][0]["content"]
        observed.append(payload)
        return budget_metadata

    def handle(request):
        assert len(observed) == 1
        assert json.loads(request.content) == observed[0]
        content = '{"action":"estimate_duration","arguments":{"reason":"estimate"}}' if protocol == "json" else "ok"
        return response({"content": content})

    monkeypatch.setattr(model_module, "enforce_budget", budget)
    with ModelClient(Settings(action_protocol=protocol, thinking="disabled", context_window=16000, max_tokens=4096), transport=httpx.MockTransport(handle)) as client:
        client.chat([{"role": "user", "content": "task"}], tool_schemas())
        assert client.last_response_metadata["context_budget"] == budget_metadata
        assert client.last_request_count == client.request_count == 1


def test_context_limit_is_visible_and_does_not_make_or_count_http():
    seen = []
    with ModelClient(Settings(context_window=300, max_tokens=128), transport=httpx.MockTransport(lambda request: seen.append(request))) as client:
        with pytest.raises(ContextLimitError, match="before HTTP") as caught:
            client.chat([{"role": "user", "content": "long input " * 3000}])
        assert caught.value.code == "context_budget_exceeded"
        assert isinstance(caught.value, ModelError)
        assert not seen
        assert client.request_count == client.last_request_count == 0
        assert client.last_response_metadata["context_budget"]


@pytest.mark.parametrize("context_window", [-1, 4096, 4000, True, 16000.0])
def test_invalid_context_budget_settings_are_rejected(context_window):
    with pytest.raises(ModelError, match="LLM_CONTEXT_WINDOW"):
        Settings(context_window=context_window, max_tokens=4096)


def test_model_settings_read_explicit_budget_and_thinking_environment(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("LLM_MODEL", "deepseek-flash")
    monkeypatch.setenv("LLM_THINKING", "disabled")
    monkeypatch.setenv("LLM_CONTEXT_WINDOW", "16000")
    monkeypatch.setenv("LLM_MAX_TOKENS", "4096")
    settings = Settings.from_env()
    assert settings.is_deepseek and settings.thinking == "disabled"
    assert (settings.context_window, settings.max_tokens) == (16000, 4096)
    assert not settings.api_key
    monkeypatch.delenv("LLM_THINKING")
    assert Settings.from_env().thinking == "disabled"


def test_actual_usage_over_budget_fails_after_http_and_retains_evidence(monkeypatch):
    import script_agent.model as model_module

    monkeypatch.setattr(model_module, "enforce_budget", lambda *_: {"enabled": True, "is_exact": False})
    usage = {"prompt_tokens": 200, "completion_tokens": 101, "total_tokens": 1}
    with ModelClient(Settings(context_window=300, max_tokens=128), transport=httpx.MockTransport(lambda _: response({"content": "public answer", "reasoning_content": "private"}, usage=usage))) as client:
        with pytest.raises(ContextLimitError, match="after HTTP"):
            client.chat([{"role": "user", "content": "task"}])
        assert client.last_request_count == client.request_count == 1
        assert client.last_usage == usage
        assert client.last_public_response == "public answer"
        assert client.last_response_metadata["context_usage_check"] == {
            "phase": "response_usage", "request_sent": True, "context_window": 300,
            "observed_total_tokens": 301, "exceeded": True,
        }
        assert "private" not in json.dumps(client.last_response_metadata)


@pytest.mark.parametrize("usage", [
    {"prompt_tokens": 200, "completion_tokens": 100},
    {"prompt_tokens": True, "completion_tokens": 500},
    {"prompt_tokens": 200.0, "completion_tokens": 101},
    {"prompt_tokens": -1, "completion_tokens": 500},
])
def test_actual_usage_check_requires_valid_integers_and_accepts_exact_budget(monkeypatch, usage):
    import script_agent.model as model_module

    monkeypatch.setattr(model_module, "enforce_budget", lambda *_: {"enabled": True, "is_exact": False})
    with ModelClient(Settings(context_window=300, max_tokens=128), transport=httpx.MockTransport(lambda _: response({"content": "ok"}, usage=usage))) as client:
        assert client.chat([])["content"] == "ok"
        if type(usage["prompt_tokens"]) is int and usage["prompt_tokens"] >= 0:
            assert client.last_response_metadata["context_usage_check"]["exceeded"] is False
        else:
            assert "context_usage_check" not in client.last_response_metadata
