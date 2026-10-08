"""Generate substantial, versioned fictional resumes without editing job data.

The 220 catalog IDs and the first ten desktop IDs are stable. Existing desktop
folders and live databases are never modified by this generator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from generate_matching_fixtures import (
    AI_PROFILES,
    CAREER_FAMILIES,
    LOCATIONS,
    NOTICE,
    SOURCES,
    build_desktop_resumes,
    build_resumes,
    write_json,
)
from resume_narrative_catalog import (
    CAREER_CONTEXTS,
    FAMILY_KEYS,
    ORIGINAL_KEYS,
    SKILL_SCOPES,
    WORK_SCENARIOS,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "data" / "examples"
PACK_NAME = "career-resumes-v2"
PACK_VERSION = 2

# New profiles deliberately include partial specialists and junior candidates.
# Their work evidence does not claim every technology required by the catalog.
AI_VARIANTS = [
    (
        "학습자료 RAG 평가",
        "ai",
        2,
        ["Python", "RAG", "평가", "Git"],
        [
            "Python으로 학습 자료 1,200건을 정리하고 RAG 답변 평가를 수행했습니다. 학습자가 되묻는 질문 140개를 유형별로 나눴습니다.",
            "AI 오케스트레이션 작업 흐름을 구현해 검색 결과가 없는 질문을 튜터 검토로 보냈습니다. 잘못된 인용 사례를 29건에서 11건으로 줄였습니다.",
            "Git으로 평가 기준을 관리하고 자료 버전에 따라 정답이 달라지는 사례를 따로 표시했습니다.",
        ],
        "상용 서비스 배포는 직접 담당하지 않았으며 학습 자료 평가와 실행 단계 연결을 맡았습니다.",
    ),
    (
        "계약 검토 승인흐름",
        "ai",
        5,
        ["Python", "LangGraph", "RAG", "평가"],
        [
            "LangGraph로 계약 검토 상태를 구현하고 RAG로 관련 조항을 검색했습니다. 합성 계약서 340건을 사용해 실험했습니다.",
            "Python으로 인용 근거를 검증하고 AI 오케스트레이션 작업 흐름의 승인 대기 상태를 구현했습니다.",
            "답변 정확도 평가에서 근거가 불충분한 67개 문장을 검토 대상으로 분리했습니다. 최종 법률 판단을 자동화하지 않았습니다.",
        ],
        "변호사 자격이나 실제 법률 자문 경력은 없으며 문서 처리 도구를 개발한 가상 사례입니다.",
    ),
    (
        "물류 알림 자동화",
        "logistics",
        4,
        ["Python", "SQL", "물류", "n8n"],
        [
            "Python으로 출고 데이터를 가공하고 SQL로 재고를 집계했습니다. 합성 출고 내역 8,500건의 누락을 확인했습니다.",
            "n8n으로 물류 작업 흐름을 연결하고 AI 오케스트레이션 운영 기록을 남겼습니다. 담당자 알림의 중복 비율을 12%에서 4%로 줄였습니다.",
            "재고 관리 오류 알림을 운영하고 출고 담당자가 조치한 결과를 다음 집계에 반영했습니다.",
        ],
        "창고 장비의 제어와 클라우드 인프라는 다른 담당자의 범위였습니다.",
    ),
    (
        "보안 이벤트 분류",
        "security",
        4,
        ["Python", "보안", "Redis", "Docker"],
        [
            "Python으로 보안 이벤트를 분류하고 Redis 작업 대기열을 구현했습니다. 교육용 로그 25,000건을 처리했습니다.",
            "Docker 분석 서비스를 배포하고 AI 오케스트레이션 작업 흐름에서 중복된 경고를 묶었습니다.",
            "보안 사고 대응 절차를 문서화하고 검토가 필요한 이벤트를 담당자에게 전달했습니다. 합성 경고의 재처리 시간을 42분에서 26분으로 줄였습니다.",
        ],
        "공격 수행이나 실제 보안 관제 대응 권한은 없었으며 허가된 교육 환경에서만 확인했습니다.",
    ),
    (
        "여행상담 노코드 운영",
        "support",
        2,
        ["n8n", "API", "영어", "고객 응대"],
        [
            "API로 예약 정보를 연결하고 n8n으로 여행 일정 알림을 구현했습니다. 합성 예약 520건을 검증했습니다.",
            "영어 고객 응대 기록을 정리하고 여행 요청 분류 테스트를 작성했습니다. 수동 확인이 필요한 질문을 먼저 표시했습니다.",
            "AI 오케스트레이션 작업 흐름을 운영해 일정 변경과 담당자 확인을 연결했습니다. 같은 요청의 중복 안내를 17건에서 6건으로 줄였습니다.",
        ],
        "직접 작성한 서버 프로그램은 없으며 설정, 사례 검증과 상담 이관을 맡았습니다.",
    ),
    (
        "환경정보 보고서 자동화",
        "analysis",
        3,
        ["Python", "SQL", "Tableau", "데이터 분석"],
        [
            "Python으로 환경 데이터를 분석하고 SQL로 관측 자료를 검증했습니다. 합성 관측값 48,000건에서 누락 구간을 분리했습니다.",
            "Tableau 대시보드를 개발하고 이상 수치 알림을 구현했습니다. 확인 대상 92건 중 센서 오류 21건을 별도로 표시했습니다.",
            "AI 오케스트레이션 작업 흐름을 구현해 집계, 설명 초안, 담당자 검토를 연결했습니다. 보고서 준비 시간을 90분에서 55분으로 줄였습니다.",
        ],
        "센서 펌웨어나 모델 학습은 담당하지 않았습니다.",
    ),
    (
        "회계증빙 OCR 운영",
        "finance",
        6,
        ["Excel", "회계", "OCR", "Python"],
        [
            "Excel로 회계 증빙을 정리하고 OCR로 전표 데이터를 추출했습니다. 합성 증빙 1,450건을 대조했습니다.",
            "Python 정산 검증을 구현하고 AI 오케스트레이션 작업 흐름에서 금액이 다른 항목을 검토자에게 보냈습니다.",
            "회계 오류 알림을 구현해 중복 증빙 44건을 확인했습니다. 검토 순서를 조정해 월말 확인 시간을 8시간에서 5시간으로 줄였습니다.",
        ],
        "세무 판단과 결산 승인은 책임자의 범위이며 자동화 결과를 최종 판단으로 사용하지 않았습니다.",
    ),
    (
        "제품추천 실험",
        "analysis",
        3,
        ["Python", "SQL", "추천", "실험"],
        [
            "Python으로 상품 추천 파이프라인을 개발하고 SQL로 상품 데이터를 분석했습니다. 합성 상품 3,800개를 사용했습니다.",
            "A/B 실험을 설계하고 추천 결과를 평가했습니다. 표본 260건에서 관련 없는 추천의 비율을 23%에서 15%로 줄였습니다.",
            "AI 오케스트레이션 작업 흐름을 구현해 추천 이유를 검토하고 누락된 상품 정보를 보완 요청으로 돌렸습니다.",
        ],
        "실제 매출 상승을 검증한 경력은 아니며 합성 데이터 실험 결과만 제시합니다.",
    ),
    (
        "돌봄일정 자동화 보조",
        "education",
        1,
        ["Excel", "n8n", "문서화", "고객 응대"],
        [
            "Excel로 방문 일정을 정리하고 n8n으로 담당자 알림을 연결했습니다. 합성 일정 180건을 확인했습니다.",
            "고객 응대 기록을 분류하고 업무 절차를 문서화했습니다. 변경된 일정의 미확인 건수를 22건에서 9건으로 줄였습니다.",
            "AI 오케스트레이션 작업 흐름을 운영하면서 자동 처리가 어려운 요청은 사람이 확인하도록 전달했습니다.",
        ],
        "의료 및 돌봄 전문 판단을 수행하지 않았으며 일정과 안내 업무에만 참여했습니다.",
    ),
    (
        "배차 요청 상태관리",
        "backend",
        5,
        ["Python", "API", "Redis", "Docker"],
        [
            "Python 배차 API를 개발하고 Redis 작업 상태를 구현했습니다. 합성 요청 12,000건에서 상태 전이를 확인했습니다.",
            "Docker 서비스를 배포하고 요청 실패 재시도 테스트를 작성했습니다. 중복 요청 36건을 재현해 재발하지 않는지 확인했습니다.",
            "AI 오케스트레이션 작업 흐름을 구현해 요청 분류와 담당자 검토 단계를 연결했습니다. 실패 복구 시간을 18분에서 7분으로 줄였습니다.",
        ],
        "실차 배차의 안전성과 경로 최적화는 이 프로젝트에서 검증하지 않았습니다.",
    ),
    (
        "AI 평가 데이터 인턴",
        "qa",
        0,
        ["Python", "평가", "Git"],
        [
            "Python으로 평가 데이터의 빈 항목을 검증했습니다. 교육 프로젝트의 질문 80개를 확인했습니다.",
            "AI 오케스트레이션 작업 흐름의 실행 결과를 분류하고 Git으로 수정 내역을 남겼습니다.",
            "실패 사례 14개를 재현해 입력 누락과 응답 형식 오류를 구분했습니다. 상용 환경의 성과는 측정하지 않았습니다.",
        ],
        "서비스 운영 경험은 없습니다. 교육 프로젝트에서 작은 평가 도구를 작성한 신입 사례입니다.",
    ),
    (
        "AI 문서 검수 계약직",
        "content",
        1,
        ["OCR", "문서화", "Excel"],
        [
            "OCR 결과와 합성 원본 문서 240건을 대조하고 날짜와 금액의 오인식 사례를 분류했습니다.",
            "Excel로 검토 결과를 정리하고 AI 오케스트레이션 운영자가 확인할 실패 사례를 문서화했습니다.",
            "검토 기준의 해석이 달랐던 19개 사례를 모아 책임자와 기준을 맞췄습니다. 확인되지 않은 항목은 정답으로 수정하지 않았습니다.",
        ],
        "자동화 프로그램 개발은 담당하지 않았습니다. 문서 검토와 결과 기록에 참여했습니다.",
    ),
    (
        "AI 상담화면 주니어",
        "frontend",
        1,
        ["TypeScript", "React", "API"],
        [
            "TypeScript와 React로 상담 상태 화면을 개발하고 API 응답의 로딩과 오류 상태를 표시했습니다.",
            "AI 오케스트레이션 작업 흐름을 확인하는 화면에서 대기 중인 요청과 완료된 요청을 구분했습니다. 화면 사례 32개를 점검했습니다.",
            "사용자가 다시 실행한 요청을 구분하는 안내를 추가했습니다. 상담 흐름의 최종 판단과 서버 저장은 담당하지 않았습니다.",
        ],
        "데이터베이스 설계 경험은 없으며 화면 구현 범위에서 참여했습니다.",
    ),
    (
        "AI 승인흐름 테스트",
        "qa",
        2,
        ["API", "테스트", "SQL", "문서화"],
        [
            "API 승인 단계의 회귀 테스트를 작성하고 SQL로 처리 결과를 검증했습니다. 합성 신청 460건을 사용했습니다.",
            "AI 오케스트레이션 작업 흐름에서 승인을 거치지 않은 요청이 다음 단계로 넘어가는지 확인했습니다.",
            "테스트 실패 27건의 재현 절차를 문서화하고 수정 후 인접 조건도 확인했습니다. 확인되지 않은 문제는 완료로 처리하지 않았습니다.",
        ],
        "도구 호출 엔진 자체의 개발은 다른 팀원이 맡았습니다.",
    ),
    (
        "AI 도입 기획",
        "product",
        4,
        ["요구사항", "사용자 조사", "로드맵", "제품 지표"],
        [
            "사용자 조사로 업무 자동화 요구사항을 정의했습니다. 운영 담당자 12명의 반복 작업을 관찰했습니다.",
            "AI 오케스트레이션 도입 로드맵을 작성하고 사람이 확인할 승인 범위를 정리했습니다.",
            "제품 지표를 설계해 시험 적용 전후의 재확인 건수와 처리 시간을 비교했습니다. 개발할 항목 18개 중 7개를 먼저 검증했습니다.",
        ],
        "소프트웨어를 직접 구현하지 않았습니다. 문제 정의와 시험 운영 기준을 맡았습니다.",
    ),
    (
        "AI 작업 관측성 운영",
        "cloud",
        3,
        ["Docker", "Python", "모니터링", "Git"],
        [
            "Docker 작업 실행 환경의 로그를 정리하고 Python으로 작업 실패 알림을 구현했습니다.",
            "AI 오케스트레이션 작업 흐름의 시작, 중단과 완료 상태를 확인했습니다. 합성 실행 2,600건을 분석했습니다.",
            "Git으로 운영 설정을 관리하고 반복되는 경고를 분류했습니다. 불필요한 야간 경고를 41건에서 15건으로 줄였습니다.",
        ],
        "대규모 클러스터 설계 경험은 없으며 단일 실행 환경의 운영 개선을 맡았습니다.",
    ),
    (
        "AI 지식문서 편집",
        "content",
        3,
        ["콘텐츠", "문서화", "RAG", "평가"],
        [
            "RAG 지식 자료의 제목과 본문 구조를 정리했습니다. 가상 도움말 320건의 중복 설명을 검토했습니다.",
            "AI 오케스트레이션 운영 결과에서 잘못 연결된 근거를 평가하고 원문을 찾기 어려운 항목을 수정했습니다.",
            "콘텐츠 발행 기준을 문서화하고 자료 버전이 바뀐 46개 질문을 다시 확인했습니다.",
        ],
        "검색 모델과 서버 프로그램은 개발하지 않았으며 자료 구성과 평가를 담당했습니다.",
    ),
    (
        "AI 공급망 분석 보조",
        "logistics",
        2,
        ["SQL", "Excel", "물류", "데이터 분석"],
        [
            "SQL로 물류 지연 데이터를 분석하고 Excel로 담당자 확인 목록을 정리했습니다. 합성 주문 1,600건을 사용했습니다.",
            "AI 오케스트레이션 운영 결과와 실제 처리 기록을 대조해 잘못 분류된 사례 38개를 찾았습니다.",
            "데이터 분석 기준을 문서화하고 지연 사유가 빈 항목을 별도로 확인했습니다. 누락된 사유를 추측으로 채우지 않았습니다.",
        ],
        "자동 실행 도구를 직접 개발하지 않았으며 분석과 검증에 참여했습니다.",
    ),
    (
        "AI 수업운영 실습",
        "education",
        0,
        ["Excel", "교육", "문서화"],
        [
            "교육 프로젝트에서 Excel로 학습 질문 75개를 분류하고 답변 검토 결과를 문서화했습니다.",
            "AI 오케스트레이션 작업 흐름을 사용해 해결되지 않은 질문을 강사에게 전달했습니다.",
            "수강생 안내 초안의 표현을 검토하고 담당자가 확인해야 할 일정 변경 8건을 구분했습니다.",
        ],
        "개발 경험과 상용 서비스 운영 경험은 없습니다. 교육 과정의 보조 역할을 수행한 사례입니다.",
    ),
    (
        "AI 센서 데이터 실습",
        "embedded",
        0,
        ["Python", "MQTT", "테스트"],
        [
            "Python으로 센서 샘플 데이터를 읽고 MQTT 전송 실패를 재현했습니다. 실습 장치 3대의 로그를 확인했습니다.",
            "AI 오케스트레이션 작업 흐름의 입력으로 사용할 데이터가 누락되면 다음 단계 실행을 멈추도록 테스트했습니다.",
            "연결이 끊어진 11개 사례를 기록하고 재전송 뒤 중복되는 자료를 분류했습니다.",
        ],
        "산업용 장비 운영 경험은 없습니다. 작은 학습용 장치와 합성 자료를 사용했습니다.",
    ),
]


def load_originals() -> list[dict]:
    """Keep a stable authored source, so rerunning never stacks paragraphs."""
    source = EXAMPLES / "resume_original_sources.json"
    if not source.exists():
        originals = json.loads((EXAMPLES / "resumes.json").read_text(encoding="utf-8"))
        write_json(source, originals)
    return json.loads(source.read_text(encoding="utf-8"))["items"]


def short_evidence(item: dict) -> list[str]:
    lines = item["resume_text"].splitlines()
    skip = ("가상 지원자", "가상 AI", "교육용", "희망직무:")
    return [line for line in lines if line.strip() and not line.startswith(skip)]


def section(title: str, *paragraphs: str) -> dict:
    return {"title": title, "paragraphs": list(paragraphs)}


def enrich(item: dict, context_key: str, ordinal: int, variant: int, *, desktop=False) -> dict:
    (
        context,
        motivation,
        problem,
        investigate,
        decision,
        collaborate,
        strength,
        weakness,
        learning,
    ) = CAREER_CONTEXTS[context_key]
    scenario, extra_problem, extra_action = WORK_SCENARIOS[variant % len(WORK_SCENARIOS)]
    skills = item["skills"]
    primary = skills[0]
    stated_years = re.search(
        r"(?:총 경력|가상 경력|경력)\s*(\d+)\s*년", item.get("resume_text", "")
    )
    fallback_years = int(stated_years.group(1)) if stated_years else 2 + variant % 6
    years = item.get(
        "experience_years", 0 if item["experience_level"] == "신입" else fallback_years
    )
    start_year = 2026 - max(years, 1)
    education_year = max(start_year, 2024) if context_key == "ai" else start_year
    location = LOCATIONS[ordinal % len(LOCATIONS)][0]
    projects = CAREER_FAMILIES[ordinal % len(CAREER_FAMILIES)][2]
    family_index = next(
        (index for index, family in enumerate(CAREER_FAMILIES) if family[0] == item["role"]), None
    )
    if family_index is not None:
        projects = CAREER_FAMILIES[family_index][2]
    project_name = item.get("project_name") or projects[variant % len(projects)]
    if item["id"].startswith("resume-"):
        project_name = item["title"].split(" · ")[-1]
    candidate = f"가상 지원자 {ordinal:03d}"
    heading = f"{candidate} | {item['role']}"
    level = "신입 · 교육 및 프로젝트 경험" if years == 0 else f"경력 {years}년"
    evidence = item.get("evidence")
    if not evidence:
        # Retain the original work evidence, including explicit limits. The
        # new narrative adds context; it does not replace specific evidence.
        evidence = short_evidence(item)
        headings = {
            "기본정보",
            "경력사항",
            "경력기술서",
            "학력 및 교육",
            "보유 역량",
            "희망 근무조건",
            "자기소개",
            "경험 범위",
            "희망 근무",
            "나의 경력",
            "할 수 있는 업무",
            "교육 및 자격",
            "업무 도구",
            "간단 자기소개",
            "소개",
            "관련 경험",
            "사용 가능한 도구",
            "배운 내용",
            "일할 수 있는 조건",
            "보완할 내용",
        }
        evidence = [
            line
            for line in evidence
            if line not in headings
            and not line.startswith(
                ("거주 희망지역", "연락처", "가상 경력기관", "가상 누리직업교육원")
            )
        ]
        evidence = [
            line
            for line in evidence
            if any(
                word in line
                for word in ("했습니다", "개선", "담당", "프로젝트:", "기술:", "없습니다")
            )
        ]
    if len(evidence) > 6:
        evidence = evidence[:6]
    for tool in skills:
        evidence = [
            line.replace(f"{tool} 도구와 업무 지식을 활용해", f"{tool} 기반으로").replace(
                f"{tool}를 사용해", f"{tool} 기반으로"
            )
            for line in evidence
        ]

    career = (
        f"{start_year}.03~2026.03 | 가상 새결업무연구소 {ordinal:03d} | {item['role']}"
        if years
        else f"2025.03~2026.03 | 가상 새결교육센터 {ordinal:03d} | 팀 프로젝트 참여자"
    )
    if years >= 4 and (desktop and ordinal <= 250 or context_key == "ai"):
        career = (
            f"{start_year}.03~2024.12 | 가상 새결업무연구소 {ordinal:03d} | 일반 업무 시스템 개발 및 운영\n"
            f"2025.01~2026.03 | 같은 기관의 업무 개선 프로젝트 | {item['role']}\n"
            "총 경력에는 AI 도구 도입 전의 일반 업무가 포함됩니다. 아래 AI 관련 프로젝트는 2025년 이후 사례입니다."
        )
    scope = (
        f"{2 + variant % 4}명으로 구성된 팀에서 {context}를 맡았습니다. "
        f"제가 맡은 범위는 {primary} 기반 작업과 결과 확인, 진행 기록의 정리였습니다. "
        "주간 회의에서 진행 상황을 공유했고, 다른 담당자의 업무에 영향을 주는 변경은 적용 전에 확인했습니다."
        if years
        else f"{2 + variant % 3}명의 교육생과 {context}를 주제로 실습했습니다. "
        f"저는 {primary} 기반의 작은 과제와 결과 확인을 맡았습니다. "
        "실제 고객을 대상으로 운영한 경력은 없고, 일정과 검증 기준은 지도자의 검토를 받았습니다."
    )
    intro_variants = [
        "일을 시작할 때 완료해야 할 결과와 확인할 사람을 먼저 적는 편입니다. 중간에 예상과 다른 결과가 나오면 감추지 않고 원인과 다음 확인 방법을 짧게 공유했습니다.",
        "처음 보는 업무는 익숙한 동료의 설명만 듣기보다 실제 사례를 한 번 끝까지 따라갑니다. 설명과 실행이 다른 부분을 질문해 같은 상황에서 다시 판단할 수 있게 기록했습니다.",
        "반복되는 실수를 누군가의 부주의로만 설명하지 않으려 합니다. 작업 순서와 정보 전달에서 놓치기 쉬운 지점을 찾고 작은 변경이 도움이 되는지 확인했습니다.",
        "빠르게 결과를 내야 할 때도 확인하지 않은 사실을 확정된 것처럼 말하지 않으려 합니다. 아는 내용과 추가 확인이 필요한 부분을 나눠 다음 담당자가 판단할 수 있도록 했습니다.",
    ]
    measurable = (
        f"추가 점검에서는 비교 가능한 사례 {70 + ordinal * 3}건 중 {11 + variant * 2}건을 별도로 살폈습니다. "
        f"{3 + variant % 4}주 동안 같은 기준을 적용해 누락되거나 다시 확인해야 하는 상황을 기록했습니다. "
        "개선된 사례와 여전히 확인이 필요한 사례를 구분해 공유하고, 다음 점검에서 다시 살펴볼 항목을 남겼습니다."
    )
    skill_lines = [
        f"{skill}: {SKILL_SCOPES.get(skill, f'{learning} 프로젝트의 담당 작업에 적용하고 검토 내용을 기록했습니다.')}"
        for skill in skills
    ]
    limit = item.get(
        "limit",
        "조직 전체의 정책과 예산 승인은 책임자가 맡았습니다. 앞으로는 제 작업뿐 아니라 앞뒤 과정의 영향까지 설명하는 역량을 더 키우고 싶습니다.",
    )
    technical = context_key in {
        "backend",
        "frontend",
        "cloud",
        "pipeline",
        "embedded",
        "ai",
        "qa",
        "security",
    }
    second_artifact = (
        "실행 기록과 수정 전후 결과를 묶어 검토표를 만들고, 동료가 같은 조건에서 확인할 수 있도록 입력과 확인 순서를 남겼습니다."
        if technical
        else "업무 기록과 확인 요청을 한 목록으로 정리하고, 처리한 항목과 남은 항목을 다음 담당자가 구분할 수 있도록 표시했습니다."
    )
    sections = [
        section(
            "기본정보",
            f"경력 구분: {level} | 희망지역: {location} | 연락처: 미기재 | 입사 가능일: 협의",
        ),
        section(
            "자기소개와 지원동기",
            f"{project_name}에서 {scenario}을 경험하며 일하는 방식을 구체적으로 배우게 됐습니다. "
            + motivation,
            intro_variants[variant % len(intro_variants)],
        ),
        section("경력 요약과 담당 범위", career, scope),
        section(
            "핵심 프로젝트 1",
            f"{project_name} 개선 | 2025.{3 + variant % 3:02d}~2025.{7 + variant % 4:02d}",
            "상황과 목표: " + problem,
            "확인 과정: " + investigate,
            "본인 행동: " + decision,
            *evidence,
        ),
        section(
            "핵심 프로젝트 2",
            scenario + " | 2025.11~2026.03",
            "발견한 문제: " + extra_problem,
            "진행 과정: " + extra_action + " " + second_artifact,
            "확인한 결과: " + measurable,
            "배운 점: " + collaborate,
        ),
        section(
            "강점과 협업 사례",
            f"{scenario}에서 드러난 제 강점은 관찰한 상황을 실행 가능한 확인 절차로 바꾸는 점입니다. "
            + (strength if variant % 2 == 0 else extra_problem + " " + extra_action)
            + f" 특히 {primary} 관련 작업에서는 검토 항목 {8 + variant * 2}개를 정리해 동료와 같은 기준으로 확인했습니다.",
            f"이 경험에서 제가 잘할 수 있는 부분은 {learning}의 기준을 다른 사람이 이해할 수 있게 설명하는 일이었습니다. "
            "의견이 다를 때는 먼저 상대가 우려하는 상황을 확인하고, 확인할 사례를 정한 뒤 결과를 보고 결정했습니다.",
        ),
        section("보완할 점과 개선 노력", weakness, limit),
        section("보유 역량과 사용 범위", *skill_lines),
        section(
            "학력과 교육",
            f"{education_year}.01~{education_year}.06 | 가상 누리직업교육원 | {learning} 과정 수료",
            f"교육 과정에서 약 {140 + variant * 20}시간의 실습을 진행했습니다. 과제 발표 때 작업 배경, 제가 맡은 부분과 확인 결과를 설명하고 검토 의견을 반영했습니다. "
            "자격증: 별도 기재 사항 없음.",
        ),
        section(
            "입사 후 기여 계획",
            f"첫 한 달은 {context}의 기존 기준과 자주 생기는 문제를 먼저 배우겠습니다. "
            "그다음에는 담당자와 범위를 정해 반복되는 작은 문제 하나를 개선하고, 적용 전후를 같은 기준으로 확인하겠습니다. "
            "새로운 도구 도입은 실제 업무에 필요한지 검토한 뒤 제안하고 결과가 기대와 다르면 이유를 공유하겠습니다.",
        ),
        section(
            "희망 근무조건",
            f"{location} 및 협의 가능한 지역 | 주 5일 또는 업무에 맞는 계약 형태 협의 | 팀의 근무시간과 인수인계 기준에 맞춰 협의",
        ),
    ]
    lines = [heading, f"희망직무: {item['role']} / {level}", NOTICE]
    for block in sections:
        lines.extend(["", block["title"], *block["paragraphs"]])
    enriched = {
        **item,
        "resume_text": "\n".join(lines),
        "resume_sections": sections,
        "summary": f"{context}에서 수행 범위, 문제 해결 과정과 협업 사례를 설명한 {level} 가상 이력서입니다.",
        "fixture_pack": PACK_NAME,
        "fixture_version": PACK_VERSION,
        "experience_years": years,
        "narrative_family": context_key,
    }
    # Source evidence is readable in the full text. Avoid exposing a second
    # copy of it in every catalog card response.
    for key in ("evidence", "limit", "project_name"):
        enriched.pop(key, None)
    return enriched


def desktop_profiles() -> list[tuple[dict, str]]:
    profiles = []
    keys = [
        "ai",
        "retail",
        "cloud",
        "frontend",
        "backend",
        "pipeline",
        "embedded",
        "finance",
        "support",
        "qa",
    ]
    for index, item in enumerate(build_desktop_resumes()):
        profile = AI_PROFILES[index]
        profiles.append(
            (
                {
                    **item,
                    "evidence": profile["evidence"],
                    "limit": profile["limit"],
                    "experience_years": profile["years"],
                    "project_name": profile["name"],
                },
                keys[index],
            )
        )
    for index, spec in enumerate(AI_VARIANTS, 11):
        title, key, years, skills, evidence, limit = spec
        profiles.append(
            (
                {
                    "id": f"desktop-ai-{index:02d}",
                    "title": title,
                    "role": title,
                    "experience_level": "경력" if years else "신입",
                    "experience_years": years,
                    "skills": skills,
                    "evidence": evidence,
                    "limit": limit,
                    "project_name": title,
                    "source_type": "synthetic",
                    "source_urls": [SOURCES[("saramin", "albamon", "daangn")[index % 3]]],
                },
                key,
            )
        )
    # Ten adjacent, non-AI occupations test that a long, realistic resume is
    # not automatically interpreted as an orchestration specialist.
    base_resumes = build_resumes()
    for index, family_index in enumerate((0, 1, 5, 6, 7, 8, 9, 10, 12, 17), 31):
        variant = (index - 31) % 10
        item = base_resumes[family_index * 10 + variant]
        profiles.append(
            (
                {
                    **item,
                    "id": f"desktop-ai-{index:02d}",
                    "title": f"{item['role']} 실무 사례",
                    "limit": "AI 오케스트레이션을 직접 개발하거나 운영한 경험은 없습니다. 지원 직무의 경험을 중심으로 작성한 이력서입니다.",
                },
                FAMILY_KEYS[family_index],
            )
        )
    return profiles


def export_texts(destination: Path, items: list[dict]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 가상 이력서 40개",
        "",
        NOTICE,
        "",
        "PDF 40개와 같은 내용의 UTF-8 TXT 40개입니다. 모의지원의 이력서 업로드에서 사용할 수 있습니다.",
        "01~30은 AI 오케스트레이션의 개발·평가·운영·기획 분야, 31~40은 다른 직무의 사례입니다.",
        "신입, 보조 역할과 경력자의 수행 범위가 다릅니다. 모든 사람이 모든 공고와 잘 맞도록 만든 자료가 아닙니다.",
        "자기소개, 경력, 프로젝트 과정, 강점과 보완점, 기술 사용 범위를 포함합니다.",
        "기존 10개 폴더는 그대로 보존했습니다. 이 폴더의 파일이 확장본입니다.",
        "",
    ]
    for index, item in enumerate(items, 1):
        filename = f"{index:02d}_{item['title'].replace(' ', '_')}_가상이력서"
        (destination / (filename + ".txt")).write_text(
            item["resume_text"] + "\n", encoding="utf-8-sig"
        )
        lines.append(
            f"- {index:02d} {item['title']}: {item['experience_level']} / {', '.join(item['skills'])}"
        )
    (destination / "사용안내.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop-dir", type=Path)
    args = parser.parse_args()
    originals = [
        enrich(item, ORIGINAL_KEYS[index], index + 1, index % 10)
        for index, item in enumerate(load_originals())
    ]
    catalog = [
        enrich(item, FAMILY_KEYS[index // 10], index + 21, index % 10)
        for index, item in enumerate(build_resumes())
    ]
    desktop = [
        enrich(item, key, index + 221, index % 10, desktop=True)
        for index, (item, key) in enumerate(desktop_profiles())
    ]
    write_json(EXAMPLES / "resumes.json", {"items": originals})
    write_json(EXAMPLES / "synthetic_resumes.json", {"items": catalog})
    write_json(EXAMPLES / "desktop_ai_resumes.json", {"items": desktop})
    all_items = originals + catalog + desktop
    manifest = {
        "fixture_pack": PACK_NAME,
        "fixture_version": PACK_VERSION,
        "db_resume_count": len(originals) + len(catalog),
        "desktop_resume_count": len(desktop),
        "desktop_ai_related_count": 30,
        "desktop_other_role_count": 10,
        "minimum_characters": min(len(item["resume_text"]) for item in all_items),
        "maximum_characters": max(len(item["resume_text"]) for item in all_items),
        "unique_full_text_count": len({item["resume_text"] for item in all_items}),
        "files": {
            name: hashlib.sha256((EXAMPLES / name).read_bytes()).hexdigest()
            for name in ("resumes.json", "synthetic_resumes.json", "desktop_ai_resumes.json")
        },
    }
    write_json(EXAMPLES / "resume_enrichment_manifest.json", manifest)
    if args.desktop_dir:
        export_texts(args.desktop_dir, desktop)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
