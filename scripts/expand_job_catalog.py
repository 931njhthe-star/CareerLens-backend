"""Build 600 detailed fictional postings without opening a database.

Run with the project's Python interpreter. The original 60 IDs, metadata and
authored requirement briefs are preserved. Regeneration produces identical
JSON. Only the three bundled job fixture files and their manifest are written.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from itertools import combinations
from pathlib import Path

from job_catalog_briefs import SECTORS, Sector


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "data" / "examples"
NOTICE = (
    "교육용 가상 채용공고입니다. 회사·사업·채용 조건·급여는 모두 허구이며 실제 모집이나 지원 접수가 아닙니다. "
    "공개 구인 사이트의 정보 구성만 참고해 독립적으로 작성했습니다."
)
LOCATIONS = (
    "서울",
    "경기 성남",
    "인천",
    "대전",
    "부산",
    "대구",
    "광주",
    "울산",
    "세종",
    "제주",
    "강원 춘천",
    "충북 청주",
    "충남 천안",
    "전북 전주",
    "전남 순천",
    "경북 포항",
    "경남 창원",
    "경기 수원",
    "경기 고양",
    "강원 원주",
    "경기 부천",
    "충북 충주",
    "전남 여수",
    "경남 진주",
)
COMPANY_PREFIXES = (
    "온새미",
    "다솜결",
    "별오름",
    "해솔길",
    "여울빛",
    "새나루",
    "마루온",
    "도담숲",
    "누리담",
    "한결봄",
)
COMPANY_SUFFIXES = (
    "솔루션",
    "리서치",
    "랩",
    "서비스",
    "파트너스",
    "운영사",
    "컴퍼니",
    "스튜디오",
    "프로젝트",
    "네트워크",
)
PAIRS = tuple(combinations(range(6), 2))[:10]
STYLES = ("saramin", "albamon", "daangn")
LAYOUT_REFERENCES = {
    "saramin": "https://www2.saramin.co.kr/zf_user/help/help-word/main?inquiryCode=1639&memberCode=1638",
    "albamon": "https://m.albamon.com/service-center/guide",
    "daangn": "https://jobs.daangn.com/s?jobTask=MANUFACTURING&regionId=4588",
    "work24": "https://m.work24.go.kr/wk/a/b/1500/empDetailAuthView.do?infoTypeCd=VALIDATION&infoTypeGroup=tb_workinfoworknet&wantedAuthNo=KF10122609040018",
}
REQUIREMENT_HEADINGS = {
    "주요업무",
    "담당업무",
    "업무내용",
    "자격요건",
    "지원자격",
    "우대사항",
    "우대조건",
}
OTHER_HEADINGS = {
    "회사소개",
    "기업소개",
    "팀소개",
    "근무조건",
    "전형절차",
    "지원방법",
    "접수방법",
    "복리후생",
}


def read_json(filename: str):
    return json.loads((EXAMPLES / filename).read_text(encoding="utf-8"))


def write_json(filename: str, value) -> None:
    (EXAMPLES / filename).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def join_particle(word: str) -> str:
    last = ord(word[-1])
    has_final = 0xAC00 <= last <= 0xD7A3 and (last - 0xAC00) % 28 != 0
    return word + ("과" if has_final else "와")


def baseline_requirements(posting: dict) -> list[str]:
    if posting.get("catalog_original_requirements"):
        return posting["catalog_original_requirements"]
    result = []
    active = False
    for line in posting["description"].splitlines():
        clean = line.strip()
        if clean in REQUIREMENT_HEADINGS:
            active = True
        elif clean in OTHER_HEADINGS:
            active = False
        elif active and clean.startswith(("-", "•")):
            result.append(clean.lstrip("-• "))
    if not result:
        raise ValueError(f"Missing authored requirement brief: {posting['id']}")
    return list(dict.fromkeys(result))


def employment(index: int, sector: Sector) -> str:
    if sector.key in {"retail", "food", "hospitality", "health", "education"} and index % 5 == 2:
        return "파트타임"
    return "계약직" if index % 5 == 3 else "정규직"


def terms(posting: dict, sector: Sector, variant: int) -> tuple[str, str]:
    if posting["employment_type"] == "파트타임":
        hourly = 14000 + (variant % 5) * 1000 + (2000 if sector.key == "health" else 0)
        return (
            "주 3일 10:00~15:00, 휴게 12:00~13:00; 가능한 요일은 면담에서 조율합니다.",
            f"시급 {hourly:,}~{hourly + 3000:,}원(세전 가상 범위). 주당 예정 시간과 별도 지급 항목을 제안서에 구분합니다.",
        )
    low, high = sector.pay
    increment = (variant % 4) * 150
    return (
        sector.schedule + "; 고정 일정과 변경 가능한 일정을 면담에서 구분해 안내합니다.",
        f"연봉 {low + increment:,}~{high + increment:,}만원(세전 가상 범위). 기본급과 별도 수당·성과 보상은 조건 협의 시 구분합니다.",
    )


def description(
    posting: dict,
    sector: Sector,
    variant: int,
    duties: list[str],
    requirements: list[str],
    preferred: list[str],
) -> str:
    pair = PAIRS[variant % len(PAIRS)]
    focus = sector.situations[pair[0]][0]
    second = sector.situations[pair[1]][0]
    style = posting["format_style"]
    duty_heading = {"saramin": "주요업무", "albamon": "담당업무", "daangn": "업무내용"}[style]
    intro_heading = {"saramin": "회사소개", "albamon": "기업소개", "daangn": "팀소개"}[style]
    bullet = "• " if style == "albamon" else "- "
    schedule, pay = terms(posting, sector, variant)
    contract = (
        "계약기간은 12개월이며 담당 범위와 종료 시점은 계약 안내에서 확인합니다."
        if posting["employment_type"] == "계약직"
        else "담당 범위와 교육 일정은 입사 안내에서 확인하고 초기 적응 기간에 함께 점검합니다."
    )
    documents = (
        "이력서와 대표 업무 사례 1~2건을 준비하는 상황을 가정합니다. 경력이 짧다면 교육·실습 자료로 본인 역할을 설명할 수 있습니다. "
        "자격이 필요한 직무는 해당 자격 확인 자료를 함께 검토하며 사진·주민등록번호·가족 정보는 요청하지 않습니다."
    )
    benefits = (
        "업무에 필요한 장비와 작업 자료를 제공하고 입사 초기에 담당 동료가 절차를 안내합니다. "
        "직무 학습비와 식사 지원을 운영하는 설정이며 세부 한도와 사용 방식은 면담에서 안내합니다."
    )
    if sector.key in {"food", "retail", "manufacturing", "engineering", "logistics", "health"}:
        benefits = (
            "근무에 필요한 유니폼·작업 도구·보호구를 직무에 맞게 제공하고 휴게 공간을 마련하는 설정입니다. "
            "신규 근무자에게 현장 교육과 동료 동행 기간을 제공하며 식사 지원과 교대 일정은 사전에 안내합니다."
        )
    process = (
        "서류 검토 → 직무 경험 면담 → 조건 협의 순서의 가상 전형입니다. "
        "면담에서는 실제로 맡은 범위와 문제를 해결한 과정을 확인하며, 사전 과제가 있으면 예상 시간과 활용 범위를 먼저 안내합니다."
    )
    if style == "daangn":
        process = (
            "업무 가능 범위와 일정을 확인한 뒤 짧은 경험 면담을 진행하는 가상 전형입니다. "
            "하루 업무를 어떻게 나누는지 함께 설명하고, 체험·실습을 제안할 경우 시간과 보상 조건을 먼저 확인하는 설정입니다."
        )
    sections = [
        f"{intro_heading}\n{NOTICE}\n{sector.context}\n"
        f"이번 채용은 {sector.team}에서 {join_particle(focus)} {second} 업무를 보강하기 위한 설정입니다. "
        "개별 담당자의 판단 범위와 검토가 필요한 항목을 구분하고 주간 진행 내용을 함께 확인합니다.",
        duty_heading + "\n" + "\n".join(bullet + text for text in duties),
        "자격요건\n" + "\n".join(bullet + text for text in requirements),
        "우대사항\n" + "\n".join(bullet + text for text in preferred),
        f"근무조건\n근무지: {posting['location']}의 가상 사업장. 실제 사무실 주소와 연락처는 제공하지 않습니다.\n"
        f"고용형태: {posting['employment_type']} / 경력: {posting['experience_level']}. {contract}\n근무일정: {schedule}",
        "급여\n" + pay,
        "복리후생\n" + benefits,
        "전형절차\n" + process,
        "지원방법\n"
        + documents
        + "\n이 문서는 서비스의 연습·검증용 자료로 실제 지원서 접수나 연락을 받지 않습니다.",
    ]
    return "\n\n".join(sections)


def new_postings() -> list[dict]:
    postings = []
    for sector_number, sector in enumerate(SECTORS):
        for role_number, role in enumerate(sector.roles):
            for variant, pair in enumerate(PAIRS):
                posting = {
                    "id": f"expanded-{sector.key}-{role_number + 1:02d}-{variant + 1:02d}",
                    "company": f"가상 {COMPANY_PREFIXES[variant]}{sector.label.split('·')[0].replace(' ', '')}{COMPANY_SUFFIXES[role_number + variant % 7]}",
                    "role": role.title + " · " + sector.situations[pair[0]][0],
                    "location": LOCATIONS[
                        (sector_number * 7 + role_number * 3 + variant) % len(LOCATIONS)
                    ],
                    "employment_type": employment(variant, sector),
                    "experience_level": (
                        "신입",
                        "경력 1년 이상",
                        "경력 무관",
                        "경력 3년 이상",
                        "신입·경력",
                    )[variant % 5],
                    "skills": list(role.skills),
                    "source_url": LAYOUT_REFERENCES[STYLES[variant % 3]],
                    "created_at": f"2026-10-{1 + variant % 5:02d}T00:00:00+00:00",
                    "format_style": STYLES[variant % 3],
                    "synthetic": True,
                    "catalog_group": "expanded-600-v1",
                    "sector": sector.key,
                    "sector_label": sector.label,
                    "role_archetype": role.title,
                    "scenario": [sector.situations[index][0] for index in pair],
                }
                # Rotate the core sequence and add two distinct operational
                # problems. The variant changes actual work, not just names.
                offset = variant % len(role.duties)
                core = list(role.duties[offset:] + role.duties[:offset])
                duties = core + [sector.situations[index][1] for index in pair]
                posting["description"] = description(
                    posting, sector, variant, duties, list(role.requirements), [role.preferred]
                )
                postings.append(posting)
    return postings


def sector_for(posting: dict) -> Sector:
    identifier = posting["id"]
    if identifier.startswith("orchestration-"):
        return next(sector for sector in SECTORS if sector.key == "ai")
    mapping = (
        (("data", "search", "vector"), "data"),
        (("ai", "agent", "voice"), "ai"),
        (("cloud", "devops", "reliability", "qa"), "cloud"),
        (("design", "ux", "product-owner", "recommendation-po"), "design"),
        (("android",), "embedded"),
    )
    key = next(
        (key for terms_, key in mapping if any(term in identifier for term in terms_)), "software"
    )
    return next(sector for sector in SECTORS if sector.key == key)


def enrich_original(posting: dict, index: int) -> dict:
    sector = sector_for(posting)
    original = baseline_requirements(posting)
    pair = PAIRS[index % len(PAIRS)]
    result = {
        **posting,
        "catalog_original_requirements": original,
        "catalog_group": "expanded-600-v1",
        "sector": sector.key,
        "sector_label": sector.label,
        "role_archetype": posting["role"],
        "scenario": [sector.situations[number][0] for number in pair],
        "format_style": posting.get("format_style", STYLES[index % 3]),
        "synthetic": True,
    }
    endings = (
        " 업무를 맡아 입력 자료와 처리 결과를 비교하고 오류 발생 시 재현 조건을 남깁니다.",
        " 업무를 수행하고 작업 단계의 변경 사유와 검토 결과를 동료가 확인할 수 있게 기록합니다.",
        " 업무를 진행하며 정상·예외 상황을 나누고 현장 담당자와 완료 기준을 확인합니다.",
    )
    duties = [
        text.rstrip(".").removesuffix("경험").strip() + endings[number % 3]
        for number, text in enumerate(original[:3])
    ]
    duties.extend(sector.situations[number][1] for number in pair)
    requirements = [
        text.rstrip(".") + " 관련 본인 역할과 수행 결과를 구체적으로 설명할 수 있어야 합니다."
        for text in original[3:5]
    ]
    if not requirements:
        requirements = [
            f"{posting['skills'][0]} 관련 구현·운영·실습 자료에서 본인이 직접 맡은 범위와 확인한 결과를 설명할 수 있어야 합니다.",
        ]
    preferred = [
        f"{posting['skills'][-1]} 관련 작업을 검토하거나 반복되는 오류의 원인을 정리한 경험을 우대합니다.",
    ]
    result["description"] = description(result, sector, index, duties, requirements, preferred)
    return result


def main() -> None:
    original = [
        enrich_original(posting, index)
        for index, posting in enumerate(read_json("job_postings.json"))
    ]
    orchestration = [
        enrich_original(posting, index + 30)
        for index, posting in enumerate(read_json("orchestration_job_postings.json"))
    ]
    expanded = new_postings()
    all_postings = original + orchestration + expanded
    if (
        len(SECTORS) != 18
        or len(all_postings) != 600
        or len({item["id"] for item in all_postings}) != 600
    ):
        raise ValueError("Expected 18 sectors and exactly 600 unique posting IDs")
    lengths = [len(item["description"]) for item in all_postings]
    if not all(900 <= length <= 1800 for length in lengths):
        raise ValueError(f"Unexpected description length: {min(lengths)}–{max(lengths)}")
    write_json("job_postings.json", original)
    write_json("orchestration_job_postings.json", orchestration)
    write_json("expanded_job_postings.json", expanded)
    manifest = {
        "version": "expanded-600-v1",
        "synthetic": True,
        "total": len(all_postings),
        "preserved_ids": [item["id"] for item in original + orchestration],
        "added": len(expanded),
        "sector_counts": dict(Counter(item["sector"] for item in all_postings)),
        "occupation_archetypes": len({item["role_archetype"] for item in all_postings}),
        "unique_descriptions": len({item["description"] for item in all_postings}),
        "description_characters": {
            "min": min(lengths),
            "max": max(lengths),
            "mean": round(sum(lengths) / len(lengths)),
        },
        "layout_references": LAYOUT_REFERENCES,
        "notice": "문장과 회사는 독립적으로 작성한 허구입니다. 참고 URL의 실제 기업·임금·채용 상태를 복제하지 않았습니다.",
        "files": {
            filename: hashlib.sha256((EXAMPLES / filename).read_bytes()).hexdigest()
            for filename in (
                "job_postings.json",
                "orchestration_job_postings.json",
                "expanded_job_postings.json",
            )
        },
    }
    write_json("expanded_jobs_manifest.json", manifest)
    print(
        json.dumps(
            {
                key: manifest[key]
                for key in (
                    "total",
                    "added",
                    "sector_counts",
                    "description_characters",
                    "unique_descriptions",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
