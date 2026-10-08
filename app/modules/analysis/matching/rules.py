"""Deterministic evidence matching with bounded, attributable excerpts."""

from __future__ import annotations


def _match(requirement: dict, sources: list[dict]) -> dict:
    term_key = "concepts" if requirement["kind"] == "concept" else "tokens"
    candidates = [(source, requirement["terms"] & source[term_key]) for source in sources]
    candidates = [(source, shared) for source, shared in candidates if shared]
    candidates.sort(
        key=lambda item: (item[0]["action"], len(item[1]), item[0]["metric"]), reverse=True
    )
    covered, evidence_items = set(), []
    for source, shared in candidates:
        if shared - covered and len(evidence_items) < 3:
            covered.update(shared)
            evidence_items.append(source)
    groups = requirement["groups"]
    coverage = sum(bool(group & covered) for group in groups) / len(groups)
    contextual = any(item["action"] for item in evidence_items)
    threshold = 0.8 if requirement["kind"] == "concept" else 0.6
    status = (
        "confirmed" if coverage >= threshold and contextual else "partial" if covered else "missing"
    )
    origin_set = {item["source"] for item in evidence_items}
    source_name = (
        next(iter(origin_set)) if len(origin_set) == 1 else "mixed" if origin_set else "none"
    )
    return {
        "requirement": requirement["text"],
        "evidence": (
            " / ".join(item["text"] for item in evidence_items)
            if evidence_items
            else "제출한 내용에서 연결되는 근거를 찾지 못했습니다."
        ),
        "status": status,
        "source": source_name,
        "source_label": {
            "resume": "이력서",
            "answer": "보완 답변",
            "mixed": "이력서 + 보완 답변",
            "none": "근거 없음",
        }[source_name],
        "evidence_items": [
            {
                "excerpt": item["text"],
                "source": item["source"],
                "source_label": item["source_label"],
            }
            for item in evidence_items
        ],
        "matched_terms": sorted(covered),
        "missing_terms": [" 또는 ".join(sorted(group)) for group in groups if not group & covered],
        "contextual": contextual,
        "quantified": any(item["metric"] and item["action"] for item in evidence_items),
    }
