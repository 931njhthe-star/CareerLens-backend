"""Transparent local comparison, follow-up questions and practice report."""

from __future__ import annotations

from collections.abc import Mapping
from app.modules.resumes.parsing.evidence import _sources
from app.modules.job_postings.requirements import _requirements
from app.modules.analysis.matching.rules import _match
from app.modules.analysis.matching.scoring import score_evidence
from app.modules.analysis.validation.rules import _validate
from app.modules.analysis.reporting.improvement import improvement_preview


def generate_questions(
    resume_text: str, job_text: str, role: str, analysis_context="job_posting"
) -> list[dict]:
    """Ask for missing, relevant evidence; answering is optional and stays separate."""
    _validate(resume_text, job_text, role)
    sources = _sources(resume_text, None)
    matches = [_match(item, sources) for item in _requirements(job_text)]
    questions = []
    for match in sorted(
        matches, key=lambda item: {"missing": 0, "partial": 1, "confirmed": 2}[item["status"]]
    ):
        if match["status"] != "confirmed" and len(questions) < 2:
            questions.append(
                {
                    "id": f"evidence_{len(questions) + 1}",
                    "prompt": (
                        f'공고의 “{match["requirement"][:150]}”와 연결되는 경험이 있나요? '
                        "맡은 일과 사용한 방법을 적어 주세요. 없다면 없다고 적어도 됩니다."
                    ),
                    "reason": "이력서에서 확인되지 않거나 구체적인 수행 근거가 부족한 요구사항입니다.",
                }
            )
    if not any(source["metric"] and source["action"] for source in sources):
        questions.append(
            {
                "id": "outcome",
                "prompt": "지원 직무와 관련된 경험 한 가지의 결과를 적어 주세요. 확인할 수 있는 전후 수치, 처리 규모 또는 산출물이 있다면 함께 적어 주세요.",
                "reason": "수행 결과를 확인할 수 있는 근거를 보완합니다. 수치를 새로 만들어 넣을 필요는 없습니다.",
            }
        )
    elif len(questions) < 3:
        questions.append(
            {
                "id": "ownership",
                "prompt": f"{role}와 연결되는 경험 중 본인이 직접 내린 결정과 맡은 범위를 설명해 주세요.",
                "reason": "팀 전체의 결과와 본인의 기여를 구분하기 위한 질문입니다.",
            }
        )
    if analysis_context == "desired_role":
        for question in questions:
            question["prompt"] = (
                question["prompt"]
                .replace("공고의 “", "희망 직무의 참고 기준 “")
                .replace("지원 직무", "희망 직무")
            )
            question["reason"] = question["reason"].replace("요구사항", "참고 항목")
    return questions[:3]


def analyze(
    resume_text: str,
    company: str,
    role: str,
    job_text: str,
    answers: dict | None = None,
    analysis_context="job_posting",
) -> dict:
    """Compare supplied statements only. Scores describe this rubric, not candidates."""
    _validate(resume_text, job_text, role)
    _validate_answers(answers)

    requirements = _requirements(job_text)
    if not requirements:
        raise ValueError("공고의 구체적인 업무 또는 자격요건을 입력해 주세요.")
    sources = _sources(resume_text, answers)
    matches = [_match(requirement, sources) for requirement in requirements]
    count = len(matches)
    confirmed = [item for item in matches if item["status"] == "confirmed"]
    partial = [item for item in matches if item["status"] == "partial"]
    missing = [item for item in matches if item["status"] == "missing"]

    scores = score_evidence(matches)
    alignment, specificity, outcomes, score = (
        scores[key] for key in ("alignment", "specificity", "outcomes", "score")
    )
    verdict = _recommendation(score, missing)
    summary = _report_summary(company, role, count, confirmed, partial, missing)
    strengths = _report_strengths(confirmed)
    gaps = _report_gaps(missing, partial)
    priorities = _report_priorities(missing, partial, outcomes)
    interview = [
        f'“{item["requirement"][:150]}”와 관련해 본인이 직접 수행한 일과 판단 근거를 설명해 주세요.'
        for item in (partial + missing + confirmed)[:3]
    ]
    email_body = _recruiter_email_body(role, confirmed, missing, partial)

    report = {
        "score": score,
        "verdict": verdict,
        "summary": summary,
        "criteria": [
            {
                "label": "공고 요구사항 연결",
                "score": alignment,
                "max_score": 70,
                "detail": f"수행 근거 확인 {len(confirmed)}개 × 1, 부분 연결 {len(partial)}개 × 0.5 / 요구사항 {count}개",
            },
            {
                "label": "수행 맥락",
                "score": specificity,
                "max_score": 20,
                "detail": "연결된 근거에서 수행·역할을 나타내는 표현이 있는 요구사항 비율",
            },
            {
                "label": "수치로 표현한 결과·규모",
                "score": outcomes,
                "max_score": 10,
                "detail": "연결된 수행 근거에서 결과·규모 수치가 나타나는 요구사항 비율",
            },
        ],
        "matches": matches,
        "strengths": strengths,
        "gaps": gaps,
        "priorities": priorities,
        "questions": interview,
        "recruiter_email": {
            "subject": f"[모의 예시] {role.strip()} 지원 자료 추가 확인",
            "body": email_body,
        },
        "methodology": (
            "외부 AI 호출 없이 한국어·영어 동의어와 공고 문장별 단어를 비교하는 로컬 규칙 기반 분석입니다. 공고에서 중복을 제외한 "
            "최대 12개 요구사항을 순서대로 비교합니다. 요구사항 연결 70점, 수행 맥락 20점, 수치로 표현한 결과·규모 10점으로 "
            "계산합니다. 중복 문장과 동일 기술의 반복은 가산하지 않습니다. 보완 답변은 이력서와 별도 출처로 표시합니다. 실제 경험의 "
            "진위·수준·필수 경력 연수·자격 충족 여부를 검증하지 않으며 동의어나 문맥을 놓칠 수 있습니다. 점수는 이 도구의 근거 "
            "충족도이며 지원자 순위, 합격률 또는 실제 채용 판단이 아닙니다."
        ),
        "analysis_mode": "local_rules",
        "company": company.strip(),
        "role": role.strip(),
        "requirement_count": count,
        "confirmed_count": len(confirmed),
        "partial_count": len(partial),
        "missing_count": len(missing),
    }
    if analysis_context == "desired_role":
        _apply_desired_role_context(report, role)
    report["improvement_preview"] = improvement_preview(report)
    return report


def _validate_answers(answers: Mapping | None) -> None:
    if answers is not None and not isinstance(answers, Mapping):
        raise ValueError("보완 답변은 질문과 답변을 연결한 형식이어야 합니다.")
    if answers and (
        len(answers) > 20
        or any(not isinstance(v, str) or len(v) > 10_000 for v in answers.values())
    ):
        raise ValueError("보완 답변은 최대 20개, 각 10,000자 이내의 텍스트여야 합니다.")


def _recommendation(score: float, missing: list[dict]) -> str:
    if score >= 80 and not missing:
        return "근거 정리 후 지원 권장"
    if score >= 55:
        return "핵심 근거 보완 후 지원 권장"
    return "직무 연결 근거부터 보완 권장"


def _report_summary(
    company: str,
    role: str,
    count: int,
    confirmed: list[dict],
    partial: list[dict],
    missing: list[dict],
) -> str:
    destination = f"{company.strip() or '지원 기업'} {role.strip()}"
    summary = (
        f"{destination} 공고의 요구사항 {count}개 중 "
        f"{len(confirmed)}개에서 수행 근거가 확인되었고, "
        f"{len(partial)}개는 부분적으로 연결됩니다. "
    )
    if missing:
        summary += (
            f"{len(missing)}개는 제출한 내용에서 근거를 찾지 못했습니다. "
            "실제 경험이 있다면 맡은 역할과 결과를 구체적으로 보완해 주세요."
        )
    elif partial:
        summary += "부분적으로 연결되는 항목에 본인이 수행한 일과 결과를 추가하면 지원서를 더 명확하게 만들 수 있습니다."
    else:
        summary += "연결된 경험의 본인 기여와 결과를 확인한 뒤 지원서에 반영해 주세요."
    return summary


def _report_strengths(confirmed: list[dict]) -> list[str]:
    strengths = [
        f'{item["requirement"]} — {", ".join(item["matched_terms"])}에 연결되는 '
        f'{item["source_label"]} 근거가 있습니다.'
        for item in confirmed[:4]
    ]
    if not strengths:
        strengths = [
            "현재 제출한 내용만으로 명확하게 확인된 직무 강점이 없습니다. 연결 가능한 경험을 구체적으로 적어 주세요."
        ]
    return strengths


def _report_gaps(missing: list[dict], partial: list[dict]) -> list[str]:
    gaps = [
        f'{item["requirement"]} — '
        + (
            f'추가 확인: {", ".join(item["missing_terms"])}.'
            if item["missing_terms"]
            else "단어 언급을 넘어 직접 수행한 역할과 결과가 필요합니다."
        )
        for item in (missing + partial)[:6]
    ]
    if not gaps:
        gaps = [
            "현재 비교한 요구사항에서 추가 확인이 필요한 항목은 없습니다. 본인 기여와 수치는 직접 확인하세요."
        ]
    return gaps


def _report_priorities(missing: list[dict], partial: list[dict], outcomes: float) -> list[dict]:
    priorities = [
        {
            "title": f'요구사항 근거 보완: {item["requirement"][:90]}',
            "detail": (
                "실제로 수행한 경험이 있다면 상황, 본인이 맡은 일, 사용한 방법, 확인 가능한 결과를 한두 문장으로 추가하세요. 경험이 "
                "없다면 보유한 것처럼 작성하지 마세요."
            ),
        }
        for item in (missing + partial)[:3]
    ]
    if not priorities:
        priorities.append(
            {
                "title": "핵심 경험의 본인 기여 확인",
                "detail": "공고와 연결되는 경험을 앞에 배치하고, 팀 성과와 본인이 직접 수행한 부분을 구분해 주세요.",
            }
        )
    if outcomes < 5 and len(priorities) < 3:
        priorities.append(
            {
                "title": "확인 가능한 수행 결과 추가",
                "detail": "관련 경험의 전후 변화, 처리 규모, 산출물을 적어 주세요. 실제로 확인할 수 있는 수치만 사용하세요.",
            }
        )
    return priorities


def _recruiter_email_body(
    role: str,
    confirmed: list[dict],
    missing: list[dict],
    partial: list[dict],
) -> str:
    email_body = f"안녕하세요. 제출하신 {role.strip()} 지원 자료를 검토하는 상황을 가정한 연습용 메일입니다.\n\n"
    if confirmed:
        email_body += (
            f"지원 자료에서 ‘{confirmed[0]['requirement'][:150]}’와 연결되는 경험을 확인했습니다. "
        )
    else:
        email_body += "현재 자료에서는 직무 요구사항과 연결되는 구체적인 수행 근거를 충분히 확인하기 어렵습니다. "

    if missing or partial:
        email_body += f"‘{(missing + partial)[0]['requirement'][:150]}’에 대한 본인의 역할과 결과를 추가로 설명해 주세요."
    else:
        email_body += "대표 경험에서 본인이 맡은 범위와 결과를 판단한 기준을 설명해 주세요."
    email_body += "\n\n이 메일은 제출한 내용으로 만든 모의 예시이며 실제 기업의 회신이나 전형 결과가 아닙니다."
    return email_body


def _apply_desired_role_context(report: dict, role: str) -> None:
    report["assessment_context"] = "desired_role"
    report["reference_source"] = "internal_role_reference"
    report["company"] = ""
    report["verdict"] = {
        "근거 정리 후 지원 권장": "직무 경험의 근거가 구체적으로 정리되어 있어요",
        "핵심 근거 보완 후 지원 권장": "핵심 경험의 근거를 보완해 보세요",
        "직무 연결 근거부터 보완 권장": "희망 직무와 연결되는 경험부터 정리해 보세요",
    }[report["verdict"]]
    report["summary"] = (
        f'희망 직무 ‘{role}’의 내부 참고 기준 {report["requirement_count"]}개 중 '
        f'{report["confirmed_count"]}개에서 수행 근거가 확인되었고, '
        f'{report["partial_count"]}개는 부분적으로 연결되며, '
        f'{report["missing_count"]}개는 제출한 내용에서 근거를 찾지 못했습니다. '
        "이력서에 적힌 경험을 정리하기 위한 분석이며 실제 채용공고와 비교한 결과는 아닙니다."
    )
    report["criteria"][0]["label"] = "희망 직무 경험 연결"
    report["criteria"][0]["detail"] = report["criteria"][0]["detail"].replace(
        "요구사항", "참고 항목"
    )
    for criterion in report["criteria"][1:]:
        criterion["detail"] = criterion["detail"].replace("요구사항", "참고 항목")
    report["gaps"] = [item.replace("요구사항", "참고 항목") for item in report["gaps"]]
    for priority in report["priorities"]:
        priority["title"] = priority["title"].replace("요구사항", "직무 경험")
        priority["detail"] = priority["detail"].replace("공고와 연결되는", "희망 직무와 연결되는")
    report["methodology"] = (
        "CareerLens가 작성한 직무별 연습용 내부 참고 기준과 제출한 이력서의 표현을 비교하는 로컬 규칙 기반 분석입니다. "
        "직접 입력한 직무에는 공통 경험 기준을 사용하며, 관심 분야는 사용자가 입력한 참고 정보입니다. "
        "희망 직무 경험 연결 70점, 수행 맥락 20점, 수치로 표현한 결과·규모 10점으로 계산합니다. "
        "실제 채용공고, 공식 직업 표준 또는 실시간 외부 데이터에 근거한 점수가 아닙니다. "
        "중복 표현은 가산하지 않고, 보완 답변은 별도 출처로 표시합니다. "
        "실제 경험의 진위·수준·경력 연수·자격 충족을 검증하지 않으며 지원자 순위나 합격률을 뜻하지 않습니다."
    )
