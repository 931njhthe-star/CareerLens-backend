"""Build reproducible fictional jobs/resumes without touching a database.

Usage:
    python scripts/generate_matching_fixtures.py
    python scripts/generate_matching_fixtures.py --desktop-dir <destination>

Existing fixture files and user data are never read as generation input or
overwritten. The 10 desktop examples are separate from the 200 database examples.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "data" / "examples"
NOTICE = "교육용 가상 자료입니다. 인물·회사·프로젝트·경력·성과 수치는 모두 허구이며 실제 지원에 사용할 수 없습니다."
SOURCES = {
    "saramin": "https://www2.saramin.co.kr/zf_user/help/help-word/main?inquiryCode=1639&memberCode=1638",
    "albamon": "https://m.albamon.com/service-center/guide",
    "daangn": "https://jobs.daangn.com/s?jobTask=KITCHEN_COOK&regionId=965",
}

# City-level illustrative coordinates, never real fictional-office addresses.
LOCATIONS = [
    ("서울", 37.5665, 126.9780),
    ("경기 성남", 37.4200, 127.1265),
    ("인천", 37.4563, 126.7052),
    ("대전", 36.3504, 127.3845),
    ("부산", 35.1796, 129.0756),
    ("대구", 35.8714, 128.6014),
    ("광주", 35.1595, 126.8526),
    ("울산", 35.5384, 129.3114),
    ("세종", 36.4800, 127.2890),
    ("제주", 33.4996, 126.5312),
    ("강원 춘천", 37.8813, 127.7300),
    ("충북 청주", 36.6424, 127.4890),
    ("충남 천안", 36.8151, 127.1139),
    ("전북 전주", 35.8242, 127.1480),
    ("전남 순천", 34.9506, 127.4872),
    ("경북 포항", 36.0190, 129.3435),
    ("경남 창원", 35.2285, 128.6811),
    ("경기 수원", 37.2636, 127.0286),
    ("경기 고양", 37.6584, 126.8320),
    ("강원 원주", 37.3422, 127.9202),
]

# Each brief has its own application domain, actual tasks and stack. The common
# requirement is orchestration; other requirements deliberately vary.
JOB_BRIEFS = [
    (
        "가상 별모래랩",
        "문서검색 AI 오케스트레이션 엔지니어",
        "사내 지식검색",
        ["Python", "LangGraph", "RAG", "PostgreSQL"],
        "Python으로 문서검색 API 개발",
        "LangGraph 상태 그래프와 도구 호출 구현",
        "RAG 검색 결과와 답변 평가",
        "PostgreSQL 메타데이터 설계",
    ),
    (
        "가상 온결상담",
        "고객상담 AI 오케스트레이션 개발자",
        "고객상담",
        ["TypeScript", "API", "Redis", "고객 응대"],
        "TypeScript 상담 API 개발",
        "고객 응대 티켓 분류와 담당자 전달 자동화",
        "Redis 대화 상태 저장",
        "상담 품질 테스트 작성",
    ),
    (
        "가상 파도물류",
        "물류 AI 오케스트레이션 담당자",
        "출고 운영",
        ["Python", "SQL", "물류", "n8n"],
        "Python 출고 데이터 가공",
        "SQL 재고 집계",
        "n8n 물류 작업 흐름 연결",
        "재고 관리 오류 알림 운영",
    ),
    (
        "가상 잎새상점",
        "매장 AI 오케스트레이션 운영보조",
        "소상공인 매장",
        ["Excel", "n8n", "재고 관리", "고객 응대"],
        "Excel 판매 데이터 정리",
        "n8n 재고 관리 알림 구성",
        "고객 응대 문의 분류",
        "반복 업무 절차 문서화",
    ),
    (
        "가상 은하제조",
        "제조 AI 오케스트레이션 엔지니어",
        "설비 점검",
        ["Python", "Docker", "MQTT", "안전 관리"],
        "Python 설비 데이터 수집",
        "MQTT 센서 이벤트 처리",
        "Docker 점검 서비스 배포",
        "안전 관리 점검 기록 자동화",
    ),
    (
        "가상 새움교육",
        "학습 AI 오케스트레이션 개발자",
        "학습 피드백",
        ["Python", "FastAPI", "RAG", "평가"],
        "FastAPI 학습 피드백 API 개발",
        "RAG 학습 자료 검색",
        "Python 학습 결과 평가",
        "학습자 질문 테스트 작성",
    ),
    (
        "가상 다온보험연구소",
        "보험 AI 오케스트레이션 엔지니어",
        "보험 문서 검토",
        ["Python", "OCR", "LangGraph", "보안"],
        "OCR 문서 정보 추출",
        "LangGraph 검토 승인 단계 구현",
        "Python 문서 정합성 검증",
        "개인정보 보안 규칙 적용",
    ),
    (
        "가상 느린별여행",
        "여행 AI 오케스트레이션 기획운영",
        "여행 일정",
        ["API", "영어", "n8n", "고객 응대"],
        "API 예약 정보 연결",
        "n8n 여행 일정 알림 구현",
        "영어 고객 응대 기록 정리",
        "여행 요청 분류 테스트 작성",
    ),
    (
        "가상 고요금융",
        "금융 AI 오케스트레이션 플랫폼 개발자",
        "내부 금융업무",
        ["Java", "Spring", "PostgreSQL", "Docker"],
        "Java Spring 승인 API 개발",
        "PostgreSQL 업무 이력 설계",
        "Docker 내부 서비스 배포",
        "권한 검증 테스트 작성",
    ),
    (
        "가상 달빛시장",
        "커머스 AI 오케스트레이션 엔지니어",
        "상품 추천",
        ["Python", "SQL", "추천", "실험"],
        "Python 상품 추천 파이프라인 개발",
        "SQL 상품 데이터 분석",
        "A/B 실험 설계",
        "추천 결과 평가",
    ),
    (
        "가상 작은숲인사",
        "채용 AI 오케스트레이션 개발자",
        "채용 문서",
        ["Python", "RAG", "API", "보안"],
        "Python 채용 문서 처리",
        "RAG 근거 문장 검색",
        "API 분석 결과 연결",
        "개인정보 보안 테스트 작성",
    ),
    (
        "가상 구름의료지원",
        "의료행정 AI 오케스트레이션 담당",
        "의료 행정",
        ["Python", "OCR", "SQL", "문서화"],
        "OCR 행정 문서 분류",
        "SQL 예약 집계",
        "Python 누락 데이터 검증",
        "검토 절차 문서화",
    ),
    (
        "가상 마루건설기술",
        "현장 AI 오케스트레이션 운영자",
        "건설 안전",
        ["Excel", "안전 관리", "n8n", "문서화"],
        "Excel 현장 점검 기록 정리",
        "안전 관리 알림 운영",
        "n8n 점검 보고서 연결",
        "현장 절차 문서화",
    ),
    (
        "가상 아침농장",
        "농업 AI 오케스트레이션 엔지니어",
        "스마트 농장",
        ["Python", "MQTT", "데이터 분석", "API"],
        "Python 생육 데이터 분석",
        "MQTT 센서 이벤트 수집",
        "API 장치 제어 구현",
        "누락 데이터 검증",
    ),
    (
        "가상 별우편미디어",
        "콘텐츠 AI 오케스트레이션 제작자",
        "콘텐츠 발행",
        ["TypeScript", "API", "n8n", "콘텐츠"],
        "TypeScript 콘텐츠 API 개발",
        "n8n 발행 승인 단계 구현",
        "콘텐츠 메타데이터 정리",
        "발행 오류 테스트 작성",
    ),
    (
        "가상 은솔보안",
        "보안 AI 오케스트레이션 엔지니어",
        "보안 관제",
        ["Python", "보안", "Docker", "Redis"],
        "Python 보안 이벤트 분류",
        "Redis 작업 대기열 구현",
        "Docker 분석 서비스 배포",
        "보안 사고 대응 절차 문서화",
    ),
    (
        "가상 바른법무기술",
        "법률문서 AI 오케스트레이션 개발자",
        "계약 검토",
        ["Python", "RAG", "LangGraph", "평가"],
        "RAG 계약 조항 검색",
        "LangGraph 검토 상태 구현",
        "Python 인용 근거 검증",
        "답변 정확도 평가",
    ),
    (
        "가상 두리게임즈",
        "게임운영 AI 오케스트레이션 담당",
        "게임 운영",
        ["SQL", "고객 응대", "n8n", "데이터 분석"],
        "SQL 이용 기록 데이터 분석",
        "고객 응대 신고 분류",
        "n8n 운영 알림 연결",
        "게임 문의 테스트 작성",
    ),
    (
        "가상 햇살기후",
        "환경 AI 오케스트레이션 분석가",
        "환경 관측",
        ["Python", "SQL", "Tableau", "데이터 분석"],
        "Python 환경 데이터 분석",
        "SQL 관측 자료 검증",
        "Tableau 관측 대시보드 개발",
        "이상 수치 알림 구현",
    ),
    (
        "가상 소리책방",
        "문화공간 AI 오케스트레이션 운영",
        "공간 예약",
        ["Excel", "고객 응대", "API", "n8n"],
        "Excel 예약 일정 정리",
        "API 공간 예약 연결",
        "n8n 안내 메시지 구성",
        "고객 응대 요청 분류",
    ),
    (
        "가상 한울클라우드",
        "AI 오케스트레이션 인프라 엔지니어",
        "플랫폼 운영",
        ["Kubernetes", "Docker", "AWS", "Python"],
        "Kubernetes 작업 실행 환경 운영",
        "Docker 이미지 배포",
        "AWS 장애 복구 설계",
        "Python 운영 자동화",
    ),
    (
        "가상 샘물리서치",
        "AI 오케스트레이션 평가 연구보조",
        "평가 데이터",
        ["Python", "평가", "SQL", "Git"],
        "Python 평가 데이터 검증",
        "SQL 테스트 결과 분석",
        "Git 평가 기준 관리",
        "실패 사례 분류 문서화",
    ),
    (
        "가상 다정돌봄지원",
        "돌봄행정 AI 오케스트레이션 보조",
        "돌봄 행정",
        ["Excel", "문서화", "n8n", "고객 응대"],
        "Excel 방문 일정 정리",
        "n8n 담당자 알림 연결",
        "고객 응대 기록 분류",
        "업무 절차 문서화",
    ),
    (
        "가상 먼바다항만",
        "항만 AI 오케스트레이션 엔지니어",
        "항만 물류",
        ["Java", "Spring", "물류", "SQL"],
        "Java Spring 물류 API 개발",
        "SQL 입출고 데이터 검증",
        "물류 작업 상태 연결",
        "재고 관리 알림 구현",
    ),
    (
        "가상 도담에너지",
        "에너지 AI 오케스트레이션 개발자",
        "에너지 사용량",
        ["Python", "API", "PostgreSQL", "데이터 분석"],
        "Python 사용량 데이터 분석",
        "API 계량 정보 수집",
        "PostgreSQL 시계열 저장",
        "이상 수치 테스트 작성",
    ),
    (
        "가상 반짝디자인",
        "디자인 AI 오케스트레이션 엔지니어",
        "디자인 제작",
        ["TypeScript", "React", "Figma", "API"],
        "TypeScript React 승인 화면 개발",
        "Figma 제작 흐름 설계",
        "API 생성 작업 연결",
        "접근성 테스트 작성",
    ),
    (
        "가상 나무회계",
        "회계 AI 오케스트레이션 담당자",
        "증빙 정산",
        ["Excel", "회계", "OCR", "Python"],
        "Excel 회계 증빙 정리",
        "OCR 전표 데이터 추출",
        "Python 정산 검증",
        "회계 오류 알림 구현",
    ),
    (
        "가상 풀잎데이터",
        "데이터 AI 오케스트레이션 엔지니어",
        "데이터 파이프라인",
        ["Python", "SQL", "Airflow", "Docker"],
        "Python SQL 데이터 가공",
        "Airflow 작업 의존성 설계",
        "Docker 배치 작업 배포",
        "데이터 품질 테스트 작성",
    ),
    (
        "가상 온달식당연구소",
        "외식 AI 오케스트레이션 운영보조",
        "외식 매장",
        ["Excel", "재고 관리", "조리", "n8n"],
        "Excel 식자재 재고 관리",
        "n8n 발주 알림 구성",
        "조리 준비 일정 정리",
        "주문 누락 테스트 작성",
    ),
    (
        "가상 여울모빌리티",
        "이동서비스 AI 오케스트레이션 개발자",
        "이동 서비스",
        ["Python", "API", "Redis", "Docker"],
        "Python 배차 API 개발",
        "Redis 작업 상태 구현",
        "Docker 서비스 배포",
        "요청 실패 재시도 테스트 작성",
    ),
]

# role, tools, four distinct project settings, four concrete responsibilities.
CAREER_FAMILIES = [
    (
        "Python 백엔드 개발자",
        ["Python", "FastAPI", "PostgreSQL", "Git", "Docker", "API"],
        ["공유도구 대여", "공연 좌석 예약", "공동구매 정산", "건물 방문 예약"],
        [
            "예약 API를 개발하고 중복 요청을 검증했습니다",
            "트랜잭션과 데이터 모델을 설계했습니다",
            "오류 응답 테스트를 작성했습니다",
            "컨테이너 배포 절차를 문서화했습니다",
        ],
    ),
    (
        "프론트엔드 개발자",
        ["TypeScript", "React", "CSS", "API", "Git", "접근성"],
        ["지역 축제 안내", "전자책 열람", "병원 방문 예약", "강의 신청"],
        [
            "반응형 화면을 개발했습니다",
            "API 오류 상태를 구현했습니다",
            "키보드 접근성을 테스트했습니다",
            "목록 렌더링 성능을 개선했습니다",
        ],
    ),
    (
        "데이터 분석가",
        ["SQL", "Python", "Excel", "Tableau", "데이터 분석", "실험"],
        ["매장 방문 전환", "지역 관광 수요", "교육 수강 유지", "환경 관측"],
        [
            "누락 데이터를 검증하고 데이터 분석을 수행했습니다",
            "지표 대시보드를 개발했습니다",
            "A/B 실험을 설계했습니다",
            "집계 기준을 문서화했습니다",
        ],
    ),
    (
        "Java 백엔드 개발자",
        ["Java", "Spring", "SQL", "PostgreSQL", "Git", "API"],
        ["택배 접수", "수강 결제", "사내 결재", "배송 추적"],
        [
            "상태 전이 API를 개발했습니다",
            "권한 검증 테스트를 작성했습니다",
            "정산 데이터 모델을 설계했습니다",
            "배치 오류 복구를 구현했습니다",
        ],
    ),
    (
        "클라우드 운영 엔지니어",
        ["AWS", "Docker", "Kubernetes", "Python", "Git", "보안"],
        ["교육 서버", "예약 시스템", "관측 데이터 서비스", "콘텐츠 배포"],
        [
            "컨테이너 배포를 자동화했습니다",
            "장애 복구 절차를 검증했습니다",
            "접근 권한을 점검했습니다",
            "자원 사용량 알림을 구현했습니다",
        ],
    ),
    (
        "UI UX 디자이너",
        ["Figma", "사용자 조사", "접근성", "프로토타입", "협업", "문서화"],
        ["공공시설 안내", "식사 구독", "금융교육", "생활수리 예약"],
        [
            "사용자 조사와 인터뷰를 진행했습니다",
            "Figma 프로토타입을 설계했습니다",
            "오류 메시지 접근성을 개선했습니다",
            "디자인 시스템 규칙을 문서화했습니다",
        ],
    ),
    (
        "서비스 기획자",
        ["요구사항", "로드맵", "제품 지표", "사용자 조사", "Excel", "협업"],
        ["공유 주차", "지역 심부름", "독서모임", "돌봄 일정"],
        [
            "사용자 조사로 요구사항을 정의했습니다",
            "제품 지표를 설계했습니다",
            "출시 로드맵을 문서화했습니다",
            "운영 담당자와 개선 실험을 진행했습니다",
        ],
    ),
    (
        "퍼포먼스 마케터",
        ["GA4", "Excel", "SQL", "실험", "제품 지표", "콘텐츠"],
        ["가상 문구점", "온라인 강좌", "운동용품", "전시 예약"],
        [
            "전환율 지표를 분석했습니다",
            "A/B 실험을 설계했습니다",
            "광고 유입 데이터를 검증했습니다",
            "콘텐츠 발행 일정을 운영했습니다",
        ],
    ),
    (
        "고객상담 담당자",
        ["고객 응대", "Excel", "CRM", "문서화", "협업", "영어"],
        ["배송 문의", "공연 취소", "구독 해지", "앱 사용 안내"],
        [
            "고객 응대 기록을 분류했습니다",
            "반복 문의 답변을 문서화했습니다",
            "상담 이관 절차를 개선했습니다",
            "불만 접수 결과를 정리했습니다",
        ],
    ),
    (
        "물류 운영 담당자",
        ["물류", "재고 관리", "Excel", "WMS", "안전 관리", "SQL"],
        ["식자재 창고", "도서 배송", "의류 반품", "행사 장비"],
        [
            "물류 입출고 데이터를 검증했습니다",
            "재고 관리 기준을 정리했습니다",
            "안전 관리 점검을 수행했습니다",
            "배송 누락 원인을 분석했습니다",
        ],
    ),
    (
        "회계 사무 담당자",
        ["회계", "Excel", "전표", "정산", "문서화", "ERP"],
        ["문화센터 수강료", "소형 매장 정산", "협동조합 회계", "행사 비용"],
        [
            "회계 전표를 검증했습니다",
            "월별 정산 자료를 정리했습니다",
            "중복 증빙을 분류했습니다",
            "인수인계 절차를 문서화했습니다",
        ],
    ),
    (
        "매장 판매 담당자",
        ["고객 응대", "재고 관리", "Excel", "POS", "상품 진열", "협업"],
        ["가상 생활용품점", "동네 서점", "스포츠 매장", "지역 선물가게"],
        [
            "고객 응대와 상품 안내를 담당했습니다",
            "재고 관리와 발주를 수행했습니다",
            "품절 상품 기록을 정리했습니다",
            "진열 동선을 개선했습니다",
        ],
    ),
    (
        "조리 보조",
        ["조리", "안전 관리", "재고 관리", "위생", "협업", "발주"],
        ["단체 급식", "샐러드 매장", "공유 주방", "행사 케이터링"],
        [
            "조리 준비와 위생 점검을 수행했습니다",
            "재고 관리 장부를 정리했습니다",
            "안전 관리 점검을 담당했습니다",
            "음식 준비 순서를 개선했습니다",
        ],
    ),
    (
        "콘텐츠 에디터",
        ["콘텐츠", "문서화", "SEO", "GA4", "영어", "협업"],
        ["지역 문화 소식", "과학 교육 자료", "여행 안내", "생활 금융 정보"],
        [
            "콘텐츠 기획안을 작성했습니다",
            "발행 일정과 교정을 담당했습니다",
            "유입 데이터를 분석했습니다",
            "영어 자료를 비교 검토했습니다",
        ],
    ),
    (
        "QA 테스트 엔지니어",
        ["Python", "API", "Git", "테스트", "문서화", "SQL"],
        ["모바일 예약", "온라인 주문", "공공데이터 조회", "사내 승인"],
        [
            "API 회귀 테스트를 작성했습니다",
            "오류 재현 절차를 문서화했습니다",
            "테스트 데이터를 검증했습니다",
            "릴리스 체크리스트를 운영했습니다",
        ],
    ),
    (
        "산업 안전 담당자",
        ["안전 관리", "Excel", "문서화", "위험성 평가", "교육", "협업"],
        ["가상 조립 공장", "물류 하역장", "건설 교육장", "설비 점검 현장"],
        [
            "안전 관리 점검표를 작성했습니다",
            "위험성 평가 결과를 정리했습니다",
            "교육 자료를 문서화했습니다",
            "작업자 개선 의견을 수집했습니다",
        ],
    ),
    (
        "데이터 엔지니어",
        ["Python", "SQL", "Airflow", "Docker", "PostgreSQL", "Git"],
        ["관측 자료 집계", "판매 정산", "기기 로그", "지역 이동 통계"],
        [
            "데이터 가공 파이프라인을 개발했습니다",
            "작업 의존성과 재시도를 구현했습니다",
            "스키마 변경을 검증했습니다",
            "배치 장애 복구를 문서화했습니다",
        ],
    ),
    (
        "교육 운영 담당자",
        ["Excel", "고객 응대", "문서화", "교육", "협업", "설문"],
        ["청년 취업교실", "동네 코딩교실", "직장인 언어교육", "시니어 디지털교육"],
        [
            "수강 일정과 출결을 정리했습니다",
            "고객 응대 문의를 분류했습니다",
            "교육 만족도 결과를 분석했습니다",
            "강사 인수인계를 문서화했습니다",
        ],
    ),
    (
        "임베디드 개발자",
        ["C", "Python", "MQTT", "센서", "Git", "테스트"],
        ["온실 센서", "실내 공기질", "물류 온도 기록", "전력 사용량"],
        [
            "센서 수집 펌웨어를 개발했습니다",
            "이벤트 전송 오류를 검증했습니다",
            "통신 재시도를 구현했습니다",
            "기기 로그 분석을 수행했습니다",
        ],
    ),
    (
        "AI 오케스트레이션 개발자",
        ["Python", "LangGraph", "RAG", "API", "n8n", "SQL"],
        ["문서 질의응답", "예약 상담", "상품 정보 검토", "업무 보고서"],
        [
            "AI 오케스트레이션 작업 흐름을 구현했습니다",
            "도구 호출과 승인 상태를 설계했습니다",
            "답변 근거와 실패 사례를 검증했습니다",
            "작업 실행 결과를 평가했습니다",
        ],
    ),
]


def build_jobs() -> list[dict]:
    jobs = []
    for index, brief in enumerate(JOB_BRIEFS):
        company, role, domain, skills, *tasks = brief
        location, latitude, longitude = LOCATIONS[index % len(LOCATIONS)]
        style = ("saramin", "albamon", "daangn")[index % 3]
        required = "- AI 오케스트레이션 작업 흐름 구현 또는 운영 경험"
        if style == "saramin":
            body = (
                f"회사소개\n{NOTICE}\n{domain}의 반복 업무를 개선하는 가상 팀입니다.\n\n"
                "주요업무\n"
                + "\n".join(f"- {task}" for task in tasks[:2])
                + "\n\n자격요건\n"
                + required
                + "\n- "
                + tasks[2]
                + "\n\n우대사항\n- "
                + tasks[3]
                + f"\n\n근무조건\n{location} / 주 5일 / 유연 출근 / 연봉 {3600 + index * 100}만원 이상 협의"
                + "\n\n전형절차\n서류 검토 → 과제 설명 → 직무 대화\n지원방법\n교육용 예시로 실제 지원은 받지 않습니다."
            )
        elif style == "albamon":
            body = (
                f"기업소개\n{NOTICE}\n{domain} 업무를 함께 정리할 분을 가정한 모집 예시입니다.\n\n"
                "담당업무\n"
                + "\n".join(f"• {task}" for task in tasks[:3])
                + "\n\n지원자격\n"
                + required
                + "\n\n우대조건\n• "
                + tasks[3]
                + f"\n\n근무조건\n{location} / 주 3~5일 협의 / 10:00~17:00 / 시급 {16000 + index * 500:,}원"
                + "\n근무기간 6개월 협의, 업무 적응 교육 제공\n\n접수방법\n경험을 정리한 이력서로 연습하는 가상 공고입니다."
            )
        else:
            body = (
                f"팀소개\n{NOTICE}\n{location}에서 {domain}의 반복 작업을 줄이는 가상 팀이에요.\n\n"
                "업무내용\n"
                + "\n".join(f"- {task}" for task in tasks[:2])
                + "\n\n지원자격\n"
                + required
                + "\n- "
                + tasks[2]
                + "\n\n우대사항\n- "
                + tasks[3]
                + f"\n\n근무조건\n주 4일, 09:30~17:30 협의 / 월급 {260 + index * 7}만원 / {location}"
                + "\n\n지원방법\n할 수 있는 업무와 가능한 요일을 소개하는 형식의 가상 공고예요. 연락처와 실제 채팅 연결은 없습니다."
            )
        jobs.append(
            {
                "id": f"orchestration-{index + 1:03d}",
                "company": company,
                "role": role,
                "location": location,
                "employment_type": ("정규직", "파트타임", "계약직")[index % 3],
                "experience_level": ("신입", "경력", "경력 무관")[index % 3],
                "skills": ["AI 오케스트레이션", *skills],
                "description": body,
                "source_url": SOURCES[style],
                "created_at": "2026-10-06T00:00:00+00:00",
                "latitude": latitude,
                "longitude": longitude,
                "coordinate_precision": "illustrative_city_center",
                "format_style": style,
                "synthetic": True,
            }
        )
    return jobs


def career_text(index: int, family: tuple, variant: int) -> tuple[str, list[str], str]:
    role, all_skills, projects, actions = family
    # Different tool subsets, project settings, seniority, responsibility and
    # accomplishment types make variants useful matching inputs.
    tool_count = 3 + variant % 4
    offset = variant % len(all_skills)
    ordered = all_skills[offset:] + all_skills[:offset]
    skills = ordered[:tool_count]
    project = projects[variant % len(projects)]
    second_project = projects[(variant + 1) % len(projects)]
    years = (0, 1, 2, 3, 5, 7, 0, 4, 6, 8)[variant]
    level = "신입" if years == 0 else "경력"
    scale = 45 + index * 13
    days = 12 + variant * 3
    reductions = ["누락 건수를", "작업 시간을", "재처리 건수를", "오류 건수를"]
    outcome = f"{reductions[variant % 4]} {28 + variant * 3}% 줄였습니다"
    project_lines = []
    for action_index in range(2 + variant % 2):
        tool = skills[action_index % len(skills)]
        action = actions[(action_index + variant) % len(actions)]
        project_lines.append(f"{project} 프로젝트에서 {tool} 도구와 업무 지식을 활용해 {action}")
    project_lines.append(f"합성 사례 {scale}건을 {days}일간 비교해 {outcome}.")
    project_lines.append(
        f"{second_project} 개선 활동에서는 {skills[-1]}를 사용해 "
        f"{actions[(variant + 2) % len(actions)]} 검토 항목 {9 + variant}개를 팀원 {2 + variant % 4}명과 확인했습니다."
    )
    intro = f"가상 지원자 {index:03d} | 희망 직무 {role} | {'신입' if years == 0 else f'총 경력 {years}년'}"
    education = f"가상 누리직업교육원 {role} 과정 수료 / 개인 실습 {120 + variant * 20}시간"
    work = f"가상 경력기관 {index:03d} / {'교육 프로젝트' if years == 0 else '담당자'} / {2026 - max(years, 1)}.03~2026.03"
    location = LOCATIONS[index % len(LOCATIONS)][0]
    if variant % 3 == 0:
        parts = [
            intro,
            NOTICE,
            "",
            "기본정보",
            f"거주 희망지역 {location} / 연락처 미기재",
            "",
            "경력사항",
            work,
            "",
            "경력기술서",
            *project_lines,
            "",
            "학력 및 교육",
            education,
            "",
            "보유 역량",
            ", ".join(skills),
            "",
            "희망 근무조건",
            f"{location} / 주 5일 / 정규직 또는 계약직 협의",
            "",
            "자기소개",
            "맡은 범위를 기록하고 결과를 검증하는 방식으로 일했습니다. 실제 수행한 범위와 팀의 기여를 구분해 설명하겠습니다.",
        ]
    elif variant % 3 == 1:
        parts = [
            intro,
            NOTICE,
            "",
            "희망 근무",
            f"{location} / 주 3~5일 / 근무시간 협의",
            "",
            "나의 경력",
            work,
            "",
            "할 수 있는 업무",
            *project_lines,
            "",
            "교육 및 자격",
            education,
            "",
            "업무 도구",
            ", ".join(skills),
            "",
            "간단 자기소개",
            f"{project} 업무를 맡아 작업 순서를 지키고 완료 내용을 인수인계했습니다.",
        ]
    else:
        parts = [
            intro,
            NOTICE,
            "",
            "소개",
            f"{location}에서 {role} 업무를 희망합니다.",
            "",
            "관련 경험",
            work,
            *project_lines,
            "",
            "사용 가능한 도구",
            ", ".join(skills),
            "",
            "배운 내용",
            education,
            "",
            "일할 수 있는 조건",
            "평일 주간 협의 가능. 처음 맡는 업무는 안내받은 절차에 따라 확인하겠습니다.",
        ]
    if variant == 0:
        parts.extend(
            ["", "경험 범위", "상용 서비스 운영 경험은 없습니다. 교육용 프로젝트의 결과입니다."]
        )
    elif variant == 8:
        parts.extend(
            ["", "보완할 내용", "팀 리더의 최종 승인과 예산 집행은 직접 담당하지 않았습니다."]
        )
    return "\n".join(parts), skills, level


def build_resumes() -> list[dict]:
    resumes = []
    for family_index, family in enumerate(CAREER_FAMILIES):
        for variant in range(10):
            index = family_index * 10 + variant + 1
            text, skills, level = career_text(index, family, variant)
            style = ("saramin", "albamon", "daangn")[variant % 3]
            resumes.append(
                {
                    "id": f"synthetic-resume-{index:03d}",
                    "title": f"{family[0]} · {family[2][variant % 4]} · 가상 {index:03d}",
                    "role": family[0],
                    "experience_level": level,
                    "skills": skills,
                    "summary": f"{family[2][variant % 4]}와 {family[2][(variant + 1) % 4]}에서 역할과 성과를 구분한 가상 이력서입니다.",
                    "resume_text": text,
                    "source_type": "synthetic",
                    "source_urls": [SOURCES[style]],
                    "format_style": style,
                    "fixture_group": "matching-2026-10",
                }
            )
    return resumes


AI_PROFILES = [
    {
        "name": "문서검색 개발",
        "years": 4,
        "skills": ["Python", "LangGraph", "RAG", "PostgreSQL", "FastAPI", "Git"],
        "summary": "문서검색과 근거 제시를 중심으로 AI 오케스트레이션을 개발한 가상 경력입니다.",
        "evidence": [
            "Python과 FastAPI로 문서검색 API를 개발했습니다. 가상 사내 지식 문서 2,400건을 처리했습니다.",
            "LangGraph 상태 그래프와 도구 호출을 구현해 검색, 근거 검증, 사람 승인 단계를 연결했습니다.",
            "RAG 검색 결과와 답변 평가를 수행했습니다. 합성 질문 180개의 근거 일치율을 68%에서 86%로 개선했습니다.",
            "PostgreSQL 메타데이터를 설계하고 문서 버전과 검색 출처를 저장했습니다.",
            "AI 오케스트레이션 작업 흐름을 구현하고 Git으로 평가 기준과 실패 사례를 관리했습니다.",
        ],
        "limit": "클라우드 인프라 구축은 별도 담당자의 범위였습니다.",
    },
    {
        "name": "매장업무 자동화",
        "years": 2,
        "skills": ["n8n", "Excel", "재고 관리", "고객 응대", "문서화"],
        "summary": "매장 운영 경험에서 반복 작업을 자동화하는 역할로 전환한 가상 경력입니다.",
        "evidence": [
            "Excel 판매 데이터와 식자재 재고 관리 장부 360건을 정리했습니다.",
            "n8n 재고 관리 알림을 구성하고 발주 누락을 18건에서 5건으로 줄였습니다.",
            "고객 응대 문의를 분류하고 예약 안내 메시지를 연결했습니다. 일일 문의 45건을 처리했습니다.",
            "AI 오케스트레이션 작업 흐름을 운영하고 실패한 자동화 요청을 담당자에게 전달했습니다.",
            "반복 업무 절차를 문서화하고 신규 운영자 3명과 인수인계 테스트를 진행했습니다.",
        ],
        "limit": "Python 개발 경험은 없습니다. 노코드 설정과 운영 검증을 맡았습니다.",
    },
    {
        "name": "클라우드 실행플랫폼",
        "years": 6,
        "skills": ["Kubernetes", "Docker", "AWS", "Python", "Redis", "보안"],
        "summary": "여러 작업 실행기를 안정적으로 배포하고 장애를 복구한 가상 경력입니다.",
        "evidence": [
            "Kubernetes 작업 실행 환경을 운영하고 18개 작업의 자원 제한을 설정했습니다.",
            "Docker 이미지 배포를 자동화하고 AWS 장애 복구를 설계했습니다. 복구 시간을 35분에서 12분으로 줄였습니다.",
            "Python 운영 자동화와 Redis 작업 대기열을 구현해 중복 실행을 검증했습니다.",
            "AI 오케스트레이션 작업 흐름을 구현하고 도구 호출의 시간 제한과 재시도를 설계했습니다.",
            "접근 권한과 보안 이벤트를 점검하고 작업 실패 알림을 운영했습니다.",
        ],
        "limit": "디자인 제작과 고객상담 실무는 담당하지 않았습니다.",
    },
    {
        "name": "콘텐츠 승인화면",
        "years": 3,
        "skills": ["TypeScript", "React", "Figma", "API", "n8n", "콘텐츠"],
        "summary": "생성 작업을 검토하고 승인하는 화면과 콘텐츠 발행 흐름을 개발한 가상 경력입니다.",
        "evidence": [
            "TypeScript와 React로 승인 화면을 개발하고 API 생성 작업을 연결했습니다.",
            "Figma 제작 흐름을 설계하고 키보드 접근성 테스트 24개를 작성했습니다.",
            "n8n 발행 승인 단계를 구현하고 콘텐츠 메타데이터 420건을 정리했습니다.",
            "AI 오케스트레이션 작업 흐름을 구현해 초안 생성, 검토, 예약 발행을 연결했습니다.",
            "발행 오류 테스트를 작성해 중복 발행 사례를 9건에서 0건으로 줄였습니다.",
        ],
        "limit": "서버 데이터베이스 최적화는 다른 팀원이 담당했습니다.",
    },
    {
        "name": "금융 승인서비스",
        "years": 5,
        "skills": ["Java", "Spring", "PostgreSQL", "Docker", "SQL", "API"],
        "summary": "내부 승인과 기록 보존을 중심으로 AI 오케스트레이션을 붙인 가상 경력입니다.",
        "evidence": [
            "Java Spring 승인 API를 개발하고 사용자별 권한 검증 테스트 54개를 작성했습니다.",
            "PostgreSQL 업무 이력을 설계하고 SQL 정합성 검증으로 누락 기록을 23건에서 2건으로 줄였습니다.",
            "Docker 내부 서비스를 배포하고 승인 실패 재처리를 구현했습니다.",
            "AI 오케스트레이션 작업 흐름을 구현해 검토 도구와 최종 승인자를 연결했습니다.",
            "합성 신청 1,100건에서 승인 단계별 처리 시간을 측정하고 운영 절차를 문서화했습니다.",
        ],
        "limit": "LLM 모델 학습 경험은 없습니다. 외부 모델 호출과 승인 시스템 통합을 담당했습니다.",
    },
    {
        "name": "데이터 평가파이프라인",
        "years": 4,
        "skills": ["Python", "SQL", "Airflow", "Docker", "평가", "Git"],
        "summary": "AI 작업의 입력 품질과 평가 결과를 관리한 데이터 엔지니어 가상 경력입니다.",
        "evidence": [
            "Python과 SQL로 데이터 가공 파이프라인을 개발하고 평가 데이터 6,000건을 검증했습니다.",
            "Airflow 작업 의존성과 재시도를 설계하고 Docker 배치 작업을 배포했습니다.",
            "Python 평가 데이터 검증과 SQL 테스트 결과 분석을 수행했습니다.",
            "AI 오케스트레이션 작업 흐름을 구현하고 실패 사례를 분류해 데이터 품질 테스트 38개를 작성했습니다.",
            "Git 평가 기준을 관리하고 야간 배치 재처리 시간을 70분에서 42분으로 줄였습니다.",
        ],
        "limit": "프론트엔드 화면 개발은 담당하지 않았습니다.",
    },
    {
        "name": "센서 설비연결",
        "years": 3,
        "skills": ["Python", "MQTT", "Docker", "API", "안전 관리", "데이터 분석"],
        "summary": "설비 데이터를 수집해 점검 작업으로 연결하는 가상 경력입니다.",
        "evidence": [
            "Python으로 설비 데이터를 수집하고 MQTT 센서 이벤트를 처리했습니다.",
            "Docker 점검 서비스를 배포하고 API 장치 제어를 구현했습니다.",
            "안전 관리 점검 기록을 자동화하고 누락 데이터 검증을 수행했습니다.",
            "AI 오케스트레이션 작업 흐름을 구현해 이상 이벤트, 점검 요청, 담당자 승인을 연결했습니다.",
            "센서 42대의 합성 로그를 데이터 분석하고 잘못된 알림 비율을 16%에서 7%로 줄였습니다.",
        ],
        "limit": "실제 산업 장비의 인증이나 안전성 검증을 수행한 이력은 아닙니다.",
    },
    {
        "name": "문서 OCR 검토",
        "years": 2,
        "skills": ["Python", "OCR", "LangGraph", "Excel", "회계", "보안"],
        "summary": "증빙 추출 결과를 검토자에게 보내는 문서 자동화 가상 경력입니다.",
        "evidence": [
            "OCR 문서 정보와 전표 데이터를 추출하고 Python 문서 정합성을 검증했습니다.",
            "LangGraph 검토 승인 단계를 구현하고 AI 오케스트레이션 작업 흐름을 운영했습니다.",
            "Excel 회계 증빙 740건을 정리하고 Python 정산 검증으로 중복 전표 31건을 찾아냈습니다.",
            "개인정보 보안 규칙을 적용하고 민감 필드 마스킹 테스트를 작성했습니다.",
            "회계 오류 알림을 구현하고 검토자의 수정 기록을 다음 평가 자료로 정리했습니다.",
        ],
        "limit": "세무 신고와 법률 판단은 담당하지 않았습니다.",
    },
    {
        "name": "상담 오케스트레이션",
        "years": 3,
        "skills": ["TypeScript", "API", "Redis", "고객 응대", "영어", "n8n"],
        "summary": "고객 문의를 분류하고 담당자에게 전달하는 서비스 가상 경력입니다.",
        "evidence": [
            "TypeScript 상담 API를 개발하고 Redis 대화 상태를 저장했습니다.",
            "고객 응대 티켓 분류와 담당자 전달을 자동화했습니다. 가상 문의 900건을 검토했습니다.",
            "n8n 여행 일정 알림을 구현하고 API 예약 정보를 연결했습니다.",
            "영어 고객 응대 기록을 정리하고 상담 품질 테스트 65개를 작성했습니다.",
            "AI 오케스트레이션 작업 흐름을 구현해 상담 이관 누락을 13건에서 3건으로 줄였습니다.",
        ],
        "limit": "모델 학습이나 클라우드 인프라 구축은 직접 담당하지 않았습니다.",
    },
    {
        "name": "신입 평가실습",
        "years": 0,
        "skills": ["Python", "평가", "Git", "문서화"],
        "summary": "실무 운영 전 단계에서 작은 AI 오케스트레이션을 학습한 신입 가상 이력서입니다.",
        "evidence": [
            "교육 프로젝트에서 Python 평가 데이터 검증을 구현했습니다. 합성 질문 60개를 분류했습니다.",
            "AI 오케스트레이션 작업 흐름을 구현해 질문 입력, 도구 호출, 검토 출력 세 단계를 연결했습니다.",
            "Git 평가 기준을 관리하고 실패 사례 분류를 문서화했습니다.",
            "잘못된 입력 12개에 대한 테스트를 작성하고 예외 메시지를 개선했습니다.",
        ],
        "limit": "SQL 실무 경험은 없습니다. 상용 배포와 대규모 서비스 운영 경험도 없습니다.",
    },
]


def build_desktop_resumes() -> list[dict]:
    items = []
    for index, profile in enumerate(AI_PROFILES, 1):
        location = LOCATIONS[index - 1][0]
        year_label = f"경력 {profile['years']}년" if profile["years"] else "신입"
        text = "\n".join(
            [
                f"가상 AI 오케스트레이션 지원자 {index:02d}",
                f"희망직무: {profile['name']} / {year_label}",
                NOTICE,
                "",
                "기본정보",
                f"희망지역: {location} / 연락처: 미기재 / 입사 가능일: 협의",
                "",
                "핵심 소개",
                profile["summary"],
                "",
                "경력 및 프로젝트",
                f"가상 실습기업 별결{index:02d} / {2026 - max(profile['years'], 1)}.03~2026.03 / {profile['name']}",
                *profile["evidence"],
                "",
                "보유 역량",
                ", ".join(profile["skills"]),
                "",
                "학력 및 교육",
                f"가상 누리직업교육원 디지털 업무 과정 수료 / 프로젝트 실습 {160 + index * 20}시간",
                "",
                "자기소개",
                "도구가 수행한 결과를 확인하고 실패한 요청은 사람이 검토하도록 연결했습니다. 맡은 역할과 결과를 기록해 팀에 공유했습니다.",
                "",
                "경험 범위",
                profile["limit"],
                "",
                "희망 근무조건",
                "주 5일 또는 프로젝트 계약 협의 / 팀의 업무 방식에 맞춰 근무시간 협의",
            ]
        )
        items.append(
            {
                "id": f"desktop-ai-{index:02d}",
                "title": profile["name"],
                "role": "AI 오케스트레이션 " + profile["name"],
                "experience_level": "경력" if profile["years"] else "신입",
                "skills": profile["skills"],
                "summary": profile["summary"],
                "resume_text": text,
                "source_type": "synthetic",
                "source_urls": [SOURCES[("saramin", "albamon", "daangn")[(index - 1) % 3]]],
            }
        )
    return items


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_desktop_files(destination: Path, items: list[dict]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    index_lines = [
        "# AI 오케스트레이션 가상 이력서 10개",
        "",
        NOTICE,
        "",
        "모의지원 2단계의 이력서 업로드에서 PDF 또는 TXT 파일을 선택하세요.",
        "같은 번호의 PDF와 TXT에는 같은 이력서가 들어 있습니다. TXT는 UTF-8이며 직접 수정할 수 있습니다.",
        "같은 역할이라도 기술, 수행 범위, 경력이 달라 공고와 연결되는 개수와 위치가 달라집니다.",
        "10개 파일은 DB의 추가 이력서 200개와 별도인 업로드 실험용 자료입니다.",
        "",
    ]
    for index, item in enumerate(items, 1):
        filename = f"{index:02d}_{item['title'].replace(' ', '_')}_가상이력서.txt"
        (destination / filename).write_text(item["resume_text"] + "\n", encoding="utf-8-sig")
        index_lines.append(f"- {filename}: {item['summary']}")
    (destination / "사용안내.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop-dir", type=Path)
    args = parser.parse_args()
    jobs = build_jobs()
    resumes = build_resumes()
    desktop = build_desktop_resumes()
    write_json(EXAMPLES / "orchestration_job_postings.json", jobs)
    write_json(EXAMPLES / "synthetic_resumes.json", {"items": resumes})
    write_json(EXAMPLES / "desktop_ai_resumes.json", {"items": desktop})
    manifest = {
        "version": 1,
        "notice": NOTICE,
        "added_job_count": len(jobs),
        "added_db_resume_count": len(resumes),
        "separate_desktop_resume_count": len(desktop),
        "unique_job_content_count": len({fingerprint(item["description"]) for item in jobs}),
        "unique_resume_content_count": len({fingerprint(item["resume_text"]) for item in resumes}),
        "role_family_count": len({item["role"] for item in resumes}),
        "format_sources": SOURCES,
        "files": {
            name: hashlib.sha256((EXAMPLES / name).read_bytes()).hexdigest()
            for name in (
                "orchestration_job_postings.json",
                "synthetic_resumes.json",
                "desktop_ai_resumes.json",
            )
        },
    }
    write_json(EXAMPLES / "matching_fixture_manifest.json", manifest)
    if args.desktop_dir:
        write_desktop_files(args.desktop_dir, desktop)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
