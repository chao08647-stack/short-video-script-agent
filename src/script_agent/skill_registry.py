"""Read validated, project-local Agent Skills without executing their contents."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml


_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FRONTMATTER = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n(.*)\Z", re.DOTALL)


class SkillError(ValueError):
    """A skill is unknown, unsafe to read, or has an invalid manifest."""


class SkillRegistry:
    """Discover metadata eagerly and disclose instructions only when requested.

    ``root`` is the dedicated skills directory, not the project root. Skill IDs
    are registry keys rather than file paths. Resources are intentionally not
    executable through this loader.
    """

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise SkillError(f"Skills directory does not exist: {self.root}")
        self._entries: dict[str, dict[str, str]] = {}
        for directory in sorted(self.root.iterdir()):
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            if not (directory / "SKILL.md").is_file():
                continue
            entry = self._read(directory.name)
            if entry["name"] in self._entries:
                raise SkillError(f"Duplicate skill: {entry['name']}")
            self._entries[entry["name"]] = {
                key: entry[key] for key in ("name", "description", "version")
            }

    def catalog(self) -> list[dict[str, str]]:
        """Return short metadata only; full skill bodies are not preloaded."""
        return [dict(self._entries[name]) for name in sorted(self._entries)]

    def load(self, name: str) -> dict[str, str]:
        """Load one registered skill, including its content fingerprint."""
        self._validate_name(name)
        if name not in self._entries:
            raise SkillError(f"Unknown skill: {name}")
        return self._read(name)

    @staticmethod
    def _validate_name(name: str) -> None:
        if not isinstance(name, str) or len(name) > 64 or not _NAME.fullmatch(name):
            raise SkillError("Skill ID must contain lowercase letters, digits and single hyphens")

    def _read(self, name: str) -> dict[str, str]:
        self._validate_name(name)
        path = (self.root / name / "SKILL.md").resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise SkillError("Skill path escapes the registered directory") from exc
        if not path.is_file():
            raise SkillError(f"Missing skill file: {name}")
        text = path.read_text(encoding="utf-8-sig")
        match = _FRONTMATTER.fullmatch(text)
        if not match:
            raise SkillError(f"Skill {name} requires YAML frontmatter and a Markdown body")
        try:
            manifest: Any = yaml.safe_load(match.group(1))
        except yaml.YAMLError as exc:
            raise SkillError(f"Invalid YAML in skill {name}") from exc
        if not isinstance(manifest, dict) or manifest.get("name") != name:
            raise SkillError(f"Skill {name} manifest name must match its directory")
        description = manifest.get("description")
        metadata = manifest.get("metadata")
        if not isinstance(description, str) or not description.strip() or len(description) > 1024:
            raise SkillError(f"Skill {name} requires a nonempty description of at most 1024 characters")
        if not isinstance(metadata, dict):
            raise SkillError(f"Skill {name} requires metadata.version")
        version = metadata.get("version")
        if not isinstance(version, str) or not version.strip():
            raise SkillError(f"Skill {name} metadata.version must be a nonempty string")
        body = match.group(2).strip()
        if not body:
            raise SkillError(f"Skill {name} has no instructions")
        return {
            "name": name,
            "description": description.strip(),
            "version": version.strip(),
            "content": body,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
