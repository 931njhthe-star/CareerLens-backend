# 비회원 분석과 로그인 후 결과 연결 · 1.7.1

비회원도 이력서 파일을 업로드하고 공개 DB 공고를 선택한 뒤 보완 답변으로 실제 분석을 완료할 수 있습니다. 분석 엔진과 회원 점수 기준은 같습니다. 결과 본문·점수는 서버에 보관하며 로그인/회원가입 후 명시적인 claim API에서만 반환합니다.

## 순서와 응답

1. `GET /auth/session`으로 익명 세션 쿠키와 CSRF 토큰을 받습니다.
2. `POST /guest/resume/upload`: multipart `file`을 업로드합니다. 기존 TXT/PDF/DOCX 파서와 10MiB, 추출문 50,000자, PDF 50페이지 제한을 사용합니다.
3. `PUT /guest/career-target`: 회원 API와 같은 `role_id`, 선택적인 `role`, `focus`로 희망 직무를 선택합니다.
4. 공개 목록에서 선택한 공고 ID로 `POST /guest/job-postings/{posting_id}/select`를 호출합니다. 서버가 공개 DB 행을 다시 조회합니다. 수동 비공개 공고는 로그인 여부와 무관하게 이 경로에서 접근할 수 없습니다.
5. 반환된 질문의 ID로 `POST /guest/analysis`에 `{ "answers": {} }`를 보냅니다. 실제 분석이 완료되어야 `completed`와 `report_locked`가 true가 됩니다.
6. 로그인·회원가입·OAuth 완료 후 새 CSRF 토큰으로 `POST /guest/claim`을 호출합니다. 이 시점에만 일반 회원 Workspace 응답과 보고서를 받습니다.

`GET /guest/workspace`로 새로고침 상태를 복원하고, `DELETE /guest/workspace`로 즉시 폐기합니다. 최초 조회와 만료 후 조회는 빈 상태를 반환하며 임시 DB 행을 새로 만들지 않습니다. 세션에 있던 자료가 만료·소실된 경우에는 `expired: true`를 반환합니다. 이 값은 OAuth 복귀처럼 새 페이지에서도 만료 안내와 재업로드 화면을 표시하고 기존 계정의 다른 보고서로 오인시키지 않도록 사용합니다. 새 방문자와 명시적 폐기 응답은 false입니다.

claim 이외 비회원 응답은 다음 허용 목록으로 제한합니다. `resume_text`, `job_text`, `answers`, `report`, `preparation`, 점수는 응답·숨김 HTML에 넣지 않습니다.

```json
{
  "draft": {
    "resume_attached": true,
    "filename": "이력서.txt",
    "company": "가상 예시 기업",
    "role": "백엔드 개발자",
    "analysis_mode": "job_posting",
    "career_target": null,
    "selected_posting_id": "example-id"
  },
  "questions": [],
  "report_locked": true,
  "completed": true,
  "expired": false,
  "expires_at": "2026-10-08T06:30:00+00:00"
}
```

## 저장과 만료

- 원본 업로드 바이트는 요청 처리 메모리에서만 읽고 파일로 저장하지 않습니다. 파싱한 이력서·답변·보고서는 별도 `guest_workspaces` 테이블에 저장합니다. 기존 SQLite/PostgreSQL 어댑터를 사용합니다.
- 비회원 multipart 파일 스트림은 메모리 버퍼를 사용하고, 제공된 Waitress 실행기는 11MiB 요청 상한보다 높은 12MiB 입력 스풀 임계값을 적용합니다. 배포 시 외부 프록시·대체 WSGI 서버도 요청 본문을 디스크에 버퍼링하지 않도록 설정해야 합니다.
- HttpOnly 서명 쿠키에 무작위 비회원 ID만 저장합니다. 본문·보고서는 쿠키에도 넣지 않습니다. 클라이언트가 보내는 임의 guest/user ID로 소유권을 선택할 수 없습니다.
- 첫 유효 업로드로 만든 만료 시각은 **30분으로 고정**합니다. 파일 교체·직무 변경·분석·로그인으로 연장하지 않습니다. 만료 시 모든 읽기·수정·claim 접근을 차단합니다.
- 실행 중인 서버의 독립 정리 스레드가 30초마다 만료 행을 SQL DELETE합니다. 브라우저를 닫아도 계속 동작합니다. 시작 및 조회 시에도 만료 행을 정리합니다. 서버가 멈춘 동안 지난 자료는 다음 서버 시작 시 삭제합니다. 외부 DB 백업의 보관 정책은 운영자가 별도로 정해야 합니다.
- claim은 트랜잭션에서 완료된 임시 초안을 **회원의 현재 작업 공간으로 교체**하고 비회원 행을 삭제합니다. 미완료·만료·소실된 자료는 회원 공간을 수정하지 않습니다. 따라서 로그인 화면은 방금 만든 비회원 분석을 현재 결과로 연결한다는 의미를 설명해야 합니다.
- 분석 중 폐기·만료·claim 또는 입력 변경이 발생하면 revision 조건부 UPDATE가 늦은 쓰기를 거부합니다. 분석 작업은 임시 행을 다시 INSERT하지 않습니다.

## 오류와 요청 제한

기존 회원 경로의 인증 요구는 그대로입니다. 비회원 변경 요청도 같은 CSRF·Origin 검사를 적용합니다. claim은 유효한 회원 세션이 추가로 필요합니다. 로그인·가입·OAuth의 세션 회전은 현재 비회원 ID를 보존합니다.

| 상태 | 코드 | 처리 |
| --- | --- | --- |
| 401 | authentication_required | claim은 로그인 필요 |
| 403 | csrf_invalid / origin_invalid | 새 CSRF 토큰 확인 |
| 404 | guest_missing | claim할 세션 자료 없음 |
| 409 | guest_incomplete | 분석 미완료 |
| 409 | guest_stale | 동시 입력 변경, 최신 상태로 재시도 |
| 410 | guest_expired | 만료·폐기·이미 연결한 자료, 새로 업로드 |
| 429 | rate_limited | 요청 제한 |

30분 단위 세션 제한은 업로드 10회, 편집/공고 선택 합계 60회, 분석 6회입니다. 쿠키를 지우는 반복 요청은 소켓 IP별 넓은 한도(각 40/600/60회)로 추가 제한합니다. 프록시를 공유하는 여러 사용자의 정상 요청은 각 세션별로 구분하며 임의 `X-Forwarded-For`는 신뢰하지 않습니다. 잘못된 입력도 시도 횟수에 포함합니다.
