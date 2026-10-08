"""Read fictional examples from the configured DB, never from user uploads."""

import json
from pathlib import Path

from flask import current_app, has_app_context

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "data/examples"
PATH = EXAMPLES_DIR / "resumes.json"


def load_examples():
    """Load 20 existing and 200 new fixtures for application startup seeding."""
    items = []
    for filename in ("resumes.json", "synthetic_resumes.json"):
        items.extend(json.loads((EXAMPLES_DIR / filename).read_text(encoding="utf-8"))["items"])
    return items


def _repository():
    if has_app_context():
        return current_app.extensions.get("resume_example_repository")
    return None


def list_examples():
    repository = _repository()
    if repository is not None:
        return repository.list()
    items = load_examples()
    return [
        {key: value for key, value in item.items() if key not in {"resume_text", "resume_sections"}}
        for item in items
    ]


def get_example(example_id):
    repository = _repository()
    if repository is not None:
        return repository.get(example_id)
    items = load_examples()
    return next((item for item in items if item["id"] == example_id), None)
