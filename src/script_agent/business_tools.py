"""Deterministic local tools; semantic support requires separate verification.

These functions never mutate materials, invent facts, call a model, or silently
alter the caller's target duration. Their JSON-compatible results are observations
for the agent, not instructions selecting its next action.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Any

from pydantic import ValidationError

from .schemas import Script


_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U0002ebef]")
_HAN_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_WORD = re.compile(r"[a-zA-Z]+(?:['’-][a-zA-Z]+)*")
_NUMBER = re.compile(r"\d+(?:\.\d+)?\s*[%％]?")
_SPACE = re.compile(r"\s+")


def _normal(text: str) -> str:
    return _SPACE.sub("", unicodedata.normalize("NFKC", text)).casefold()


def _issue(code: str, message: str, **context: Any) -> dict:
    return {"code": code, "message": message, **context}


def _material_index(materials: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for material in materials:
        source_id = material.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("Each material needs a non-empty source_id.")
        if source_id in index:
            raise ValueError(f"Duplicate material source_id: {source_id}")
        if not isinstance(material.get("text"), str):
            raise ValueError(f"Material {source_id} needs original text.")
        index[source_id] = material
    return index


def _query_tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens = set(re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", normalized))
    for segment in _HAN_RUN.findall(normalized):
        if len(segment) == 1:
            tokens.add(segment)
        else:
            tokens.update(segment[i : i + 2] for i in range(len(segment) - 1))
    return tokens


def _conflicts(materials: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for material in materials:
        group = material.get("conflict_group")
        if group:
            groups.setdefault(str(group), []).append(material)
    return [
        {
            "group": group,
            "source_ids": [item["source_id"] for item in items],
            "message": "同一冲突组存在不同资料，未提供适用范围或优先级时不能自动选取其一。",
        }
        for group, items in groups.items()
        if len(items) > 1 and len({_normal(item["text"]) for item in items}) > 1
    ]


def search_materials(query: str, materials: list[dict], limit: int = 5) -> dict:
    """Lexical search using Chinese bigrams, English tokens, and keyword matches.

    No web retrieval or embeddings are implied. Queries with no lexical overlap
    return an empty result, allowing a real model to rewrite or ask for evidence.
    Explicitly grouped conflicting records are included in conflict diagnostics
    even if only one record enters the top-k results.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("limit must be an integer between 1 and 20")
    _material_index(materials)
    query_normal = _normal(query)
    tokens = _query_tokens(query)
    document_tokens: list[set[str]] = []
    for item in materials:
        fields = [item.get("title", ""), item["text"], *item.get("facts", []), *item.get("keywords", [])]
        document_tokens.append(_query_tokens(" ".join(str(field) for field in fields)))
    frequency = Counter(token for doc in document_tokens for token in doc)
    scored: list[tuple[float, dict]] = []
    for item, doc in zip(materials, document_tokens):
        score = sum(math.log(1 + (len(materials) + 1) / (frequency[token] + 1)) for token in tokens & doc)
        source_normal = _normal(item["source_id"])
        if source_normal and source_normal in query_normal:
            score += 10
        title = _normal(str(item.get("title", "")))
        if title and (title in query_normal or query_normal in title):
            score += 3
        for keyword in item.get("keywords", []):
            keyword_normal = _normal(str(keyword))
            if keyword_normal and (keyword_normal in query_normal or query_normal in keyword_normal):
                score += 2
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["source_id"]))
    matches = [{**item, "score": round(score, 4)} for score, item in scored[:limit]]
    matched_groups = {item.get("conflict_group") for item in matches if item.get("conflict_group")}
    conflicts = [conflict for conflict in _conflicts(materials) if conflict["group"] in matched_groups]
    return {"query": query, "matches": matches, "count": len(matches), "conflicts": conflicts}


def _positive_setting(rules: dict, name: str, default: float) -> float:
    value = rules.get(name, default)
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return float(value)


def _nonnegative_setting(rules: dict, name: str, default: float) -> float:
    value = rules.get(name, default)
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a non-negative finite number")
    return float(value)


def _text_seconds(text: str, chars_rate: float, words_rate: float, pauses: bool) -> float:
    text = unicodedata.normalize("NFKC", text)
    words = len(_WORD.findall(text))
    remaining = _WORD.sub("", text)
    # Digits count as individual spoken units; arbitrary numeric verbalization
    # and abbreviations remain a documented estimation limitation.
    characters = sum(1 for char in remaining if char.isalpha() or char.isdigit())
    pause_seconds = 0.0
    if pauses:
        pause_seconds += len(re.findall(r"[,，、;；:：]", text)) * 0.2
        pause_seconds += len(re.findall(r"[。!?！？]|(?<!\d)\.(?!\d)", text)) * 0.4
    return characters / chars_rate + words / words_rate + pause_seconds


def _ceil_seconds(value: float) -> float:
    return math.ceil((value - 1e-9) * 100) / 100


def estimate_duration(script: dict, rules: dict, target_seconds: float) -> dict:
    """Calculate a conservative, inspectable estimate for the supplied version."""
    draft = Script.model_validate(script)
    if type(target_seconds) not in (int, float) or not math.isfinite(target_seconds) or target_seconds <= 0:
        raise ValueError("target_seconds must be positive and finite")
    chars_rate = _positive_setting(rules, "chars_per_second", 4.0)
    subtitle_rate = _positive_setting(rules, "subtitle_chars_per_second", 6.0)
    words_rate = _positive_setting(rules, "english_words_per_second", 2.5)
    minimum = _nonnegative_setting(rules, "minimum_scene_seconds", 1.0)
    transition = _nonnegative_setting(rules, "transition_seconds", 0.0)
    rows: list[dict] = []
    total = 0.0
    for index, scene in enumerate(draft.scenes):
        narration = _text_seconds(scene.narration, chars_rate, words_rate, pauses=True)
        subtitles = _text_seconds(scene.subtitle, subtitle_rate, words_rate, pauses=False)
        visual_minimum = max(minimum, scene.min_display_seconds)
        estimated = _ceil_seconds(max(narration, subtitles, visual_minimum))
        if index:
            total += transition
        rows.append({
            "scene_id": scene.scene_id,
            "narration_seconds": _ceil_seconds(narration),
            "subtitle_seconds": _ceil_seconds(subtitles),
            "min_display_seconds": visual_minimum,
            "estimated_seconds": estimated,
            "start_seconds": round(total, 2),
            "end_seconds": round(total + estimated, 2),
        })
        total += estimated
    total = _ceil_seconds(total)
    passed = total <= target_seconds
    issues = [] if passed else [_issue(
        "TIME_LIMIT_EXCEEDED",
        f"预计 {total:g} 秒，超过目标 {target_seconds:g} 秒。请修改内容或请求用户调整要求。",
        excess_seconds=round(total - target_seconds, 2),
    )]
    return {
        "passed": passed,
        "estimated_seconds": total,
        "target_seconds": target_seconds,
        "scenes": rows,
        "issues": issues,
        "assumptions": {
            "chars_per_second": chars_rate,
            "subtitle_chars_per_second": subtitle_rate,
            "english_words_per_second": words_rate,
            "minimum_scene_seconds": minimum,
            "transition_seconds": transition,
            "timing_rule": "每镜取旁白、字幕阅读、画面最低展示时间的最大值；镜头串行累计。",
            "limitation": "文字估时，不是实际录音或成片时长；数字、缩写及表演节奏可能存在误差。",
        },
    }


def _structural_number(text: str, start: int, end: int) -> bool:
    """Allow explicit storyboard/tutorial numbering, never percentages."""
    value = text[start:end]
    if "%" in value or "％" in value:
        return False
    before, after = text[max(0, start - 4) : start], text[end : end + 8]
    return bool(
        re.search(r"(?:步骤|镜头|第)$", before)
        or re.match(r"(?:个)?(?:步骤|镜头|步)(?!提升|提高)", after)
        or re.match(r"秒(?:带你|教你|看懂|了解)", after)
    )


def check_rules(script: dict, materials: list[dict], rules: dict) -> dict:
    """Check deterministic constraints; this does NOT establish semantic support.

    The caller must perform a separate semantic verifier pass to detect uncited
    qualitative claims, mismatched entities, and misleading paraphrases. A valid
    source ID or quote is never represented as complete fact verification here.
    """
    try:
        draft = Script.model_validate(script)
    except ValidationError as exc:
        return {
            "passed": False,
            "issues": [_issue("INVALID_SCRIPT", "脚本结构不合法或缺少可读内容。", errors=exc.errors(include_url=False, include_context=False))],
            "scope": "deterministic_only",
            "requires_semantic_verification": True,
            "semantic_status": "not_checked",
        }
    sources = _material_index(materials)
    scenes = {scene.scene_id: scene for scene in draft.scenes}
    issues: list[dict] = []
    fields: list[tuple[str, str, str]] = [("", "title", draft.title)]
    for scene in draft.scenes:
        fields.extend((scene.scene_id, name, getattr(scene, name)) for name in ("visual", "narration", "subtitle"))
        for source_id in scene.source_ids:
            if source_id not in sources:
                issues.append(_issue("UNKNOWN_SOURCE", "分镜引用的资料不存在。", scene_id=scene.scene_id, source_id=source_id))
    valid_claims = []
    for index, claim in enumerate(draft.claims):
        context = {"claim_index": index, "scene_id": claim.scene_id, "source_id": claim.source_id}
        if claim.source_id not in sources:
            issues.append(_issue("UNKNOWN_SOURCE", "断言引用的资料不存在。", **context))
            continue
        if claim.scene_id and claim.scene_id not in scenes:
            issues.append(_issue("UNKNOWN_SCENE", "断言引用的分镜不存在。", **context))
            continue
        if _normal(claim.quote) not in _normal(sources[claim.source_id]["text"]):
            issues.append(_issue("QUOTE_NOT_IN_SOURCE", "引用原文不在对应资料中。", **context))
            continue
        scoped_fields = [text for scene_id, _, text in fields if not claim.scene_id or scene_id == claim.scene_id]
        if not any(_normal(claim.text) in _normal(text) for text in scoped_fields):
            issues.append(_issue("CLAIM_NOT_IN_SCRIPT", "断言文句未出现在对应脚本内容中。", **context))
            continue
        if claim.scene_id and claim.source_id not in scenes[claim.scene_id].source_ids:
            issues.append(_issue("CLAIM_SOURCE_NOT_ATTACHED", "分镜来源列表缺少断言所用资料。", **context))
        valid_claims.append(claim)
    for scene in draft.scenes:
        scene_text = _normal(" ".join((scene.visual, scene.narration, scene.subtitle)))
        for source_id in scene.source_ids:
            if source_id in sources and not any(
                claim.source_id == source_id
                and (not claim.scene_id or claim.scene_id == scene.scene_id)
                and _normal(claim.text) in scene_text
                for claim in valid_claims
            ):
                issues.append(_issue("UNMAPPED_SOURCE", "来源 ID 需要对应脚本文句及支持原文，不能只挂一个引用。", scene_id=scene.scene_id, source_id=source_id))
    for banned in rules.get("banned_phrases", []):
        phrase = banned.get("phrase", "") if isinstance(banned, dict) else str(banned)
        if not phrase:
            continue
        for scene_id, field, text in fields:
            if _normal(phrase) in _normal(text):
                issues.append(_issue("BANNED_PHRASE", f"出现品牌禁用表述：{phrase}", scene_id=scene_id, field=field, phrase=phrase))
    if rules.get("check_unsupported_numbers", True):
        for scene_id, field, text in fields:
            for match in _NUMBER.finditer(unicodedata.normalize("NFKC", text)):
                normalized_text = unicodedata.normalize("NFKC", text)
                if _structural_number(normalized_text, match.start(), match.end()):
                    continue
                number = _normal(match.group())
                supported = any(
                    (not claim.scene_id or claim.scene_id == scene_id)
                    and _normal(claim.text) in _normal(text)
                    and number in {_normal(item.group()) for item in _NUMBER.finditer(unicodedata.normalize("NFKC", claim.text))}
                    and number in {_normal(item.group()) for item in _NUMBER.finditer(unicodedata.normalize("NFKC", claim.quote))}
                    for claim in valid_claims
                )
                if not supported:
                    issues.append(_issue("UNSUPPORTED_NUMBER", "数字表述缺少对应文句及支持原文；结构性步骤编号除外。", scene_id=scene_id, field=field, number=match.group().strip()))
    used_ids = {source_id for scene in draft.scenes for source_id in scene.source_ids} | {claim.source_id for claim in draft.claims}
    for conflict in _conflicts(materials):
        if used_ids.intersection(conflict["source_ids"]):
            issues.append(_issue("CONFLICTING_SOURCES", conflict["message"], source_ids=conflict["source_ids"], conflict_group=conflict["group"]))
    return {
        "passed": not issues,
        "issues": issues,
        "scope": "deterministic_only",
        "requires_semantic_verification": True,
        "semantic_status": "not_checked",
        "checked_claims": len(draft.claims),
        "valid_quote_mappings": len(valid_claims),
    }
