"""Run the member analysis engine with an explicitly restricted guest response."""

from copy import deepcopy
from datetime import datetime, timezone

from app.application.workspace import WorkspaceService
from app.modules.analysis.workspace import empty_draft


class GuestError(ValueError):
    def __init__(self, message, code="guest_expired", status=410):
        super().__init__(message)
        self.code, self.status = code, status


class WorkingDraft:
    """A request-local snapshot; the real write uses the guest revision guard."""

    def __init__(self, draft):
        self.draft = deepcopy(draft)

    def load(self, _):
        return deepcopy(self.draft)

    def save(self, _, draft):
        self.draft = deepcopy(draft)

    def save_if_unchanged(self, key, draft, expected):
        if self.draft != expected:
            return False
        self.save(key, draft)
        return True


class GuestService:
    def __init__(self, repository, examples):
        self.repository, self.examples = repository, examples

    @staticmethod
    def response(record=None, *, expired=False):
        draft = record["draft"] if record else empty_draft()
        completed = isinstance(draft.get("report"), dict)
        # An allowlist is intentional: no resume, answers, preliminary analysis,
        # report or score may leave this boundary, including after completion.
        return {
            "draft": {
                "resume_attached": bool(draft.get("resume_text")),
                **{
                    key: draft.get(key)
                    for key in (
                        "filename", "company", "role", "analysis_mode",
                        "career_target", "selected_posting_id",
                    )
                },
            },
            "questions": WorkspaceService.questions(draft),
            "report_locked": completed,
            "completed": completed,
            "expired": expired,
            "expires_at": (
                datetime.fromtimestamp(record["expires_at"], timezone.utc).isoformat()
                if record else None
            ),
        }

    def workspace(self, guest_id):
        record = self.repository.load(guest_id) if guest_id else None
        return self.response(record, expired=bool(guest_id and record is None))

    def upload(self, guest_id, filename, data, *, create=False):
        if create:
            # Parse and validate before any temporary row is inserted. Binary
            # upload bytes live only for this request and are never persisted.
            work = WorkingDraft(empty_draft())
            WorkspaceService(work, self.examples).upload_resume(guest_id, filename, data)
            return self.response(self.repository.create(guest_id, work.draft))
        return self.mutate(guest_id, "upload_resume", filename, data)

    def mutate(self, guest_id, operation, *args, **kwargs):
        record = self.repository.load(guest_id) if guest_id else None
        if record is None:
            raise GuestError("비회원 임시 자료가 만료되었거나 삭제되었습니다. 이력서를 다시 첨부해 주세요.")
        work = WorkingDraft(record["draft"])
        workspace = WorkspaceService(work, self.examples)
        getattr(workspace, operation)(guest_id, *args, **kwargs)
        if not self.repository.replace(guest_id, work.draft, record["revision"]):
            if self.repository.load(guest_id) is None:
                raise GuestError("비회원 임시 자료가 만료되었거나 삭제되었습니다. 다시 시작해 주세요.")
            raise GuestError(
                "분석 중 입력이 변경되었습니다. 최신 내용으로 다시 시도해 주세요.",
                "guest_stale", 409,
            )
        return self.response({**record, "draft": work.draft})
