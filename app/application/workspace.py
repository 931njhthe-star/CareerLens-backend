"""Resume → job → optional evidence → practice application use cases."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.integrations.document_parsers.resume import extract_resume
from app.modules.analysis.reporting.service import analyze, generate_questions
from app.modules.analysis.workspace import DraftRepository, empty_draft, invalidate

MAX_TEXT = 50_000


def clean_text(value, label="입력") -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} 내용은 텍스트여야 합니다.")
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


class WorkspaceService:
    def __init__(self, repository: DraftRepository, examples: Path):
        self.repository = repository
        self.examples = examples

    @staticmethod
    def questions(draft: dict) -> list[dict]:
        if not all(draft.get(key) for key in ("resume_text", "role", "job_text")):
            return []
        return generate_questions(draft["resume_text"], draft["job_text"], draft["role"])

    def response(self, draft: dict) -> dict:
        return {"draft": draft, "questions": self.questions(draft)}

    def workspace(self, user_id: str) -> dict:
        return self.response(self.repository.load(user_id))

    def save_resume(self, user_id: str, value) -> dict:
        text = clean_text(value, "이력서")
        if not 40 <= len(text) <= MAX_TEXT:
            raise ValueError("경력이나 프로젝트를 포함해 이력서를 40~50,000자로 입력해 주세요.")
        draft = self.repository.load(user_id)
        if draft["resume_text"] != text:
            invalidate(draft)
        draft["resume_text"] = text
        self.repository.save(user_id, draft)
        return self.response(draft)

    def upload_resume(self, user_id: str, filename: str, data: bytes) -> dict:
        text = extract_resume(filename, data)
        draft = self.repository.load(user_id)
        draft.update(resume_text=text, filename=Path(filename.replace("\\", "/")).name[:255])
        invalidate(draft)
        self.repository.save(user_id, draft)
        return self.response(draft)

    def save_job(self, user_id: str, company, role, job_text) -> dict:
        draft = self.repository.load(user_id)
        if not draft["resume_text"]:
            raise ValueError("이력서를 먼저 입력해 주세요.")
        updated = {"company": clean_text(company, "회사명"), "role": clean_text(role, "직무명"), "job_text": clean_text(job_text, "공고")}
        if not 1 <= len(updated["company"]) <= 120 or not 1 <= len(updated["role"]) <= 120 or not 40 <= len(updated["job_text"]) <= MAX_TEXT:
            raise ValueError("회사명·직무명은 1~120자, 공고 본문은 40~50,000자로 입력해 주세요.")
        if any(draft[key] != value for key, value in updated.items()):
            invalidate(draft)
        draft.update(updated)
        self.repository.save(user_id, draft)
        return self.response(draft)

    def analyze(self, user_id: str, answers) -> dict:
        draft = self.repository.load(user_id)
        if not all(draft.get(key) for key in ("resume_text", "company", "role", "job_text")):
            raise ValueError("이력서와 채용공고를 먼저 입력해 주세요.")
        if not isinstance(answers, dict):
            raise ValueError("보완 답변은 질문 ID와 답변을 연결한 객체여야 합니다.")
        questions = self.questions(draft)
        question_ids = {question["id"] for question in questions}
        if set(answers) - question_ids:
            raise ValueError("현재 질문에 해당하는 답변만 제출해 주세요. 질문을 새로고침한 뒤 다시 시도해 주세요.")
        normalized = {question["id"]: clean_text(answers.get(question["id"], ""), "답변") for question in questions}
        if any(len(answer) > 8000 for answer in normalized.values()):
            raise ValueError("답변은 질문당 8,000자 이내로 입력해 주세요.")
        report = analyze(draft["resume_text"], draft["company"], draft["role"], draft["job_text"], normalized)
        draft.update(answers=normalized, report=report, created_at=datetime.now(timezone(timedelta(hours=9))).strftime("%Y.%m.%d %H:%M"))
        self.repository.save(user_id, draft)
        return {"report": report}

    def example(self, user_id: str) -> dict:
        draft = empty_draft()
        draft.update(
            resume_text=(self.examples / "resume.txt").read_text(encoding="utf-8"),
            job_text=(self.examples / "job.txt").read_text(encoding="utf-8"),
            company="샘플테크", role="주니어 Python 백엔드 개발자", filename="체험용 이력서",
        )
        self.repository.save(user_id, draft)
        return self.response(draft)

    def delete(self, user_id: str) -> dict:
        self.repository.delete(user_id)
        return self.response(empty_draft())
