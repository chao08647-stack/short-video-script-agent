"""Explicit OFFLINE workflow simulator, never evidence of model decisions.

This class deliberately uses fixed conditions. It exists so reviewers can test
LangGraph state, tool errors, review gates, and exports without a model service.
Only ModelClient is used for live runs.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any


class MockModel:
    mode = "mock"

    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.last_usage: dict[str, int] = {}
        self.last_request_count = 0
        self.request_count = 0

    def set_state(self, state: dict[str, Any]) -> None:
        self.state = copy.deepcopy(state)

    def close(self) -> None:
        pass

    def __enter__(self) -> MockModel:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _action(self, tool_name: str, **arguments: Any) -> dict[str, Any]:
        arguments.setdefault("reason", "离线 Mock 固定流程，仅用于验证工程行为。")
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"mock-{self.state.get('model_calls', self.request_count)}",
                    "type": "function",
                    "function": {"name": tool_name, "arguments": json.dumps(arguments, ensure_ascii=False)},
                }
            ],
        }

    def _load(self, name: str) -> dict[str, Any] | None:
        if name not in self.state.get("loaded_skills", {}):
            return self._action("load_skill", name=name)
        return None

    def _used(self, *preferred: str) -> list[str]:
        return [name for name in preferred if name in self.state.get("loaded_skills", {})]

    def _script(self, *, compact: bool = False, revised: bool = False) -> dict[str, Any]:
        materials = self.state.get("retrieved_materials", [])
        material = next((m for m in materials if m.get("source_id") == "P01"), materials[0])
        quote = material["text"]
        # Exact fact copying is intentional in Mock; it does not simulate writing quality.
        fact = (material.get("facts") or [quote])[0]
        if fact not in quote:
            fact = quote
        if compact and "支持自动生成字幕" in quote:
            fact = "支持自动生成字幕"
        feedback_count = len(self.state.get("feedback", []))
        title = "产品功能介绍" + (" · 修改稿" * max(1, feedback_count) if revised else "")
        scenes = []
        if not compact:
            scenes.append({"scene_id": "S1", "visual": "展示创作者准备开始操作的情景。", "narration": "先看看这个功能。", "subtitle": "功能介绍", "source_ids": [], "min_display_seconds": 1.0})
        scenes.append({
            "scene_id": "S2" if scenes else "S1",
            "visual": "展示产品说明中的对应功能文字，供拍摄参考。",
            "narration": fact,
            "subtitle": fact,
            "source_ids": [material["source_id"]],
            "min_display_seconds": 1.0,
        })
        claims = [{"text": fact, "source_id": material["source_id"], "quote": quote, "scene_id": scenes[-1]["scene_id"]}]
        if "手动修改字幕" in self.state.get("notes", ""):
            by_id = {item["source_id"]: item for item in self.state.get("retrieved_materials", [])}
            # The fixed mock keeps both explicitly requested example facts. This
            # remains a deterministic fixture, never evidence of model planning.
            if {"P01", "P02"}.issubset(by_id):
                scenes, claims = [], []
                for index, source_id in enumerate(("P01", "P02"), 1):
                    text = by_id[source_id]["text"]
                    scene_id = f"S{index}"
                    scenes.append({"scene_id": scene_id, "visual": "展示资料所述字幕功能。", "narration": text,
                                   "subtitle": text, "source_ids": [source_id], "min_display_seconds": 1.0})
                    claims.append({"text": text, "source_id": source_id, "quote": text, "scene_id": scene_id})
        return {"title": title, "scenes": scenes, "claims": claims}

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict[str, Any]:
        del messages, tools
        self.request_count += 1
        self.last_request_count = 1
        state = self.state
        brief = state.get("brief", {})
        missing = [key for key in ("topic", "audience", "platform", "target_seconds", "style") if brief.get(key) is None]
        if missing:
            load = self._load("brief-clarification")
            return load or self._action("ask_user", question="请补充创作需求：" + "、".join(missing), fields=missing)

        tool_events = [e for e in state.get("events", []) if e.get("kind") == "tool_result"]
        last = tool_events[-1] if tool_events else None
        if last and last.get("result", {}).get("ok") is False:
            failures = sum(1 for e in tool_events if e.get("tool") == last["tool"] and e.get("result", {}).get("ok") is False)
            if failures == 1:
                return self._action(last["tool"], **{**last["arguments"], "reason": "离线 Mock：观察注入错误后重试一次，保留已有成果。"})
            return self._action("finish_incomplete", reason="离线 Mock：工具重复失败，停止并保留已有成果。")

        if not state.get("retrieved_materials"):
            load = self._load("material-search")
            if load:
                return load
            searches = [e for e in tool_events if e.get("tool") == "search_materials"]
            if not searches:
                tag = re.search(r"内部素材标签为\s+([A-Z0-9_]+)", state.get("notes", ""))
                return self._action("search_materials", query=tag.group(1) if tag else brief["topic"])
            if len(searches) == 1:
                load = self._load("query-rewrite")
                if load:
                    return load
                topic = brief["topic"]
                query = "字幕" if any(word in topic for word in ("字幕", "剪辑", "小剪")) else "耳机" if "耳机" in topic else topic
                return self._action("search_materials", query=query, reason="离线 Mock：首次零结果，使用主题内的简短关键词再查一次。")
            return self._action("ask_user", question="现有资料没有找到支持该主题的产品事实。请补充资料后发起新任务，或取消本次任务。", fields=[])

        phase = state.get("phase", "direction")
        if phase == "direction":
            conflicts = [e for e in tool_events if e.get("tool") == "search_materials" and e.get("result", {}).get("conflicts")]
            if conflicts:
                load = self._load("evidence-conflict")
                return load or self._action("ask_user", question="产品资料存在冲突，需要补充适用范围或可靠依据。", fields=[])
            load = self._load("audience-angle")
            if load:
                return load
            if not state.get("direction") or state.get("revision_required"):
                if state.get("revision_required"):
                    load = self._load("human-feedback")
                    if load:
                        return load
                suffix = "按人工意见调整表达。" * len(state.get("feedback", []))
                return self._action("submit_direction", angle="通过有来源的产品功能说明帮助目标受众理解用途。" + suffix,
                                    outline=["提出使用场景", "说明有依据的产品功能", "提醒按需尝试"],
                                    source_ids=[m["source_id"] for m in state["retrieved_materials"]],
                                    notes="离线 Mock 固定示意方向，不证明真实策划能力。",
                                    used_skills=self._used("material-search", "audience-angle", "human-feedback"))
            return self._action("request_review", reason="离线 Mock：方向已保存，等待人工审核。")

        if state.get("revision_required"):
            load = self._load("human-feedback")
            return load or self._action("submit_script", **self._script(compact=True, revised=True), used_skills=self._used("human-feedback", "claim-grounding"))
        if not state.get("script"):
            for skill in ("storyboard-planning", "narration-subtitles", "claim-grounding"):
                load = self._load(skill)
                if load:
                    return load
            return self._action("submit_script", **self._script(), used_skills=self._used("storyboard-planning", "narration-subtitles", "claim-grounding"))
        checks = state.get("checks", {})
        if "duration" not in checks:
            return self._action("estimate_duration")
        if "rules" not in checks:
            return self._action("check_rules")
        if phase == "draft":
            return self._action("request_review", reason="离线 Mock：初稿及初检报告已准备，等待表达审核。")
        if checks["duration"].get("passed") is not True:
            load = self._load("duration-compression")
            if load:
                return load
            candidate = self._script(compact=True)
            if candidate == state["script"]:
                return self._action("finish_incomplete", reason="离线 Mock：最短有依据稿件仍超时，无法满足目标时长。")
            return self._action("submit_script", **candidate, used_skills=self._used("duration-compression", "claim-grounding"))
        if checks["rules"].get("passed") is not True:
            load = self._load("factual-revision")
            if load:
                return load
            candidate = self._script(compact=True)
            if candidate == state["script"]:
                return self._action("finish_incomplete", reason="离线 Mock：无法通过事实或品牌检查。")
            return self._action("submit_script", **candidate, used_skills=self._used("factual-revision", "claim-grounding"))
        return self._action("request_review", reason="离线 Mock：当前版本检查通过，等待终稿审核。")

    def verify_script(self, script: dict, materials: list[dict]) -> dict:
        self.request_count += 1
        self.last_request_count = 1
        source_map = {m["source_id"]: m for m in materials}
        issues = []
        claims = []
        normalize = lambda value: re.sub(r"[\s，。！？、,.!?：:；;]", "", value)
        for claim in script.get("claims", []):
            source = source_map.get(claim["source_id"])
            supported = bool(source and claim["quote"] in source.get("text", "") and normalize(claim["text"]) in normalize(claim["quote"]))
            claims.append({**claim, "status": "supported" if supported else "unsupported", "reason": "离线字符串对照，不能证明语义支持。"})
            if not supported:
                issues.append({"code": "mock_unsupported", "message": "Mock 仅接受能直接对应原文的断言。"})
        return {"passed": not issues, "issues": issues, "claims": claims, "mode": "mock", "limitation": "仅验证流程与原文子串关系，不检测所有遗漏断言，不证明真实模型事实核验能力。"}
