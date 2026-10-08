"""Shared Korean/English term normalization; no I/O."""

from __future__ import annotations

import re


_CONCEPTS = {
    "Python": ("python", "파이썬"),
    "SQL": ("sql", "에스큐엘"),
    "PostgreSQL": ("postgresql", "postgres", "포스트그레SQL", "포스트그레스"),
    "Redis": ("redis", "레디스"),
    "Java": ("java", "자바"),
    "JavaScript": ("javascript", "자바스크립트"),
    "TypeScript": ("typescript", "타입스크립트"),
    "React": ("react", "리액트"),
    "Django": ("django", "장고"),
    "FastAPI": ("fastapi", "패스트에이피아이"),
    "Flask": ("flask", "플라스크"),
    "Spring": ("spring", "스프링"),
    "API": ("api", "rest api", "restful"),
    "AWS": ("aws", "아마존 웹 서비스"),
    "Docker": ("docker", "도커"),
    "Kubernetes": ("kubernetes", "k8s", "쿠버네티스"),
    "Git": ("git", "깃"),
    "Excel": ("excel", "엑셀"),
    "Figma": ("figma", "피그마"),
    "Tableau": ("tableau", "태블로"),
    "GA4": ("ga4", "google analytics", "구글 애널리틱스"),
    "데이터 분석": (
        "데이터 분석",
        "데이터분석",
        "data analysis",
        "data analytics",
        "데이터를 분석",
        "데이터 분석을",
    ),
    "실험": ("a/b", "ab test", "a/b testing", "실험 설계", "실험을 설계", "a·b"),
    "제품 지표": (
        "kpi",
        "product metrics",
        "제품 지표",
        "제품지표",
        "핵심 지표",
        "핵심지표",
        "전환율",
        "retention",
        "리텐션",
    ),
    "사용자 조사": (
        "user research",
        "사용자 조사",
        "고객 인터뷰",
        "사용자 인터뷰",
        "유저 리서치",
        "사용자 리서치",
    ),
    "온보딩": ("onboarding", "온보딩"),
    "로드맵": ("roadmap", "로드맵"),
    "요구사항": ("requirements", "요구사항", "요구 사항", "prd"),
    "협업": (
        "collaboration",
        "collaborated",
        "cross-functional",
        "협업",
        "협력",
        "부서 간",
        "유관부서",
        "유관 부서",
    ),
    "커뮤니케이션": ("communication", "communicated", "커뮤니케이션", "의사소통", "소통"),
    "프로젝트 관리": ("project management", "프로젝트 관리", "일정 관리", "일정관리"),
    "마케팅": ("marketing", "마케팅"),
    "콘텐츠": ("content", "콘텐츠", "컨텐츠"),
    "SEO": ("seo", "검색 엔진 최적화", "검색엔진 최적화"),
    "캠페인": ("campaign", "campaigns", "캠페인"),
    "광고": ("advertising", "ads", "광고"),
    "SNS": ("social media", "sns", "소셜 미디어", "인스타그램"),
    "영업": ("sales", "영업"),
    "고객 관리": ("crm", "고객 관리", "고객관리", "customer relationship"),
    "고객 응대": (
        "customer service",
        "customer support",
        "고객 응대",
        "고객응대",
        "고객 상담",
        "고객상담",
    ),
    "매출": ("revenue", "매출"),
    "재고 관리": ("inventory", "재고 관리", "재고관리", "재고를 관리"),
    "회계": ("accounting", "회계"),
    "정산": ("reconciliation", "정산"),
    "급여": ("payroll", "급여"),
    "채용": ("recruiting", "recruitment", "채용"),
    "문서 작성": ("documentation", "문서 작성", "문서작성", "보고서 작성", "보고서를 작성"),
    "디자인": ("design", "디자인"),
    "UX": ("ux", "사용자 경험", "user experience"),
    "UI": ("ui", "사용자 인터페이스", "user interface"),
    "품질 관리": ("quality assurance", "quality control", "qa", "품질 관리", "품질관리"),
    "테스트": ("testing", "tests", "테스트", "단위 테스트", "unittest"),
    "영어": ("english", "영어"),
    "일본어": ("japanese", "일본어"),
    "물류": ("logistics", "물류"),
    "안전 관리": ("safety", "안전 관리", "안전관리"),
    "조리": ("cooking", "조리", "요리"),
}


def _pattern(term: str) -> re.Pattern:
    left = r"(?<![a-zA-Z0-9])" if term[0].isascii() and term[0].isalnum() else ""
    right = r"(?![a-zA-Z0-9])" if term[-1].isascii() and term[-1].isalnum() else ""
    return re.compile(left + re.escape(term) + right, re.IGNORECASE)


_ALIASES = {name: tuple(_pattern(term) for term in aliases) for name, aliases in _CONCEPTS.items()}


_STOP = set(
    "a an the and or of to in on with for from by as at is are be have has will you your our we must required preferred experience skill skills ability knowledge work working strong good excellent relevant role responsibilities qualifications team years year more plus proficiency including use using 경력 경험 업무 담당 주요 자격 요건 자격요건 우대 사항 우대사항 필수 조건 기술 역량 능력 이해 활용 관련 통한 또는 및 위해 대한 있는 갖춘 가능 지원 수행 이상 년 년차 보유 요구 해당 함께 등 채용 모집 저희 회사 인재 근무 환경 필요 합니다 있습니다 입니다 하는 통한 바탕 기반 대상으로 실제".split()
)


_NEG_AFTER = re.compile(
    r"^(?:\s|은|는|을|를|에|의|관련|실무|개발|사용|활용|분석|경험|보유|능력|지식|도|가|이|과|와|만|아직|전혀|거의|직접|해본|해\s*본|해보지|해\s*보지|하지|한|배운|적|\w+지|이\s*){0,15}(?:없|부족|않|못|미경험|미보유|미사용)",
    re.IGNORECASE,
)


def _is_negative(text: str, start: int, end: int) -> bool:
    before, after = text[max(0, start - 60) : start], text[end : end + 120]
    # Context such as "AWS 환경에서 운영한 경험은 없습니다" belongs to the
    # mentioned technology, but another clause can contain positive experience.
    clause = re.split(
        r"[,;.!?。]|하지만|그러나|반면|반대로|대신|그리고|했으며|했고|하였고|해봤고|있고|이며|으나|지만",
        after,
        maxsplit=1,
    )[0]
    if re.search(
        r"(?:경험|(?:본|한|배운)\s*적)(?:이|은|는|도|을|를)?\s*(?:(?:전혀|거의|아직|별로|현재|실제로)\s*)?(?:없|부족|미보유)",
        clause,
    ):
        return True
    if _NEG_AFTER.search(after):
        return True
    if re.search(
        r"\b(?:no|without)\s+(?:(?:prior|professional|practical|hands.on)\s+)?(?:experience|knowledge|proficiency)\s+(?:in|with|of|using)?\s*$",
        before,
        re.I,
    ):
        return True
    if re.search(r"\bno\s*$", before, re.I):
        return True
    if re.search(
        r"\b(?:not|never|haven't|hasn't|didn't|don't|cannot)\s+(?!only\b)(?:(?:yet|ever|used|using|worked|work|with|in|learned|know|have|any|experience|experienced|of|familiar|proficient|knowledgeable)\s+){0,7}$",
        before,
        re.I,
    ):
        return True
    return bool(
        re.search(
            r"^\s*(?:experience\s*)?(?::\s*)?(?:none|not\s+(?:used|known)|없음|미경험)", after, re.I
        )
    )


def _concepts(text: str, positive_only: bool = False) -> set[str]:
    found = set()
    for name, patterns in _ALIASES.items():
        for pattern in patterns:
            if any(
                not positive_only or not _is_negative(text, m.start(), m.end())
                for m in pattern.finditer(text)
            ):
                found.add(name)
                break
    return found


def _tokens(text: str, positive_only: bool = False) -> set[str]:
    result = set()
    for match in re.finditer(r"[a-zA-Z][a-zA-Z0-9+#.-]*|[가-힣]{2,}", text.lower()):
        word = match.group(0)
        if positive_only and _is_negative(text, match.start(), match.end()):
            continue
        word = re.sub(r"(?:으로|에서|에게|부터|까지|을|를|은|는|이|가|와|과|의|에)$", "", word)
        if len(word) > 1 and word not in _STOP:
            result.add(word)
    return result


def _clauses(text: str) -> list[str]:
    # Preserve the actual submitted excerpt. Deduplicate only the comparison key.
    pieces = re.split(r"[\r\n]+|(?<=[.!?。])\s+|[;；]|\s+[•●▪]\s*", text)
    result, seen = [], set()
    for piece in pieces:
        piece = piece.strip(" \t•●▪-–")[:900]
        key = re.sub(r"\s+", " ", piece.casefold())
        if piece and key not in seen:
            result.append(piece)
            seen.add(key)
    return result
