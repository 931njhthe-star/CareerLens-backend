"""Job source adapter boundary; the default adapter performs no network calls."""

import json
from pathlib import Path
from typing import Protocol


class JobSource(Protocol):
    def load_examples(self) -> list[dict]:
        """Return synthetic normalized postings; never overwrite user-owned data."""
        ...


class LocalExampleSource:
    def __init__(self, path, additional_paths=()):
        self.path = Path(path)
        self.additional_paths = tuple(Path(item) for item in additional_paths)

    def load_examples(self):
        items = []
        for path in (self.path, *self.additional_paths):
            items.extend(json.loads(path.read_text(encoding="utf-8")))
        if len({item["id"] for item in items}) != len(items):
            raise ValueError("Bundled job examples must have unique IDs.")
        return items
