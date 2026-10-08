"""Editable prompt registry; read afresh for each run, contained in prompts/."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class PromptEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: str
    enabled: bool = True
    version: str = Field(min_length=1, max_length=60)


class RetrievalSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    top_k: int = Field(default=3, ge=1, le=5)


class Registry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    default: str
    prompts: dict[str, PromptEntry]
    retrieval: RetrievalSettings
    max_retries: int = Field(default=1, ge=0, le=1)
    max_context_chars: int = Field(default=14000, ge=4000, le=20000)


def load_prompt(directory: Path, prompt_id: str | None = None):
    root = directory.resolve()
    registry = Registry.model_validate_json((root / "registry.json").read_text(encoding="utf-8"))
    entry = registry.prompts[prompt_id or registry.default]
    path = (root / entry.file).resolve()
    if not path.is_relative_to(root) or path.suffix != ".md":
        raise ValueError("Prompt must be a Markdown file inside prompts/.")
    text = path.read_text(encoding="utf-8")
    if not 1 <= len(text.strip()) <= 16000:
        raise ValueError("Prompt must contain 1–16000 characters.")
    settings = registry.model_dump()
    settings["coaching_enabled"] = entry.enabled
    return text, f"{registry.version}/{entry.version}", settings
