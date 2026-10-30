"""Atomic text/citation edits to an existing script, with a narrow path allowlist.

This validates structure only. Every changed script still needs fresh timing,
brand, and factual checks; edits never carry an approval or check result.
"""

from __future__ import annotations

from copy import deepcopy
import re

from .schemas import Script


_INDEX = r"(0|[1-9][0-9]*)"
_SCENE_TEXT = re.compile(rf"/scenes/{_INDEX}/(visual|narration|subtitle)")
_CLAIM_TEXT = re.compile(rf"/claims/{_INDEX}/(text|source_id|quote|scene_id)")
_SOURCE_ID = re.compile(rf"/scenes/{_INDEX}/source_ids/{_INDEX}")
_CLAIM = re.compile(rf"/claims/{_INDEX}")


def _index(items: list, token: str) -> int:
    index = int(token)
    if index >= len(items):
        raise ValueError(f"索引 {token} 越界；当前列表长度为 {len(items)}。")
    return index


def _target(script: dict, op: str, path: str) -> tuple[dict | list, str | int]:
    """Resolve only approved paths; never interpret escapes or object attributes."""
    if op == "replace":
        if path == "/title":
            return script, "title"
        match = _SCENE_TEXT.fullmatch(path)
        if match:
            scene = script["scenes"][_index(script["scenes"], match[1])]
            return scene, match[2]
        match = _CLAIM_TEXT.fullmatch(path)
        if match:
            claim = script["claims"][_index(script["claims"], match[1])]
            return claim, match[2]
    match = _SOURCE_ID.fullmatch(path)
    if match:
        scene = script["scenes"][_index(script["scenes"], match[1])]
        sources = scene["source_ids"]
        return sources, _index(sources, match[2])
    if op == "remove":
        match = _CLAIM.fullmatch(path)
        if match:
            return script["claims"], _index(script["claims"], match[1])
    raise ValueError(f"不允许 {op} 路径 {path!r}；只能修改白名单中的文字或引用。")


def apply_script_patch(script: dict, edits: list[dict]) -> dict:
    """Apply 1–20 ordered edits to a copy and return a changed, validated script.

    ``replace`` requires exactly ``op``, ``path``, and a string ``value``.
    ``remove`` requires exactly ``op`` and ``path``. Array indices refer to the
    current copy after earlier edits. Escapes, negative/leading-zero indices,
    new fields, scene removal, and timing/configuration edits are disallowed.
    Failure at any point leaves both caller-owned inputs untouched.
    """
    if type(edits) is not list or not 1 <= len(edits) <= 20:
        raise ValueError("edits 必须是包含 1 至 20 个修改对象的列表。")
    original = Script.model_validate(script).model_dump()
    updated = deepcopy(original)
    for position, edit in enumerate(edits):
        try:
            if type(edit) is not dict:
                raise ValueError("每项修改必须是 JSON 对象。")
            op = edit.get("op")
            if op not in ("replace", "remove"):
                raise ValueError("op 只允许 replace 或 remove。")
            expected = {"op", "path", "value"} if op == "replace" else {"op", "path"}
            if set(edit) != expected:
                raise ValueError(f"{op} 必须且只能包含字段：{', '.join(sorted(expected))}。")
            path = edit["path"]
            if not isinstance(path, str):
                raise ValueError("path 必须是白名单中的 JSON Pointer 字符串。")
            if op == "replace" and not isinstance(edit["value"], str):
                raise ValueError("replace 的 value 必须为字符串。")
            parent, key = _target(updated, op, path)
            if op == "replace":
                parent[key] = edit["value"]
            else:
                del parent[key]
        except ValueError as exc:
            raise ValueError(f"edits[{position}]: {exc}") from exc
    validated = Script.model_validate(updated).model_dump()
    if validated == original:
        raise ValueError("修改后稿件内容没有变化，请提供实际文字或引用修订。")
    return validated


__all__ = ["apply_script_patch"]
