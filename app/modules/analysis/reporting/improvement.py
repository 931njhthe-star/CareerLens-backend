"""Conditional improvement examples; never replace assessed evidence or saved scores."""

from copy import deepcopy

from app.modules.analysis.matching.scoring import score_evidence


def improvement_preview(report: dict) -> dict | None:
    """Apply explicit evidence assumptions through the same 70/20/10 rubric."""
    matches = report.get("matches")
    criteria = report.get("criteria", [])
    if (
        report.get("analysis_mode") != "local_rules"
        or not isinstance(matches, list)
        or not matches
        or not isinstance(criteria, list)
        or len(criteria) != 3
        or any(not isinstance(item, dict) for item in criteria)
        or [item.get("max_score") for item in criteria] != [70, 20, 10]
        or any(
            not isinstance(item, dict)
            or not isinstance(item.get("requirement"), str)
            or item.get("status") not in {"confirmed", "partial", "missing"}
            or not isinstance(item.get("contextual"), bool)
            or not isinstance(item.get("quantified"), bool)
            for item in matches
        )
    ):
        return None

    baseline = score_evidence(matches)
    keys = ("alignment", "specificity", "outcomes")
    if baseline["score"] != report.get("score") or any(
        criterion.get("score") != baseline[key] for criterion, key in zip(criteria, keys)
    ):
        return None

    projected = deepcopy(matches)
    assumptions = []
    # Match the report's priority order: missing evidence first, then partial evidence.
    candidates = sorted(
        (index for index, item in enumerate(matches) if item["status"] != "confirmed"),
        key=lambda index: {"missing": 0, "partial": 1}[matches[index]["status"]],
    )[:3]
    for index in candidates:
        item = projected[index]
        item.update(status="confirmed", contextual=True)
        assumptions.append(
            {
                "requirement": item["requirement"],
                "detail": (
                    "실제로 수행한 관련 경험의 본인 역할과 사용한 방법을 보완하여, "
                    "이 항목의 연결 근거가 확인되는 경우를 가정합니다."
                ),
                "kind": "evidence",
            }
        )

    # A measurable result is a separate assumption, never an invented numeric achievement.
    metric_index = next(
        (i for i, item in enumerate(projected) if item["contextual"] and not item["quantified"]),
        None,
    )
    if metric_index is not None:
        projected[metric_index]["quantified"] = True
        assumptions.append(
            {
                "requirement": projected[metric_index]["requirement"],
                "detail": (
                    "이 경험에 실제로 확인 가능한 결과·처리 규모 수치를 추가한 경우를 가정합니다. "
                    "확인할 수 있는 수치가 없다면 적용할 수 없는 가정입니다."
                ),
                "kind": "outcome",
            }
        )
    if not assumptions:
        return None

    scores = score_evidence(projected)
    projected_criteria = deepcopy(criteria)
    for criterion, key in zip(projected_criteria, keys):
        criterion["score"] = scores[key]
    return {
        "basis": "conditional_rules",
        "score": scores["score"],
        "criteria": projected_criteria,
        "assumptions": assumptions,
        "notice": (
            "아래 근거를 모두 보완했다고 가정한 예시입니다. 현재 평가를 변경하지 않으며, "
            "실제 수정 후 점수는 입력한 이력서를 다시 분석해 확인합니다."
        ),
    }
