"""Resume-to-catalog comparison with stable IDs and no generated matches."""

from collections.abc import Mapping
from functools import lru_cache
from math import isfinite

from app.modules.analysis.matching.rules import _match
from app.modules.analysis.matching.scoring import score_evidence
from app.modules.job_postings.requirements import _requirements
from app.modules.resumes.parsing.evidence import _sources


MATCH_THRESHOLD = 60
MATCH_METHOD = "local_rules_v1"


@lru_cache(maxsize=1_024)
def catalog_requirements(description: str) -> tuple[dict, ...]:
    """Reuse parsed job text, never resume evidence or computed match results.

    The full description is the key, so editing a job takes effect immediately.
    Matching reads these structures without modifying them.
    """
    return tuple(_requirements(description))


def matching_item(posting: dict, sources: list[dict], has_resume: bool) -> dict:
    requirements = catalog_requirements(posting["description"]) if has_resume else ()
    matches = [_match(requirement, sources) for requirement in requirements]
    score = score_evidence(matches)["score"] if requirements else None
    item = {
        "id": posting["id"],
        "company": posting["company"],
        "role": posting["role"],
        "location": posting["location"],
        "source_type": posting.get("source_type", "example"),
        "score": score,
        "matched": score is not None and score >= MATCH_THRESHOLD,
        "status": (
            "scored" if requirements else "resume_required" if not has_resume else "no_requirements"
        ),
        "evidence": [
            {
                "requirement": match["requirement"],
                "status": match["status"],
                "matched_terms": match["matched_terms"],
            }
            for match in matches
        ],
    }
    latitude, longitude = posting.get("latitude"), posting.get("longitude")
    if (
        isinstance(latitude, (int, float))
        and not isinstance(latitude, bool)
        and isinstance(longitude, (int, float))
        and not isinstance(longitude, bool)
        and isfinite(latitude)
        and isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    ):
        item.update(latitude=latitude, longitude=longitude)
    return item


def match_catalog(resume_text: str, postings: list[dict], answers: Mapping | None = None) -> dict:
    """Parse submitted evidence once; evaluate each posting independently."""
    if not isinstance(resume_text, str) or len(resume_text) > 100_000:
        raise ValueError("이력서는 100,000자 이내의 텍스트여야 합니다.")
    if answers is not None and (
        not isinstance(answers, Mapping)
        or len(answers) > 20
        or any(not isinstance(value, str) or len(value) > 10_000 for value in answers.values())
    ):
        raise ValueError("보완 답변은 최대 20개, 각 10,000자 이내의 텍스트여야 합니다.")

    has_resume = bool(resume_text.strip())
    sources = _sources(resume_text, answers) if has_resume else []
    # IDs, not score rank, keep each job anchored when a different resume is used.
    items = [
        matching_item(posting, sources, has_resume)
        for posting in sorted(postings, key=lambda item: item["id"])
    ]
    return {
        "threshold": MATCH_THRESHOLD,
        "method": MATCH_METHOD,
        "status": "no_jobs" if not items else "ready" if has_resume else "resume_required",
        "total_jobs": len(items),
        "evaluated_jobs": sum(item["score"] is not None for item in items),
        "matched_count": sum(item["matched"] for item in items),
        "truncated": False,
        "items": items,
    }
