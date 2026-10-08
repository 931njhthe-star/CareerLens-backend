"""Per-request graph state. Raw application text is never written to trace logs."""

from typing import TypedDict


class AnalysisState(TypedDict, total=False):
    resume_text: str
    company: str
    role: str
    job_text: str
    analysis_context: str
    answers: dict[str, str]
    report: dict
    references: list[dict]
    candidate: dict | None
    coaching: dict | None
    steps: list[str]
    tools_called: list[str]
    error_codes: list[str]
    current_error: str
    retry_count: int
    fallback_used: bool
    prompt_version: str
    prompt_text: str
    settings: dict
    mode: str
