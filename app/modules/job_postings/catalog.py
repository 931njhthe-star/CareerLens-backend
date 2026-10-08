"""Validation for the educational job catalog, independent of HTTP/storage."""

from urllib.parse import urlsplit
import json
from pathlib import Path

from app.modules.analysis.career_roles import resolve_role


def text(value, label, minimum=1, maximum=80):
    if not isinstance(value, str):
        raise ValueError(f"{label}은(는) 문자열로 입력해 주세요.")
    value = value.replace("\r\n", "\n").strip()
    if not minimum <= len(value) <= maximum or "\x00" in value:
        raise ValueError(f"{label}은(는) {minimum}~{maximum}자로 입력해 주세요.")
    return value


def validate_posting(payload):
    if not isinstance(payload, dict):
        raise ValueError("공고는 JSON 객체로 입력해 주세요.")
    result = {
        "company": text(payload.get("company"), "회사명", maximum=120),
        "role": text(payload.get("role"), "직무명", maximum=120),
        "location": text(payload.get("location"), "근무 지역"),
        "employment_type": text(payload.get("employment_type"), "고용 형태"),
        "experience_level": text(payload.get("experience_level"), "경력 조건"),
        "description": text(payload.get("description"), "공고 내용", minimum=40, maximum=50_000),
    }
    skills = payload.get("skills", [])
    if not isinstance(skills, list) or len(skills) > 20:
        raise ValueError("기술은 최대 20개 문자열 목록으로 입력해 주세요.")
    result["skills"] = []
    seen = set()
    for value in skills:
        skill = text(value, "기술명", maximum=50)
        if skill.casefold() not in seen:
            seen.add(skill.casefold())
            result["skills"].append(skill)
    source_url = text(payload.get("source_url", ""), "출처 URL", minimum=0, maximum=2000)
    if source_url:
        try:
            parsed = urlsplit(source_url)
            valid = (
                parsed.scheme in ("http", "https")
                and parsed.hostname
                and not parsed.username
                and not parsed.password
                and parsed.port != 0
                and not any(character.isspace() or ord(character) < 32 for character in source_url)
                and "\\" not in source_url
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("출처 URL은 계정 정보가 없는 http 또는 https 주소로 입력해 주세요.")
    result["source_url"] = source_url
    return result


def validate_filters(query):
    result = {}
    result["role_terms"] = []
    if query.get("role_id"):
        selected = resolve_role(query["role_id"])
        if selected["id"] == "custom":
            result["role_terms"] = [text(query.get("role", ""), "희망 직무", maximum=120)]
        else:
            path = Path(__file__).resolve().parents[3] / "data/knowledge/job-role-queries.json"
            result["role_terms"] = json.loads(path.read_text(encoding="utf-8"))[selected["id"]]
    for name in ("q", "location", "employment_type", "experience_level", "skill"):
        result[name] = text(
            query.get(name, ""), "검색 조건", minimum=0, maximum=200 if name == "q" else 80
        )
    for name, default, maximum in (("page", 1, 1_000_000), ("page_size", 12, 50)):
        value = query.get(name, str(default))
        if (
            not isinstance(value, str)
            or not value.isascii()
            or not value.isdigit()
            or len(value) > 7
        ):
            raise ValueError(f"{name}는 1~{maximum}의 정수여야 합니다.")
        result[name] = int(value)
        if not 1 <= result[name] <= maximum:
            raise ValueError(f"{name}는 1~{maximum}의 정수여야 합니다.")
    if query.get("saved", "0") not in ("0", "1"):
        raise ValueError("saved는 0 또는 1이어야 합니다.")
    result["saved"] = query.get("saved", "0") == "1"
    return result
