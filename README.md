# CareerLens Backend — 팀 공유본

팀원이 자신의 `.env`와 데이터베이스를 연결해 실행하는 Python 백엔드입니다. 회원가입·로그인, 채용공고 탐색·저장, 이력서와 공고 비교, 보완 질문, 모의지원 결과를 제공합니다. 기존 폴더 구조와 규칙 분석 위에 LangGraph 실행 및 선택적 LLM 코칭을 추가했습니다.

현재 화면의 분석 흐름은 **이력서 → 희망 직무 선택 → DB 공고 선택 → 분석 → 보고서**입니다. 공고의 **모의지원 결과 확인**을 누르면 추가 질문 화면 없이 빈 보완 답변으로 최종 분석을 요청합니다. 비회원도 실제 분석을 완료할 수 있으며 보고서는 로그인·회원가입 후 현재 계정 작업 공간에 연결하여 확인합니다. 비회원 이력서·답변·보고서는 최초 업로드부터 30분만 임시 보관합니다. [비회원 API와 보관 정책](docs/api/guest-analysis.md)을 확인하세요. 기존 보완 질문과 [직무 참고 기준 분석 API](docs/api/career-preparation.md)는 호환을 위해 유지합니다.

개인 `.env`, API 키, 기존 사용자 정보·DB 파일·메일·업로드 파일은 포함하지 않습니다. 개인 대시보드와 DB 덤프는 공유 대상에 포함하지 않습니다. DB 초기화와 공통 스키마·저장소 코드는 공유 대상입니다. 실행에 필요한 공통 DB 연결·저장소 코드는 제공하며, 각자의 DB에 필요한 테이블을 처음 실행할 때 생성합니다.

## 실행

Python 3.12에서 백엔드 저장소 안에서 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# .env를 열어 본인의 DB·OAuth·SMTP 설정을 입력합니다.
.\.venv\Scripts\python.exe run.py
```

`run.py`는 이 저장소의 `.env`를 읽습니다. 이미 설정된 프로세스 환경변수는 덮어쓰지 않습니다. 기본 API 주소는 `http://127.0.0.1:5101/api/v1`이며 `--port` 또는 `BACKEND_PORT`로 바꿀 수 있습니다. 기본 바인딩은 로컬 loopback이며, 배포 시 `--host` 또는 `BACKEND_HOST`로 지정할 수 있습니다.

화면은 별도의 CareerLens-frontend 저장소를 실행합니다. 프론트엔드의 `BACKEND_URL`을 이 백엔드 주소로 설정하고, 백엔드 `PUBLIC_ORIGIN`을 실제 브라우저 주소와 맞춥니다. 기본 브라우저 주소는 `http://127.0.0.1:5100`입니다. 화면 프록시를 통한 동일 출처 세션·CSRF 흐름을 사용합니다.

## 각자의 DB 연결

`.env`의 `DATABASE_URL`만 바꾸면 같은 로그인·모의지원 API를 사용할 수 있습니다.

| 설정 | 동작 |
| --- | --- |
| 빈 값 | 새로운 `.runtime/careerlens.sqlite3` 파일을 생성 |
| `sqlite:///./.runtime/team.sqlite3` | 저장소 루트 기준 SQLite 파일을 사용 |
| `postgresql://USER:PASSWORD@HOST:5432/postgres?sslmode=require` | 본인 PostgreSQL DB에 연결 |

Supabase는 필수가 아닙니다. 로컬 SQLite 또는 직접 운영/호스팅하는 PostgreSQL을 사용할 수 있습니다. 관리형 PostgreSQL을 사용해도 프로젝트 REST URL이나 프론트엔드용 API 키가 아닌 PostgreSQL 연결 URI를 입력합니다. 비밀번호의 특수문자는 URI 규칙대로 인코딩하며 `postgres://` 형식도 허용합니다.

PostgreSQL 테이블은 고정된 `careerlens` 스키마에 생성합니다. 연결 계정에는 해당 스키마·테이블을 생성하고 읽고 쓸 권한이 필요합니다. 개인 테이블을 자동 공개하는 설정은 사용하지 않습니다. 외부 호스트는 `sslmode`를 생략하면 `require`가 적용되며 psycopg의 자동 prepared statement는 끕니다.

이 프로그램의 이메일·OAuth 인증과 자료 저장을 각자의 DB에 연결하는 구성입니다. 실제 원격 DB 접속과 OAuth 제공자 로그인은 각자의 유효한 연결 정보로 확인해야 합니다.

`DATA_DIR`은 DB와 별개의 로컬 개인 파일 위치이며 빈 값이면 `.runtime`입니다. 세션 서명 키는 여기에 `session.key`로 생성하거나 `CAREERLENS_SECRET_KEY`로 직접 지정합니다. SMTP를 설정하지 않으면 재설정 메일도 이 디렉터리의 `mail`에 저장합니다. PostgreSQL 주소를 파일 경로로 취급하지 않습니다.

## 기능과 제한

- 이메일 회원가입·로그인·로그아웃·비밀번호 재설정과 설정된 Google/GitHub/LinkedIn 로그인.
- 이력서 TXT·PDF·DOCX 추출 및 본문 확인·수정, 회사·직무·공고 입력.
- 채용공고 목록·상세·검색·조건 필터·정렬·페이지 이동, 계정별 북마크, 본인 공고 등록·수정·삭제.
- 교육용 가상 공고 600개와 DB에 저장되는 합성 이력서 220개를 제공합니다. 공고에는 업무·요건·보상·근무조건·전형을, 이력서에는 자기소개·경력·프로젝트·강점과 보완점을 포함합니다. 별도 업로드 이력서 40개(AI 관련 30개·다른 직무 10개)는 PDF/TXT로 제공합니다. 기존 공고 ID와 사용자 자료를 보존합니다. [공고 작성 범위](docs/references/expanded-job-catalog.md)와 [이력서 작성 범위](docs/matching-synthetic-data.md)를 확인하세요.
- 최대 3개 보완 질문, 원문 근거·보완 우선순위·면접 질문·모의 회신 보고서.
- 이전 공고 입력 방식의 보고서는 전체 공고별 점수와 60점 이상 연결 대상을 포함합니다. 새 희망 직무 보고서에서는 이 매칭을 실행하지 않습니다. [기존 매칭 API와 점수 기준](docs/api/job-matching.md)을 확인하세요.
- 로그인 사용자별 작업 저장, 입력 변경 시 이전 답변·결과 무효화, 내 자료 삭제.
- 비회원 파일 업로드·공고 분석, 로그인 전 결과 잠금, 30분 고정 만료와 서버 자동 삭제, 인증 후 단일 claim으로 결과 연결.
- 기본 분석은 외부 AI 호출 없는 규칙 모드입니다. 실제 LangGraph가 검색·규칙 분석을 실행하고, 선택적 LLM 모드에서는 근거 검증을 통과한 작성 조언을 별도로 제공합니다. 기존 점수 계산은 그대로 유지합니다.

실제 기업 지원·채용 회신·지원자 순위 예측은 제공하지 않습니다. 현재 공고 카탈로그는 가상 예시와 사용자 직접 입력이며 실시간 외부 채용 API 연동은 아직 없습니다.

파일은 10MB, PDF는 50페이지, 이력서·공고는 40~50,000자, 회사·직무는 1~120자, 보완 답변은 질문당 8,000자까지 지원합니다. 스캔 PDF에는 OCR이 필요합니다. 원본 업로드 파일은 저장하지 않고 추출 본문만 사용자의 DB에 저장합니다.

OAuth는 각자 등록한 앱의 CLIENT_ID/CLIENT_SECRET을 사용합니다. 비어 있으면 이메일 가입·로그인으로 실행할 수 있습니다. 실제 메일은 각자 SMTP를 설정해야 발송하며, 기본값은 로컬 메일 파일입니다. 자세한 흐름은 [인증 안내](docs/api/auth.md)를 참고하세요.

## 프롬프트와 선택적 LLM

기본 `.env`의 `CAREERLENS_ANALYSIS_MODE=rules`에서는 키 없이 실행됩니다. 선택적으로 `llm` 모드, 본인의 `OPENAI_API_KEY`, `CAREERLENS_LLM_MODEL`을 지정하고 서버를 다시 실행하면 코칭을 추가합니다. 이 모드에서는 이력서·공고·답변의 일부 발췌를 지정한 제공자에 보냅니다. 실제 제공자 연결과 품질은 본인 환경에서 별도 검증해야 합니다.

`app/agent/prompts/coaching.md`에서 문구를 고치고, 같은 폴더의 `registry.json`에서 프롬프트 추가·선택·비활성·버전과 재시도 한도를 관리합니다. 다음 분석부터 파일 수정이 반영됩니다. 검색 안내는 `data/knowledge/policies/career-guidance.json`에서 고칠 수 있습니다.

현재 검색은 키워드 기반이며 임베딩·벡터 DB·영속 에이전트 기억은 아직 없습니다. 모델 호출/검증 실패 시 최대 1회 재시도 후 기존 규칙 보고서를 반환합니다. 자세한 [그래프 구조와 편집 방법](docs/architecture/agent-evolution.md), [프로젝트 1·2 평가 기준별 적용 현황](docs/evaluations/project-2-coverage.md)을 확인하세요.

## 구조와 계약

| 경로 | 책임 |
| --- | --- |
| `app/api/v1/routes` | 인증·공고·작업 흐름 HTTP API |
| `app/application` | 인증·분석·저장 유스케이스 조립 |
| `app/core/config.py` | DB URL과 로컬 파일 위치 설정 |
| `app/modules` | 정규화·요구사항·근거 비교·보고서·인증 규칙 |
| `app/agent` | LangGraph·타입 상태·프롬프트·검증·재시도 |
| `app/retrieval/search` | 자체 작성 안내의 키워드 검색 |
| `app/infrastructure/database` | SQLite/PostgreSQL 공통 연결·저장소 코드 |
| `app/integrations` | 문서 추출·OAuth·메일·선택적 LLM 어댑터 |
| `data/examples` | 합성 이력서·공고 |
| `data/knowledge/policies` | 출처가 구분된 자체 작성 안내 |
| `contracts/openapi/v1/openapi.json` | 현재 구현 계약 원본 1.7.1 |
| `contracts/openapi/v*` | 프론트엔드 동기화용 버전별 명세·해시 manifest |

프론트엔드는 [현재 계약](contracts/openapi/v1/openapi.json)의 `/auth/*`, `/workspace`, `/resume`, `/job`, `/questions`, `/analysis`, `/job-postings`, `/job-matches` 등을 사용합니다. 자세한 [계약 전달 절차](docs/api/contract-workflow.md)를 따릅니다. 새 기능은 기존 책임 위치에 추가했고 `workers`와 일정 등 아직 구현하지 않은 폴더는 확장 공간으로 유지합니다. GitHub 공유 브랜치는 `sub-main/withandwithout`입니다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/evaluate-agent.py
```

기존 분석·문서 추출·인증·작업 흐름·DB 설정에 공고 기능과 에이전트 오류 경로 시험을 추가했습니다. 기본 테스트는 임시 SQLite와 모의 제공자를 사용합니다. `evaluations/results/agent-baseline-v1.json`은 합성 오류 주입 결과이며 실제 LLM 성능이나 실제 채용 적합성의 측정값이 아닙니다. PostgreSQL·OAuth·LLM 실제 연결은 자신의 설정으로 별도 확인합니다. `.env`, `.runtime`, DB 파일, 키, 재설정 메일을 커밋하지 마세요.

## 배포 준비

특정 클라우드 업체에 종속되지 않습니다. 실행 주소·포트·환경변수·DB 영속 저장과 HTTPS 설정은 [배포 안내](infra/deploy/README.md)를 확인하세요. 실제 배포는 아직 수행하지 않았습니다.
