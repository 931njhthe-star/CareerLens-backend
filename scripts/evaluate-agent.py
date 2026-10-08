"""Reproducible injected-error comparison, never a live-model benchmark."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agent.graphs.analysis import build_graph, validate_coaching
from app.agent.prompts.loader import load_prompt
from app.modules.analysis.reporting.service import analyze
from app.retrieval.search.local import retrieve_guidance


def main():
    inputs = {
        "resume_text": "Python으로 주문 API를 구현하고 SQL 인덱스를 개선했습니다. 테스트 24개를 작성하고 Docker로 배포했습니다.",
        "company": "가상 평가 기업",
        "role": "Python 백엔드 개발자",
        "job_text": "Python API 개발 경험이 필요합니다. SQL 모델 설계 및 Docker 배포 경험이 필요합니다.",
        "answers": {},
    }
    prompt, version, settings = load_prompt(ROOT / "app/agent/prompts")
    references = retrieve_guidance(
        inputs["job_text"], ROOT / "data/knowledge/policies/career-guidance.json"
    )
    original = analyze(**inputs)
    rows = []
    for scenario in (
        "valid",
        "quote_repaired",
        "invalid_schema",
        "unknown_reference",
        "provider_timeout",
    ):

        def coach(state):
            if scenario == "provider_timeout":
                raise TimeoutError("synthetic timeout")
            candidate = {
                "summary": "담당한 API 작업과 검증 범위를 구체화합니다.",
                "recommendations": [
                    {
                        "text": "직접 작성한 테스트의 대상을 명시해 보세요.",
                        "evidence_quote": "Python으로 주문 API를 구현하고",
                    }
                ],
                "reference_ids": [],
            }
            if scenario == "quote_repaired" and state["retry_count"] == 0:
                candidate["recommendations"][0]["evidence_quote"] = "원문에 없는 매출 상승 900%"
            if scenario == "invalid_schema":
                candidate["score"] = 100
            if scenario == "unknown_reference":
                candidate["reference_ids"] = ["invented-document"]
            return candidate

        baseline_state = {
            **inputs,
            "report": original,
            "references": references,
            "settings": settings,
            "retry_count": 0,
            "current_error": "",
            "prompt_text": prompt,
        }
        try:
            baseline_value = coach(baseline_state)
            baseline_valid, error = validate_coaching(baseline_value, baseline_state)
            baseline_received = True
        except TimeoutError:
            baseline_valid, error, baseline_received = None, "provider_error", False
        report = build_graph(coach=coach).invoke(
            {**inputs, "mode": "llm"}, {"recursion_limit": 16}
        )["report"]
        final_coaching = report.get("ai_coaching")
        checked_coaching, _ = (
            validate_coaching(final_coaching, baseline_state) if final_coaching else (None, "")
        )
        rows.append(
            {
                "scenario": scenario,
                "injected_error": error or None,
                "baseline_valid_coaching": bool(baseline_valid),
                "baseline_invalid_output_passed_through": baseline_received
                and not bool(baseline_valid),
                "after_valid_coaching": bool(checked_coaching),
                "after_invalid_output_passed_through": bool(final_coaching)
                and not bool(checked_coaching),
                "after_errors": report["agent"]["error_codes"],
                "after_fallback": report["agent"]["fallback_used"],
                "after_retries": report["agent"]["retry_count"],
                "after_score_unchanged": report["score"] == original["score"],
                "after_workflow_completed": report["agent"]["steps"][-1] == "finish",
            }
        )
    count = len(rows)
    output = {
        "evaluation_version": "1.0.0",
        "workflow_version": "1.0.0",
        "prompt_version": version,
        "kind": "offline_synthetic_fault_injection",
        "case_count": count,
        "baseline_definition": "One structured-coaching attempt with no correction or fallback; candidates are checked only by the evaluation harness.",
        "scope": "Synthetic responses, not actual LLM output. Does not measure hiring quality, autonomous tool selection, retrieval relevance or production reliability.",
        "metrics": {
            "baseline_valid_coaching_rate": sum(row["baseline_valid_coaching"] for row in rows)
            / count,
            "after_valid_coaching_rate": sum(row["after_valid_coaching"] for row in rows) / count,
            "baseline_invalid_outputs_passed_through": sum(
                row["baseline_invalid_output_passed_through"] for row in rows
            ),
            "after_invalid_outputs_passed_through": sum(
                row["after_invalid_output_passed_through"] for row in rows
            ),
            "after_workflow_completion_rate": sum(row["after_workflow_completed"] for row in rows)
            / count,
            "after_score_consistency_rate": sum(row["after_score_unchanged"] for row in rows)
            / count,
            "after_retry_count": sum(row["after_retries"] for row in rows),
            "after_average_retries": sum(row["after_retries"] for row in rows) / count,
            "tool_selection_accuracy": None,
            "retry_reduction": None,
        },
        "cases": rows,
    }
    destination = ROOT / "evaluations/results/agent-baseline-v1.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(output["metrics"], indent=2))


if __name__ == "__main__":
    main()
