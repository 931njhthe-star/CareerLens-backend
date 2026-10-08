"""Small local keyword retriever. This is not embedding/vector search."""

import json
import re
from pathlib import Path
from pydantic import BaseModel, Field


class Guidance(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{1,60}$")
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=2000)
    source: str = Field(min_length=1, max_length=250)
    keywords: list[str] = Field(min_length=1, max_length=40)


class Corpus(BaseModel):
    documents: list[Guidance] = Field(max_length=500)


def retrieve_guidance(query: str, path: Path, top_k=3) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    if len(raw) > 2_000_000:
        raise ValueError("Guidance corpus is too large.")
    documents = [item.model_dump() for item in Corpus.model_validate_json(raw).documents]
    if len({item["id"] for item in documents}) != len(documents):
        raise ValueError("Guidance IDs must be unique.")
    terms = set(re.findall(r"[a-zA-Z0-9가-힣+#.]+", query.casefold()))
    ranked = []
    for document in documents:
        score = sum(
            1
            for keyword in document["keywords"]
            if any(keyword.casefold() in term for term in terms)
        )
        if score:
            ranked.append(
                {key: document[key] for key in ("id", "title", "text", "source")} | {"score": score}
            )
    return sorted(ranked, key=lambda item: (-item["score"], item["id"]))[: max(1, min(top_k, 5))]
