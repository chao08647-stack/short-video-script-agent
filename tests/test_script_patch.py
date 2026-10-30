"""Local edits are atomic and cannot bypass the normal content checks."""

from copy import deepcopy

import pytest

from script_agent.business_tools import check_rules, estimate_duration
from script_agent.script_patch import apply_script_patch


@pytest.fixture
def script():
    return {
        "title": "字幕操作指南",
        "scenes": [{
            "scene_id": "S1", "visual": "演示字幕生成操作",
            "narration": "小剪支持自动生成字幕。", "subtitle": "自动生成字幕",
            "source_ids": ["P01"], "min_display_seconds": 2.0,
        }],
        "claims": [{
            "text": "小剪支持自动生成字幕", "source_id": "P01",
            "quote": "小剪支持自动生成字幕。", "scene_id": "S1",
        }],
    }


@pytest.fixture
def materials():
    return [{
        "source_id": "P01", "version": "2026-10-01", "title": "字幕功能",
        "text": "小剪支持自动生成字幕。", "facts": ["支持自动生成字幕"], "keywords": ["字幕"],
    }]


def test_repairs_text_quote_and_scene_binding_without_mutating_inputs(script, materials):
    script["claims"][0].update(text="旧文句", source_id="UNKNOWN", quote="错误原文", scene_id="S9")
    script["scenes"][0]["source_ids"] = ["UNKNOWN"]
    before = deepcopy(script)
    edits = [
        {"op": "replace", "path": "/claims/0/text", "value": "小剪支持自动生成字幕"},
        {"op": "replace", "path": "/claims/0/source_id", "value": "P01"},
        {"op": "replace", "path": "/claims/0/quote", "value": "小剪支持自动生成字幕。"},
        {"op": "replace", "path": "/claims/0/scene_id", "value": "S1"},
        {"op": "replace", "path": "/scenes/0/source_ids/0", "value": "P01"},
    ]
    original_edits = deepcopy(edits)
    assert check_rules(script, materials, {})["passed"] is False
    patched = apply_script_patch(script, edits)
    assert check_rules(patched, materials, {})["passed"] is True
    assert script == before
    assert edits == original_edits
    assert patched["scenes"][0]["min_display_seconds"] == 2.0


def test_shorter_copy_changes_actual_duration_and_preserves_display_minimum(script):
    script["scenes"][0]["narration"] = "字幕" * 100
    before = estimate_duration(script, {}, 30)
    patched = apply_script_patch(script, [
        {"op": "replace", "path": "/title", "value": "自动字幕介绍"},
        {"op": "replace", "path": "/scenes/0/visual", "value": "展示字幕效果"},
        {"op": "replace", "path": "/scenes/0/narration", "value": "小剪支持自动生成字幕。"},
        {"op": "replace", "path": "/scenes/0/subtitle", "value": "自动字幕"},
    ])
    after = estimate_duration(patched, {}, 30)
    assert before["passed"] is False
    assert after["passed"] is True
    assert after["estimated_seconds"] < before["estimated_seconds"]
    assert patched["scenes"][0]["min_display_seconds"] == script["scenes"][0]["min_display_seconds"]


def test_removals_use_current_indices_and_leave_no_shared_mutable_objects(script):
    script["claims"] += [{**script["claims"][0], "source_id": "P02"}, {**script["claims"][0], "source_id": "P03"}]
    script["scenes"][0]["source_ids"] += ["P02", "P03"]
    original = deepcopy(script)
    patched = apply_script_patch(script, [
        {"op": "remove", "path": "/claims/0"},
        {"op": "remove", "path": "/claims/1"},
        {"op": "remove", "path": "/scenes/0/source_ids/0"},
        {"op": "remove", "path": "/scenes/0/source_ids/1"},
    ])
    assert [claim["source_id"] for claim in patched["claims"]] == ["P02"]
    assert patched["scenes"][0]["source_ids"] == ["P02"]
    patched["scenes"][0]["narration"] = "caller-owned new output"
    patched["claims"][0]["text"] = "another changed output"
    assert script == original


@pytest.mark.parametrize("edit", [
    {"op": "replace", "path": "/scenes/-1/narration", "value": "x"},
    {"op": "replace", "path": "/scenes/00/narration", "value": "x"},
    {"op": "replace", "path": "/scenes/０/narration", "value": "x"},
    {"op": "replace", "path": "/scenes/1/narration", "value": "x"},
    {"op": "replace", "path": "/scenes/0/source_ids/1", "value": "P01"},
    {"op": "replace", "path": "/claims/1/quote", "value": "x"},
    {"op": "replace", "path": "/scenes/0/min_display_seconds", "value": "0"},
    {"op": "replace", "path": "/scenes/0/scene_id", "value": "S2"},
    {"op": "replace", "path": "/scenes/0/source_ids", "value": "P01"},
    {"op": "replace", "path": "/claims/0", "value": "x"},
    {"op": "replace", "path": "/rules/chars_per_second", "value": "100"},
    {"op": "replace", "path": "/brief/target_seconds", "value": "300"},
    {"op": "replace", "path": "/checks/rules/passed", "value": "true"},
    {"op": "replace", "path": "/scenes/0/~1narration", "value": "x"},
    {"op": "replace", "path": "/scenes/0/narration~0", "value": "x"},
    {"op": "replace", "path": "scenes/0/narration", "value": "x"},
    {"op": "replace", "path": "", "value": "x"},
    {"op": "replace", "path": "/title/", "value": "x"},
    {"op": "replace", "path": "/__class__", "value": "x"},
    {"op": "remove", "path": "/title"},
    {"op": "remove", "path": "/scenes/0"},
    {"op": "remove", "path": "/claims/0/text"},
    {"op": "remove", "path": "/scenes/0/source_ids/-"},
    {"op": "remove", "path": "/claims/1"},
])
def test_invalid_paths_are_rejected_atomically_even_after_a_valid_edit(script, edit):
    original = deepcopy(script)
    with pytest.raises(ValueError, match=r"edits\[1\]"):
        apply_script_patch(script, [{"op": "replace", "path": "/title", "value": "中间修改"}, edit])
    assert script == original


@pytest.mark.parametrize("edit", [
    None, "replace", [],
    {"op": "add", "path": "/title", "value": "x"},
    {"op": "replace", "path": "/title"},
    {"op": "replace", "path": "/title", "value": 1},
    {"op": "replace", "path": "/title", "value": None},
    {"op": "replace", "path": "/title", "value": True},
    {"op": "replace", "path": ["title"], "value": "x"},
    {"op": "replace", "path": "/title", "value": "x", "reason": "unexpected"},
    {"op": "remove", "path": "/claims/0", "value": None},
])
def test_edit_objects_are_strict(script, edit):
    with pytest.raises(ValueError):
        apply_script_patch(script, [edit])


@pytest.mark.parametrize("edits", [None, {}, (), [], [{"op": "replace", "path": "/title", "value": "x"}] * 21])
def test_edits_list_has_explicit_bounds(script, edits):
    with pytest.raises(ValueError, match="1 至 20"):
        apply_script_patch(script, edits)


def test_twenty_edits_are_allowed_and_apply_in_order(script):
    patched = apply_script_patch(script, [{"op": "replace", "path": "/title", "value": f"Title {index}"} for index in range(20)])
    assert patched["title"] == "Title 19"


@pytest.mark.parametrize("edits", [
    [{"op": "replace", "path": "/title", "value": "字幕操作指南"}],
    [{"op": "replace", "path": "/title", "value": "  字幕操作指南  "}],
    [{"op": "replace", "path": "/title", "value": "中间内容"}, {"op": "replace", "path": "/title", "value": "字幕操作指南"}],
])
def test_effectively_unchanged_patches_are_rejected(script, edits):
    with pytest.raises(ValueError, match="没有变化"):
        apply_script_patch(script, edits)


def test_invalid_final_script_rolls_back_all_edits(script):
    original = deepcopy(script)
    with pytest.raises(ValueError):
        apply_script_patch(script, [
            {"op": "replace", "path": "/title", "value": "中间修改"},
            {"op": "replace", "path": "/scenes/0/narration", "value": ""},
            {"op": "replace", "path": "/scenes/0/subtitle", "value": ""},
        ])
    assert script == original


def test_only_final_structure_must_validate_when_copy_moves_to_subtitles(script):
    script["scenes"][0]["subtitle"] = ""
    patched = apply_script_patch(script, [
        {"op": "replace", "path": "/scenes/0/narration", "value": ""},
        {"op": "replace", "path": "/scenes/0/subtitle", "value": "小剪支持自动生成字幕。"},
    ])
    assert patched["scenes"][0]["narration"] == ""
    assert patched["scenes"][0]["subtitle"]


@pytest.mark.parametrize("edit, expected_issue", [
    ({"op": "replace", "path": "/claims/0/quote", "value": "虚构的原文"}, "QUOTE_NOT_IN_SOURCE"),
    ({"op": "replace", "path": "/scenes/0/narration", "value": "剪辑效率提升80%。"}, "UNSUPPORTED_NUMBER"),
    ({"op": "replace", "path": "/title", "value": "效果保证100%"}, "BANNED_PHRASE"),
    ({"op": "remove", "path": "/claims/0"}, "UNMAPPED_SOURCE"),
])
def test_structurally_valid_edits_still_fail_factual_or_brand_checks(script, materials, edit, expected_issue):
    patched = apply_script_patch(script, [edit])
    report = check_rules(patched, materials, {"banned_phrases": ["保证"]})
    assert report["passed"] is False
    assert expected_issue in {issue["code"] for issue in report["issues"]}
    assert report["requires_semantic_verification"] is True
