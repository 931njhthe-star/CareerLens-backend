"""One evidence rubric shared by the detailed report and catalog matching."""


def score_evidence(matches: list[dict]) -> dict:
    """Score requirement coverage, performed work and quantified outcomes."""
    if not matches:
        return {"alignment": 0, "specificity": 0, "outcomes": 0, "score": 0}

    count = len(matches)
    confirmed = sum(item["status"] == "confirmed" for item in matches)
    partial = sum(item["status"] == "partial" for item in matches)
    alignment = round(70 * (confirmed + 0.5 * partial) / count)
    specificity = round(20 * sum(item["contextual"] for item in matches) / count)
    outcomes = round(10 * sum(item["quantified"] for item in matches) / count)
    return {
        "alignment": alignment,
        "specificity": specificity,
        "outcomes": outcomes,
        "score": alignment + specificity + outcomes,
    }
