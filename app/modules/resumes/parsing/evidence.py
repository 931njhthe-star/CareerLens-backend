"""Evidence keeps submitted excerpts and original source labels."""
from __future__ import annotations

import re
from collections.abc import Mapping
from app.modules.resumes.normalization.rules import _clauses, _concepts, _tokens


_ACTION = re.compile(
    r"개발|구현|구축|설계|운영|분석|개선|기획|주도|담당|작성|제작|수행|협업|관리|진행|처리|응대|달성|감소|증가|향상|사용|활용|배포|검증|판매|조리|매출|교육|상담|정산|작성|집행|보유|경력|경험|인턴|재직|근무|\b(?:built|developed|implemented|designed|managed|led|improved|analyzed|analysed|created|delivered|launched|reduced|increased|achieved|maintained|worked|used|collaborated|handled|conducted|experience|years)\b",
    re.IGNORECASE,
)


_NUMBER = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|퍼센트|배|건|명|개|시간|분|초|원|만원|억원|천|만|million|thousand|users|customers|projects|hours|seconds)\b|\d+(?:[.,]\d+)?\s*%", re.IGNORECASE)


def _sources(resume_text: str, answers: Mapping | None) -> list[dict]:
    sources = [{"text": text, "source": "resume", "source_label": "이력서"} for text in _clauses(resume_text)]
    if answers:
        for key, answer in answers.items():
            if isinstance(answer, str):
                number = re.fullmatch(r"evidence_(\d+)", str(key))
                label = f"보완 답변 {number.group(1)}" if number else {"ownership": "본인 기여 답변", "outcome": "결과·규모 답변"}.get(str(key), "보완 답변")
                sources.extend({"text": text, "source": "answer", "source_label": label} for text in _clauses(answer))
    for source in sources:
        source["concepts"] = _concepts(source["text"], True)
        source["tokens"] = _tokens(source["text"], True)
        source["action"] = bool(_ACTION.search(source["text"]))
        source["metric"] = bool(_NUMBER.search(source["text"]))
    return sources
