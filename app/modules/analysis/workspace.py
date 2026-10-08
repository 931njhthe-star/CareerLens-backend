"""User workspace state and storage contract, independent of HTTP and SQLite."""

from typing import Protocol


def empty_draft() -> dict:
    return {
        "resume_text": "",
        "filename": "",
        "company": "",
        "role": "",
        "job_text": "",
        "answers": {},
        "report": None,
        "created_at": None,
        "analysis_mode": "job_posting",
        "career_target": None,
        "selected_posting_id": None,
        "preparation": None,
    }


def invalidate(draft: dict) -> None:
    draft.update(answers={}, report=None, created_at=None, preparation=None)


class DraftRepository(Protocol):
    def load(self, user_id: str) -> dict: ...
    def save(self, user_id: str, draft: dict) -> None: ...
    def save_if_unchanged(self, user_id: str, draft: dict, expected: dict) -> bool: ...
    def delete(self, user_id: str) -> None: ...
