"""Domain input validation."""

from __future__ import annotations


def _validate(resume_text: str, job_text: str, role: str) -> None:
    for value, label in ((resume_text, "이력서"), (job_text, "채용공고"), (role, "지원 직무")):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} 내용을 입력해 주세요.")
    if len(resume_text) > 100_000 or len(job_text) > 50_000:
        raise ValueError("이력서는 100,000자, 채용공고는 50,000자 이내로 입력해 주세요.")
