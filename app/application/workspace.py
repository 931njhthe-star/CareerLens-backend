"""Resume → job → optional evidence → practice application use cases."""

from datetime import datetime, timedelta, timezone
from copy import deepcopy
from pathlib import Path

from app.integrations.document_parsers.resume import extract_resume
from app.modules.analysis.reporting.service import generate_questions
from app.modules.analysis.reporting.improvement import improvement_preview
from app.agent.graphs.analysis import analyze_with_agent as analyze
from app.modules.analysis.workspace import DraftRepository, empty_draft, invalidate
from app.modules.analysis.career_roles import (
    STAGES,
    preparation_for,
    reference_for,
    reference_text,
    resolve_role,
)
from app.modules.resumes.parsing.evidence import _sources

MAX_TEXT = 50_000


class PreparationConflict(ValueError):
    """The client must restart using the latest input, rather than retry stale work."""


def clean_text(value, label="입력") -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} 내용은 텍스트여야 합니다.")
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


class WorkspaceService:
    def __init__(self, repository: DraftRepository, examples: Path, matching_service=None):
        self.repository = repository
        self.examples = examples
        self.matching_service = matching_service

    @staticmethod
    def questions(draft: dict) -> list[dict]:
        if draft.get("analysis_mode") == "desired_role":
            preparation = preparation_for(draft)
            return (
                preparation.get("questions", []) if preparation and preparation["complete"] else []
            )
        if not all(draft.get(key) for key in ("resume_text", "role", "job_text")):
            return []
        return generate_questions(draft["resume_text"], draft["job_text"], draft["role"])

    def response(self, draft: dict, user_id: str | None = None) -> dict:
        # Derived catalog results stay current when jobs are added, changed or
        # removed, including reports saved before catalog matching existed.
        if (
            self.matching_service
            and user_id
            and draft.get("analysis_mode") != "desired_role"
            and isinstance(draft.get("report"), dict)
        ):
            draft["report"]["job_matches"] = self.matching_service.match(
                user_id, draft["resume_text"], draft.get("answers")
            )
        preparation = preparation_for(draft)
        if preparation is not None:
            previous = draft.get("preparation")
            if previous and previous.get("fingerprint") != preparation["fingerprint"]:
                invalidate(draft)
            draft["preparation"] = preparation
        if isinstance(draft.get("report"), dict):
            # Add a derived preview to older saved reports without writing the user's draft.
            draft["report"]["improvement_preview"] = improvement_preview(draft["report"])
        return {"draft": draft, "questions": self.questions(draft), "preparation": preparation}

    def workspace(self, user_id: str) -> dict:
        return self.response(self.repository.load(user_id), user_id)

    def save_resume(self, user_id: str, value) -> dict:
        text = clean_text(value, "이력서")
        if not 40 <= len(text) <= MAX_TEXT:
            raise ValueError("경력이나 프로젝트를 포함해 이력서를 40~50,000자로 입력해 주세요.")
        draft = self.repository.load(user_id)
        if draft["resume_text"] != text:
            invalidate(draft)
        draft["resume_text"] = text
        self.repository.save(user_id, draft)
        return self.response(draft, user_id)

    def upload_resume(self, user_id: str, filename: str, data: bytes) -> dict:
        text = extract_resume(filename, data)
        draft = self.repository.load(user_id)
        draft.update(resume_text=text, filename=Path(filename.replace("\\", "/")).name[:255])
        invalidate(draft)
        self.repository.save(user_id, draft)
        return self.response(draft, user_id)

    def save_job(
        self, user_id: str, company, role, job_text, *, posting_id=None, preserve_target=False
    ) -> dict:
        draft = self.repository.load(user_id)
        if not draft["resume_text"]:
            raise ValueError("이력서를 먼저 입력해 주세요.")
        updated = {
            "company": clean_text(company, "회사명"),
            "role": clean_text(role, "직무명"),
            "job_text": clean_text(job_text, "공고"),
        }
        if (
            not 1 <= len(updated["company"]) <= 120
            or not 1 <= len(updated["role"]) <= 120
            or not 40 <= len(updated["job_text"]) <= MAX_TEXT
        ):
            raise ValueError("회사명·직무명은 1~120자, 공고 본문은 40~50,000자로 입력해 주세요.")
        if (
            draft.get("analysis_mode") == "desired_role"
            or draft.get("selected_posting_id") != posting_id
            or any(draft[key] != value for key, value in updated.items())
        ):
            invalidate(draft)
        draft.update(
            updated,
            analysis_mode="job_posting",
            career_target=draft.get("career_target") if preserve_target else None,
            selected_posting_id=posting_id,
        )
        self.repository.save(user_id, draft)
        return self.response(draft, user_id)

    def save_career_target(self, user_id, role_id, role="", focus=""):
        draft = self.repository.load(user_id)
        if not draft["resume_text"]:
            raise ValueError("이력서를 먼저 입력해 주세요.")
        selected = resolve_role(role_id)
        role = clean_text(role, "직무명")
        focus = clean_text(focus, "관심 분야")
        label = role if role_id == "custom" else selected["label"]
        if not 1 <= len(label) <= 120 or len(focus) > 1000:
            raise ValueError("희망 직무는 1~120자, 관심 분야는 1,000자 이내로 입력해 주세요.")
        target = {
            "role_id": role_id,
            "label": label,
            "focus": focus,
            "reference_source": "internal_role_reference",
        }
        if draft.get("analysis_mode") != "desired_role" or draft.get("career_target") != target:
            invalidate(draft)
        draft.update(
            analysis_mode="desired_role",
            career_target=target,
            role=label,
            company="",
            job_text="",
            selected_posting_id=None,
        )
        self.repository.save(user_id, draft)
        return self.response(draft, user_id)

    def prepare(self, user_id, stage, expected_fingerprint=None):
        if not isinstance(stage, str) or stage not in STAGES:
            raise ValueError("분석 단계는 resume, role, report 중 하나여야 합니다.")
        draft = self.repository.load(user_id)
        expected = deepcopy(draft)
        preparation = preparation_for(draft)
        if not preparation or not draft["resume_text"]:
            raise ValueError("이력서와 희망 직무를 먼저 입력해 주세요.")
        if expected_fingerprint is not None and expected_fingerprint != preparation["fingerprint"]:
            raise PreparationConflict(
                "입력이 변경되었습니다. 최신 이력서와 희망 직무로 분석을 다시 시작해 주세요."
            )
        previous = draft.get("preparation")
        if previous and previous.get("fingerprint") != preparation["fingerprint"]:
            invalidate(draft)
        index = STAGES.index(stage)
        if any(item["status"] != "complete" for item in preparation["stages"][:index]):
            raise ValueError("앞선 분석 단계를 완료한 뒤 다시 시도해 주세요.")
        if preparation["stages"][index]["status"] == "complete":
            return self.response(draft, user_id)
        if stage == "resume":
            sources = _sources(draft["resume_text"], None)
            evidence = {
                "character_count": len(draft["resume_text"]),
                "statement_count": len(sources),
                "action_statement_count": sum(bool(item["action"]) for item in sources),
                "metric_statement_count": sum(bool(item["metric"]) for item in sources),
            }
            preparation["resume_evidence"] = evidence
            detail = f"이력서 {evidence['statement_count']}개 문장 · 수행 표현 {evidence['action_statement_count']}개 확인"
        elif stage == "role":
            reference = reference_for(draft["career_target"])
            preparation["role_reference"] = reference
            detail = f"{draft['role']} · 내부 참고 기준 {len(reference['criteria'])}개 확인"
        else:
            criteria = reference_text(preparation["role_reference"])
            report = analyze(
                draft["resume_text"],
                "",
                draft["role"],
                criteria,
                {},
                analysis_context="desired_role",
            )
            preparation["preliminary_report"] = report
            preparation["questions"] = generate_questions(
                draft["resume_text"], criteria, draft["role"], analysis_context="desired_role"
            )
            focus = draft["career_target"].get("focus", "")
            if focus:
                preparation["questions"] = preparation["questions"][:2] + [
                    {
                        "id": "focus",
                        "prompt": f"관심 분야 ‘{focus[:200]}’와 관련해 직접 수행한 경험과 본인이 맡은 일을 적어 주세요. 경험이 없다면 없다고 적어도 됩니다.",
                        "reason": "직접 입력한 관심 분야에 맞춘 보완 질문입니다. 실제 수행 경험만 작성해 주세요.",
                    }
                ]
            detail = f"세 가지 근거 점수 분석 · 보완 질문 {len(preparation['questions'])}개 준비"
        preparation["stages"][index].update(status="complete", detail=detail)
        preparation["complete"] = all(
            item["status"] == "complete" for item in preparation["stages"]
        )
        draft["preparation"] = preparation
        if not self.repository.save_if_unchanged(user_id, draft, expected):
            raise PreparationConflict(
                "분석 중 입력이 변경되었습니다. 최신 내용으로 다시 시작해 주세요."
            )
        return self.response(draft, user_id)

    def analyze(self, user_id: str, answers) -> dict:
        draft = self.repository.load(user_id)
        expected = deepcopy(draft)
        desired_role = draft.get("analysis_mode") == "desired_role"
        preparation = preparation_for(draft) if desired_role else None
        if desired_role and (not preparation or not preparation["complete"]):
            raise ValueError("이력서와 희망 직무의 분석을 먼저 완료해 주세요.")
        if not desired_role and not all(
            draft.get(key) for key in ("resume_text", "company", "role", "job_text")
        ):
            raise ValueError("이력서와 채용공고를 먼저 입력해 주세요.")
        if not isinstance(answers, dict):
            raise ValueError("보완 답변은 질문 ID와 답변을 연결한 객체여야 합니다.")
        questions = self.questions(draft)
        question_ids = {question["id"] for question in questions}
        if set(answers) - question_ids:
            raise ValueError(
                "현재 질문에 해당하는 답변만 제출해 주세요. 질문을 새로고침한 뒤 다시 시도해 주세요."
            )
        normalized = {
            question["id"]: clean_text(answers.get(question["id"], ""), "답변")
            for question in questions
        }
        if any(len(answer) > 8000 for answer in normalized.values()):
            raise ValueError("답변은 질문당 8,000자 이내로 입력해 주세요.")
        if desired_role:
            criteria = reference_text(preparation["role_reference"])
            report = analyze(
                draft["resume_text"],
                "",
                draft["role"],
                criteria,
                normalized,
                analysis_context="desired_role",
            )
        else:
            report = analyze(
                draft["resume_text"], draft["company"], draft["role"], draft["job_text"], normalized
            )
        if self.matching_service and not desired_role:
            report["job_matches"] = self.matching_service.match(
                user_id, draft["resume_text"], normalized
            )
        draft.update(
            answers=normalized,
            report=report,
            created_at=datetime.now(timezone(timedelta(hours=9))).strftime("%Y.%m.%d %H:%M"),
        )
        if desired_role:
            if not self.repository.save_if_unchanged(user_id, draft, expected):
                raise PreparationConflict(
                    "분석 중 입력이 변경되었습니다. 최신 내용으로 다시 시작해 주세요."
                )
        else:
            self.repository.save(user_id, draft)
        return {"report": report}

    def example(self, user_id: str) -> dict:
        draft = empty_draft()
        draft.update(
            resume_text=(self.examples / "resume.txt").read_text(encoding="utf-8"),
            job_text=(self.examples / "job.txt").read_text(encoding="utf-8"),
            company="샘플테크",
            role="주니어 Python 백엔드 개발자",
            filename="체험용 이력서",
        )
        self.repository.save(user_id, draft)
        return self.response(draft, user_id)

    def delete(self, user_id: str) -> dict:
        self.repository.delete(user_id)
        return self.response(empty_draft(), user_id)
