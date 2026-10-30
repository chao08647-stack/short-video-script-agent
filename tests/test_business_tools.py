from copy import deepcopy
import json
from pathlib import Path

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


TERM_RULES = {
    "evidence_required_terms": {
        "feature": ["导出", "下载", "上传", "实时"],
        "ui_detail": ["滑块", "进度条", "按钮", "面板", "菜单", "时间轴", "时间线"],
    }
}


# Freeze actual field excerpts, not mutable paths under examples/deepseek-flash.
# These runs passed the earlier automatic checker and failed manual fact review.
@pytest.mark.parametrize("run_id,field,excerpt,expected_code,term", [
    ("8d6b1326-f461-41cb-afa3-10a8326af758", "visual",
     "录屏：在小剪 App 里点开字幕功能，选择自动生成字幕，进度条走完后时间线上出现字幕条",
     "UNSUPPORTED_UI_DETAIL", "进度条"),
    ("033c5552-1641-4eac-ba87-344a3499ba8b", "narration",
     "记住，自动生成后检查一遍内容，识别错误手动修正，再导出。",
     "UNSUPPORTED_FEATURE", "导出"),
    ("e8e5a583-7c0c-452f-9c4c-15105efc924e", "visual",
     "录屏：打开字幕样式面板，拖动字体大小滑块，再点选不同颜色，字幕实时变化",
     "UNSUPPORTED_UI_DETAIL", "滑块"),
])
def test_manual_audit_regression_excerpts_require_feature_or_ui_evidence(run_id, field, excerpt, expected_code, term):
    value = script()
    # Preserve the ordinary cited subtitle fact so this tests the new omission.
    value["scenes"][0][field] += " " + excerpt
    assert check_rules(value, MATERIALS, {})["passed"] is True, run_id
    result = check_rules(value, MATERIALS, TERM_RULES)
    assert result["passed"] is False
    issue = next(issue for issue in result["issues"] if issue["code"] == expected_code and issue["term"] == term)
    assert issue["field"] == field and issue["scene_id"] == "S1"
    assert issue["path"] == f"/scenes/0/{field}"


@pytest.mark.parametrize("field", ["title", "visual", "narration", "subtitle"])
def test_term_evidence_must_be_a_valid_claim_in_that_exact_field(field):
    value = script()
    phrase = "字幕界面提供按钮。"
    sources = deepcopy(MATERIALS)
    sources[0]["text"] += phrase
    if field == "title":
        value["title"] += phrase
    else:
        value["scenes"][0][field] += phrase
    assert "UNSUPPORTED_UI_DETAIL" in codes(check_rules(value, sources, TERM_RULES))
    value["claims"].append({"text": phrase, "source_id": "P01", "quote": phrase,
                            "scene_id": "" if field == "title" else "S1"})
    assert check_rules(value, sources, TERM_RULES)["passed"] is True


def test_term_in_an_unrelated_source_cannot_support_caption_only_claim():
    value = script(narration="小剪支持自动生成字幕。再导出。")
    sources = deepcopy(MATERIALS)
    sources[1]["text"] += "另一个产品支持导出。"
    assert "UNSUPPORTED_FEATURE" in codes(check_rules(value, sources, TERM_RULES))


def test_broad_quote_containing_term_cannot_expand_a_caption_only_claim():
    value = script(narration="小剪支持自动生成字幕。再导出。")
    sources = deepcopy(MATERIALS)
    sources[0]["text"] += "产品还支持导出。"
    value["claims"][0]["quote"] = sources[0]["text"]
    assert "UNSUPPORTED_FEATURE" in codes(check_rules(value, sources, TERM_RULES))
    value["claims"].append({"text": "导出", "source_id": "P01", "quote": "产品还支持导出。", "scene_id": "S1"})
    assert check_rules(value, sources, TERM_RULES)["passed"] is True


def test_claim_in_narration_does_not_cover_a_different_visual_assertion():
    value = script(narration="小剪支持自动生成字幕。界面有按钮。")
    value["scenes"][0]["visual"] = "点击红色按钮，画面切换。"
    sources = deepcopy(MATERIALS)
    sources[0]["text"] += "界面有按钮。"
    value["claims"].append({"text": "界面有按钮。", "source_id": "P01", "quote": "界面有按钮。", "scene_id": "S1"})
    issues = [issue for issue in check_rules(value, sources, TERM_RULES)["issues"] if issue["code"] == "UNSUPPORTED_UI_DETAIL"]
    assert len(issues) == 1 and issues[0]["field"] == "visual"


def test_demo_label_does_not_exempt_specific_ui_and_abstract_visual_is_allowed():
    value = script()
    value["scenes"][0]["visual"] = "示意画面：拖动字体滑块。"
    assert "UNSUPPORTED_UI_DETAIL" in codes(check_rules(value, MATERIALS, TERM_RULES))
    value["scenes"][0]["visual"] = "抽象演示：字幕文字逐渐放大，与人物画面交替展示。"
    assert check_rules(value, MATERIALS, TERM_RULES)["passed"] is True


def test_term_guard_does_not_claim_unconfigured_synonym_detection():
    value = script()
    value["scenes"][0]["visual"] = "拖动滑杆调整显示。"
    assert check_rules(value, MATERIALS, TERM_RULES)["passed"] is True
    configured = deepcopy(TERM_RULES)
    configured["evidence_required_terms"]["ui_detail"].append("滑杆")
    assert "UNSUPPORTED_UI_DETAIL" in codes(check_rules(value, MATERIALS, configured))


def test_term_aliases_each_need_corresponding_literal_quote_support():
    value = script()
    value["scenes"][0]["visual"] = "界面显示时间线。"
    sources = deepcopy(MATERIALS)
    sources[0]["text"] += "界面显示时间轴。"
    value["claims"].append({"text": "界面显示时间线。", "source_id": "P01", "quote": "界面显示时间轴。", "scene_id": "S1"})
    assert "UNSUPPORTED_UI_DETAIL" in codes(check_rules(value, sources, TERM_RULES))
    sources[0]["text"] += "界面显示时间线。"
    value["claims"][-1]["quote"] = "界面显示时间线。"
    assert check_rules(value, sources, TERM_RULES)["passed"] is True


def test_all_bundled_datasets_enable_the_same_targeted_term_guards():
    root = Path(__file__).resolve().parents[1]
    for dataset in ("demo", "empty", "conflict"):
        rules = json.loads((root / "data" / dataset / "rules.json").read_text(encoding="utf-8"))
        assert rules["evidence_required_terms"] == TERM_RULES["evidence_required_terms"]


@pytest.mark.parametrize("configured", [None, [], {"unknown": ["导出"]}, {"feature": "导出"}, {"feature": [""]}])
def test_bad_term_configuration_fails_closed(configured):
    with pytest.raises(ValueError, match="evidence_required_terms"):
        check_rules(script(), MATERIALS, {"evidence_required_terms": configured})
