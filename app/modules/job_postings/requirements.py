"""Extract explicit job requirements and omit unrelated sections."""

from __future__ import annotations

import re
from app.modules.resumes.normalization.rules import _ALIASES, _clauses, _concepts, _tokens


_REQUIREMENT_SECTIONS = {
    "주요업무",
    "담당업무",
    "업무내용",
    "수행업무",
    "자격요건",
    "지원자격",
    "필수요건",
    "필수자격",
    "우대사항",
    "우대조건",
    "요구사항",
    "responsibilities",
    "keyresponsibilities",
    "requirements",
    "qualifications",
    "requiredqualifications",
    "preferredqualifications",
    "musthave",
    "nicetohave",
    "whatyou'lldo",
    "whatyoubring",
}


_OTHER_SECTIONS = {
    "회사소개",
    "기업소개",
    "팀소개",
    "복리후생",
    "혜택",
    "근무조건",
    "근무환경",
    "근무지",
    "근무시간",
    "급여",
    "채용절차",
    "전형절차",
    "지원방법",
    "접수방법",
    "접수기간",
    "마감",
    "기타안내",
    "benefits",
    "aboutus",
    "aboutcompany",
    "aboutthecompany",
    "howtoapply",
    "applicationprocess",
    "location",
    "compensation",
    "salary",
}


_DEMOGRAPHIC = re.compile(
    r"성별|남성|여성|남자|여자|남녀|연령|나이|생년|출생|종교|기독교|불교|천주교|국적|인종|민족|미혼|기혼|혼인|결혼|임신|장애인|장애\s*여부|\d{2}\s*대(?:\s|$)|만\s*\d{2}\s*세|\b(?:age|gender|sex|male|female|religion|religious|race|ethnicity|nationality|citizenship|marital|pregnancy|disability)\b",
    re.I,
)


def _section(line: str) -> tuple[str | None, str]:
    """Recognize explicit headings, including '# 자격 요건' and inline sections."""
    cleaned = re.sub(r"^[\s#*\[\]()\d.]+|[\s*\[\]]+$", "", line)
    parts = re.split(r"[:：]", cleaned, maxsplit=1)
    key = re.sub(r"\s+", "", parts[0]).casefold()
    kind = (
        "requirement"
        if key in _REQUIREMENT_SECTIONS
        else "other" if key in _OTHER_SECTIONS else None
    )
    return kind, parts[1].strip() if kind and len(parts) == 2 else ""


def _alternative_groups(line: str, terms: set[str]) -> list[set[str]]:
    groups = [{term} for term in sorted(terms)]
    spans = sorted(
        (match.start(), match.end(), name)
        for name in terms
        for pattern in _ALIASES[name]
        for match in pattern.finditer(line)
    )
    for left, right in zip(spans, spans[1:]):
        if left[2] != right[2] and re.fullmatch(
            r"\s*(?:또는|혹은|or)\s*", line[left[1] : right[0]], re.I
        ):
            left_group = next(group for group in groups if left[2] in group)
            right_group = next(group for group in groups if right[2] in group)
            if left_group is not right_group:
                left_group.update(right_group)
                groups.remove(right_group)
    return groups


def _requirements(job_text: str) -> list[dict]:
    requirements = []
    seen = set()
    lines = _clauses(job_text)
    sectioned = any(_section(line)[0] == "requirement" for line in lines)
    active = not sectioned
    for line in lines:
        section, inline = _section(line)
        if section:
            if section == "other" and inline and not sectioned:
                continue
            active = section == "requirement"
            if not active or not inline:
                continue
            line = inline
        if not active or _DEMOGRAPHIC.search(line):
            continue
        if re.search(
            r"^(?:본|이)\s*(?:공고|채용공고|채용 공고|문서)는|가상의?\s*채용\s*공고|프로그램\s*체험|^지원해\s*주|^많은\s*지원",
            line,
        ):
            continue
        if "|" in line or re.match(
            r"^(?:회사명|기업명|직무|모집\s*직무|포지션|채용\s*공고|company|job\s*title)\s*[:：]",
            line,
            re.I,
        ):
            continue
        concepts, tokens = _concepts(line), _tokens(line)
        terms = concepts if concepts else tokens
        groups = (
            _alternative_groups(line, terms) if concepts else [{term} for term in sorted(terms)]
        )
        key = tuple(sorted(tuple(sorted(group)) for group in groups))
        if not terms or key in seen:
            continue
        requirements.append(
            {
                "text": line,
                "terms": terms,
                "groups": groups,
                "kind": "concept" if concepts else "token",
            }
        )
        seen.add(key)
    return requirements[:12]
