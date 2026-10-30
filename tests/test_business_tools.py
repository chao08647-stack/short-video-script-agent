from copy import deepcopy

import pytest
from pydantic import ValidationError

from script_agent.business_tools import check_rules, estimate_duration, search_materials
from script_agent.schemas import Brief, RunRequest, Script


MATERIALS = [
    {"source_id": "P01", "version": "2026-10-01", "title": "字幕功能", "text": "小剪支持自动生成字幕。", "facts": ["支持自动生成字幕"], "keywords": ["字幕", "自动字幕"]},
    {"source_id": "P02", "version": "2026-10-02", "title": "字幕编辑", "text": "用户可以手动修改字幕文字。", "facts": ["可手动修改字幕"], "keywords": ["字幕修改", "编辑"]},
]


def script(narration="小剪支持自动生成字幕。", subtitle="自动生成字幕", min_display=1.0):
    return {
        "title": "字幕操作指南",
        "scenes": [{"scene_id": "S1", "visual": "演示字幕生成操作", "narration": narration, "subtitle": subtitle, "source_ids": ["P01"], "min_display_seconds": min_display}],
        "claims": [{"text": "小剪支持自动生成字幕", "source_id": "P01", "quote": "小剪支持自动生成字幕。", "scene_id": "S1"}],
    }


def codes(result):
    return {issue["code"] for issue in result["issues"]}


def test_missing_brief_is_preserved_for_clarification_not_coerced():
    brief = Brief(topic="字幕", audience="  ")
    assert brief.missing_fields() == ["audience", "platform", "target_seconds", "style"]
    with pytest.raises(ValidationError):
        Brief(target_seconds="30")
    with pytest.raises(ValidationError):
        RunRequest(brief=brief, max_tool_calls=True)


def test_search_can_return_empty_then_find_rephrased_query():
    assert search_materials("量子隧穿材料", MATERIALS)["matches"] == []
    found = search_materials("自动字幕", MATERIALS)
    assert found["matches"][0]["source_id"] == "P01"
    assert found["matches"][0]["text"] == MATERIALS[0]["text"]


def test_search_exposes_conflicting_record_outside_top_k():
    materials = [
        {**MATERIALS[0], "conflict_group": "subtitle-language"},
        {**MATERIALS[1], "text": "仅支持英文字幕。", "conflict_group": "subtitle-language"},
    ]
    result = search_materials("P01", materials, limit=1)
    assert len(result["matches"]) == 1
    assert result["conflicts"][0]["source_ids"] == ["P01", "P02"]


def test_duration_overlapping_narration_subtitles_are_not_added():
    value = script(narration="字" * 40, subtitle="字" * 40)
    result = estimate_duration(value, {}, 10)
    assert result["estimated_seconds"] == 10
    assert result["passed"] is True
    assert result["scenes"][0]["subtitle_seconds"] == 6.67


def test_duration_uses_visual_minimum_and_serial_transitions():
    value = script(narration="看", subtitle="看", min_display=8.0)
    value["scenes"].append({**value["scenes"][0], "scene_id": "S2", "min_display_seconds": 6.0})
    result = estimate_duration(value, {"transition_seconds": 0.5}, 14)
    assert result["estimated_seconds"] == 14.5
    assert result["scenes"][1]["start_seconds"] == 8.5
    assert codes(result) == {"TIME_LIMIT_EXCEEDED"}


def test_shortening_content_changes_actual_estimate_without_clamping():
    long = estimate_duration(script(narration="字" * 120, subtitle=""), {}, 25)
    short = estimate_duration(script(narration="字" * 80, subtitle=""), {}, 25)
    assert (long["estimated_seconds"], long["passed"]) == (30, False)
    assert (short["estimated_seconds"], short["passed"]) == (20, True)


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), True, "4"])
def test_duration_rejects_invalid_rate_configuration(bad):
    with pytest.raises(ValueError):
        estimate_duration(script(), {"chars_per_second": bad}, 30)


def test_valid_citation_passes_only_deterministic_checks():
    result = check_rules(script(), MATERIALS, {})
    assert result["passed"] is True
    assert result["requires_semantic_verification"] is True
    assert result["semantic_status"] == "not_checked"


def test_changing_material_invalidates_old_quote():
    replaced = deepcopy(MATERIALS)
    replaced[0]["text"] = "小剪仅支持手动输入字幕。"
    result = check_rules(script(), replaced, {})
    assert result["passed"] is False
    assert "QUOTE_NOT_IN_SOURCE" in codes(result)


def test_source_id_alone_is_not_a_grounded_claim():
    value = script()
    value["claims"] = []
    assert "UNMAPPED_SOURCE" in codes(check_rules(value, MATERIALS, {}))


def test_unsupported_number_is_not_allowed_by_unrelated_source():
    value = script(narration="小剪支持自动生成字幕，效率提升80%。")
    result = check_rules(value, MATERIALS, {})
    assert "UNSUPPORTED_NUMBER" in codes(result)
    assert result["passed"] is False


def test_supported_numeric_claim_has_matching_script_and_quote():
    material = {"source_id": "N1", "text": "测试样本中字幕准确率为80%。", "title": "测试", "version": "1", "facts": [], "keywords": []}
    value = script(narration="测试样本中字幕准确率为80%。", subtitle="")
    value["scenes"][0]["source_ids"] = ["N1"]
    value["claims"] = [{"text": "测试样本中字幕准确率为80%", "source_id": "N1", "quote": material["text"], "scene_id": "S1"}]
    assert check_rules(value, [material], {})["passed"] is True


def test_step_number_is_not_misreported_as_product_performance():
    value = script(narration="第1步，小剪支持自动生成字幕。")
    assert "UNSUPPORTED_NUMBER" not in codes(check_rules(value, MATERIALS, {}))


def test_brand_rules_cover_visuals_and_titles_too():
    value = script()
    value["title"] = "百分百准确的字幕"
    value["scenes"][0]["visual"] = "画面显示百分百准确"
    result = check_rules(value, MATERIALS, {"banned_phrases": ["百分百准确"]})
    assert len([issue for issue in result["issues"] if issue["code"] == "BANNED_PHRASE"]) == 2


def test_conflict_cannot_be_resolved_by_just_citing_newer_source():
    materials = [
        {**MATERIALS[0], "conflict_group": "auto-subtitle"},
        {**MATERIALS[1], "text": "小剪不支持自动生成字幕。", "conflict_group": "auto-subtitle"},
    ]
    assert "CONFLICTING_SOURCES" in codes(check_rules(script(), materials, {}))


def test_empty_script_is_reported_as_failed_check():
    result = check_rules({"title": "", "scenes": [], "claims": []}, MATERIALS, {})
    assert result["passed"] is False
    assert codes(result) == {"INVALID_SCRIPT"}


def test_duplicate_scene_ids_and_extra_fields_are_rejected():
    value = script()
    value["scenes"].append(deepcopy(value["scenes"][0]))
    with pytest.raises(ValidationError):
        Script.model_validate(value)
    with pytest.raises(ValidationError):
        Brief(topic="字幕", guessed_source="P01")


def test_tools_do_not_mutate_input():
    value = script()
    original_script, original_materials = deepcopy(value), deepcopy(MATERIALS)
    search_materials("字幕", MATERIALS)
    estimate_duration(value, {}, 30)
    check_rules(value, MATERIALS, {})
    assert value == original_script
    assert MATERIALS == original_materials
