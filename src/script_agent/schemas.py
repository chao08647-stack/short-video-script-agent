"""Validated public contracts shared by the CLI, graph, and business tools."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Brief(StrictModel):
    # Incomplete briefs are valid requests: the graph asks the human to fill them in.
    topic: NonEmptyText | None = None
    audience: NonEmptyText | None = None
    platform: NonEmptyText | None = None
    target_seconds: Annotated[float, Field(gt=0)] | None = None
    style: NonEmptyText | None = None

    @field_validator("topic", "audience", "platform", "style", mode="before")
    @classmethod
    def blank_means_missing(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    def missing_fields(self) -> list[str]:
        return [name for name in type(self).model_fields if getattr(self, name) is None]


class Scene(StrictModel):
    scene_id: NonEmptyText
    visual: NonEmptyText
    narration: str
    subtitle: str = ""
    source_ids: list[NonEmptyText] = Field(default_factory=list)
    min_display_seconds: Annotated[float, Field(ge=0)] = 1.0

    @model_validator(mode="after")
    def needs_readable_copy(self) -> Scene:
        if not self.narration.strip() and not self.subtitle.strip():
            raise ValueError("A scene must contain narration or subtitles.")
        return self


class Claim(StrictModel):
    text: NonEmptyText
    source_id: NonEmptyText
    quote: NonEmptyText
    scene_id: str = ""


class Script(StrictModel):
    title: NonEmptyText
    scenes: Annotated[list[Scene], Field(min_length=1)]
    claims: list[Claim] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_scene_ids(self) -> Script:
        ids = [scene.scene_id for scene in self.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("Scene IDs must be unique within a script.")
        return self


class Direction(StrictModel):
    angle: NonEmptyText
    outline: Annotated[list[NonEmptyText], Field(min_length=1)]
    source_ids: list[NonEmptyText]
    notes: str = ""


class RunRequest(StrictModel):
    brief: Brief
    dataset: NonEmptyText = "demo"
    notes: str = ""
    initial_script: Script | None = None
    max_model_calls: Annotated[int, Field(ge=1)] = 40
    max_tool_calls: Annotated[int, Field(ge=1)] = 60
    failure_injections: dict[str, Annotated[int, Field(ge=0)]] = Field(default_factory=dict)


__all__ = ["Brief", "Scene", "Claim", "Script", "Direction", "RunRequest"]
