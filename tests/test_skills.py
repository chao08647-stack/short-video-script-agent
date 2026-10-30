import json
from pathlib import Path

import pytest

from script_agent.skill_registry import SkillError, SkillRegistry


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "brief-clarification", "audience-angle", "platform-adaptation", "narrative-structure",
    "material-search", "query-rewrite", "evidence-conflict", "claim-grounding",
    "hook-writing", "storyboard-planning", "narration-subtitles", "visual-direction",
    "duration-compression", "brand-revision", "factual-revision", "human-feedback",
}


def test_all_sixteen_skills_have_metadata_and_loadable_instructions():
    registry = SkillRegistry(ROOT / "skills")
    catalog = registry.catalog()
    assert {item["name"] for item in catalog} == EXPECTED
    assert all("content" not in item for item in catalog)
    for item in catalog:
        skill = registry.load(item["name"])
        expected_version = "1.1" if item["name"] in {"human-feedback", "visual-direction"} else "1.0"
        assert skill["version"] == item["version"] == expected_version
        assert "输入" in skill["content"]
        assert "产出" in skill["content"]
        assert "验证示例" in skill["content"]
        assert len(skill["sha256"]) == 64


@pytest.mark.parametrize("name", ["../data", "..\\data", "/etc/passwd", "C:\\secret", "unknown", "BRIEF", "a--b"])
def test_loader_rejects_paths_and_unregistered_ids(name):
    with pytest.raises(SkillError):
        SkillRegistry(ROOT / "skills").load(name)


def test_manifest_identity_is_verified(tmp_path):
    directory = tmp_path / "good-name"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        '---\nname: wrong-name\ndescription: demo\nmetadata:\n  version: "1.0"\n---\nInstructions\n',
        encoding="utf-8",
    )
    with pytest.raises(SkillError, match="match its directory"):
        SkillRegistry(tmp_path)


def test_manifest_version_and_yaml_are_validated(tmp_path):
    directory = tmp_path / "demo"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        '---\nname: demo\ndescription: demo\nmetadata:\n  version: 1.0\n---\nInstructions\n',
        encoding="utf-8",
    )
    with pytest.raises(SkillError, match="nonempty string"):
        SkillRegistry(tmp_path)


def test_fingerprint_changes_when_instructions_change(tmp_path):
    directory = tmp_path / "demo"
    directory.mkdir()
    path = directory / "SKILL.md"
    original = '---\nname: demo\ndescription: demo\nmetadata:\n  version: "1.0"\n---\nFirst instructions\n'
    path.write_text(original, encoding="utf-8")
    registry = SkillRegistry(tmp_path)
    before = registry.load("demo")["sha256"]
    path.write_text(original.replace("First", "Updated"), encoding="utf-8")
    assert registry.load("demo")["sha256"] != before


def test_catalog_cannot_mutate_registry():
    registry = SkillRegistry(ROOT / "skills")
    catalog = registry.catalog()
    name = catalog[0]["name"]
    catalog[0]["name"] = "changed"
    assert registry.catalog()[0]["name"] == name


def test_each_skill_has_a_reviewable_scenario_and_existing_input():
    mapping = json.loads((ROOT / "data" / "skill_scenarios.json").read_text(encoding="utf-8"))
    cases = mapping["cases"]
    assert {case["skill_id"] for case in cases} == EXPECTED
    for case in cases:
        assert (ROOT / case["input_file"]).is_file()
        assert case["scenario"] and case["observable_result"]
