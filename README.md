# CareerLens Backend — 팀 공유본

팀원이 자신의 `.env`와 데이터베이스를 연결해 실행하는 Python 백엔드입니다. 회원가입·로그인부터 이력서, 채용공고, 보완 질문, 모의지원 결과까지 API 계약 1.1.0의 전체 흐름을 제공합니다.

개인 `.env`, API 키, 기존 사용자 정보·DB 파일·메일·업로드 파일은 포함하지 않습니다. 대시보드와 마이그레이션 파일도 공유 대상에 포함하지 않았습니다. 실행에 필요한 공통 DB 연결·저장소 코드는 제공하며, 각자의 DB에 필요한 테이블을 처음 실행할 때 생성합니다.

## 실행

Python 3.12에서 백엔드 저장소 안에서 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# .env를 열어 본인의 DB·OAuth·SMTP 설정을 입력합니다.
.\.venv\Scripts\python.exe run.py
```

`run.py`는 이 저장소의 `.env`를 읽습니다. 이미 설정된 프로세스 환경변수는 덮어쓰지 않습니다. 기본 API 주소는 `http://127.0.0.1:5101/api/v1`이며 `--port` 또는 `BACKEND_PORT`로 바꿀 수 있습니다. 서버는 로컬 loopback에 바인딩합니다.

화면은 별도의 CareerLens-frontend 저장소를 실행합니다. 프론트엔드의 `BACKEND_URL`을 이 백엔드 주소로 설정하고, 백엔드 `PUBLIC_ORIGIN`을 실제 브라우저 주소와 맞춥니다. 기본 브라우저 주소는 `http://127.0.0.1:5100`입니다. 화면 프록시를 통한 동일 출처 세션·CSRF 흐름을 사용합니다.

## 각자의 DB 연결

`.env`의 `DATABASE_URL`만 바꾸면 같은 로그인·모의지원 API를 사용할 수 있습니다.

| 설정 | 동작 |
| --- | --- |
| 빈 값 | 새로운 `.runtime/careerlens.sqlite3` 파일을 생성 |
| `sqlite:///./.runtime/team.sqlite3` | 저장소 루트 기준 SQLite 파일을 사용 |
| `postgresql://USER:PASSWORD@HOST:5432/postgres?sslmode=require` | 본인 PostgreSQL DB에 연결 |

Supabase를 사용하는 경우 프로젝트 Connect 메뉴의 **PostgreSQL 연결 URI**를 사용합니다. 네트워크에 맞게 direct connection 또는 session pooler 주소를 선택합니다. Supabase 프로젝트 URL·anon key·service-role REST key는 이 `DATABASE_URL`의 대체값이 아닙니다. 비밀번호의 특수문자는 URI 규칙대로 인코딩하세요. `postgres://` 형식도 허용합니다.

연결 문자열 선택은 [Supabase 공식 PostgreSQL 연결 안내](https://supabase.com/docs/guides/database/connecting-to-postgres)를 참고하세요.

PostgreSQL 테이블은 고정된 `careerlens` 스키마에 생성합니다. 연결 계정에는 해당 스키마·테이블을 생성하고 읽고 쓸 권한이 필요합니다. Supabase Data API의 exposed schemas에 `careerlens`를 추가하지 마세요. 기본 `public` 스키마에 사용자 자료를 생성하지 않습니다. 외부 호스트는 `sslmode`를 생략하면 `require`가 적용되며 psycopg의 자동 prepared statement는 끕니다.

Supabase Auth나 REST API를 대신 구현한 것은 아닙니다. 이 프로그램의 이메일·OAuth 인증과 자료 저장을 각자의 PostgreSQL DB에 연결하는 구성입니다. 실제 원격 DB 접속과 OAuth 제공자 로그인은 각자의 유효한 연결 정보로 확인해야 합니다.

`DATA_DIR`은 DB와 별개의 로컬 개인 파일 위치이며 빈 값이면 `.runtime`입니다. 세션 서명 키는 여기에 `session.key`로 생성하거나 `CAREERLENS_SECRET_KEY`로 직접 지정합니다. SMTP를 설정하지 않으면 재설정 메일도 이 디렉터리의 `mail`에 저장합니다. PostgreSQL 주소를 파일 경로로 취급하지 않습니다.

## 기능과 제한

- 이메일 회원가입·로그인·로그아웃·비밀번호 재설정과 설정된 Google/GitHub/LinkedIn 로그인.
- 이력서 TXT·PDF·DOCX 추출 및 본문 확인·수정, 회사·직무·공고 입력.
- 최대 3개 보완 질문, 원문 근거·보완 우선순위·면접 질문·모의 회신 보고서.
- 로그인 사용자별 작업 저장, 입력 변경 시 이전 답변·결과 무효화, 내 자료 삭제.
- 외부 AI 호출 없는 로컬 규칙 기반 분석. 실제 기업 지원·채용 회신·지원자 순위 예측은 제공하지 않습니다.

파일은 10MB, PDF는 50페이지, 이력서·공고는 40~50,000자, 회사·직무는 1~120자, 보완 답변은 질문당 8,000자까지 지원합니다. 스캔 PDF에는 OCR이 필요합니다. 원본 업로드 파일은 저장하지 않고 추출 본문만 사용자의 DB에 저장합니다.

OAuth는 각자 등록한 앱의 CLIENT_ID/CLIENT_SECRET을 사용합니다. 비어 있으면 이메일 가입·로그인으로 실행할 수 있습니다. 실제 메일은 각자 SMTP를 설정해야 발송하며, 기본값은 로컬 메일 파일입니다. 자세한 흐름은 [인증 안내](docs/api/auth.md)를 참고하세요.

## 구조와 계약

| 경로 | 책임 |
| --- | --- |
| `app/api/v1/routes` | 인증·작업 흐름 HTTP API |
| `app/application` | 인증·분석·저장 유스케이스 조립 |
| `app/core/config.py` | DB URL과 로컬 파일 위치 설정 |
| `app/modules` | 정규화·요구사항·근거 비교·보고서·인증 규칙 |
| `app/infrastructure/database` | SQLite/PostgreSQL 공통 연결·저장소 코드 |
| `app/integrations` | 문서 추출·OAuth·메일 어댑터 |
| `data/examples` | 합성 이력서·공고 |
| `contracts/openapi/v1/openapi.json` | 현재 구현 계약 원본 1.1.0 |
| `contracts/openapi/v1.1.0` | 프론트엔드 동기화용 명세·해시 manifest |

프론트엔드는 [계약 1.1.0](contracts/openapi/v1.1.0/openapi.json)의 `/auth/*`, `/workspace`, `/resume`, `/job`, `/questions`, `/analysis` 등을 사용합니다. 자세한 [계약 전달 절차](docs/api/contract-workflow.md)를 따릅니다. `agent`, `retrieval`, `workers` 등의 빈 폴더는 원래 설계의 확장 공간으로 유지합니다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

기존 분석·문서 추출 36개 테스트와 인증·작업 흐름·DB 설정 테스트를 포함합니다. 기본 테스트는 임시 SQLite와 모의 PostgreSQL 연결 경계로 개인 데이터에 접근하지 않습니다. 실제 Supabase/PostgreSQL 접속 여부는 자신의 설정으로 별도 확인합니다. `.env`, `.runtime`, DB 파일, 키, 재설정 메일을 커밋하지 마세요.
