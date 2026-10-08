# 희망 직무 선택과 분석 준비

새 화면 흐름은 이력서 → 희망 직무 선택 → 눈 모션 분석 → 모의지원 보완 질문 → 보고서입니다. 화면의 두 번째 단계 이름은 `채용 공고`이지만 회사나 공고 본문을 입력하거나 실제 공고에 매칭하지 않습니다. 기존 `/job`과 카탈로그 API는 저장된 자료와 기존 클라이언트 호환을 위해 유지합니다.

## API 1.4.1

모든 경로 앞에 `/api/v1`을 붙입니다. 로그인 세션이 필요하고 PUT·POST에는 `X-CSRF-Token`도 필요합니다.

| 요청 | 입력 | 결과 |
| --- | --- | --- |
| `GET /career-roles` | 없음 | `items: [{id, label, description}]` |
| `PUT /career-target` | `{role_id, role?, focus?}` | 현재 작업·준비 상태. `custom`은 `role` 1~120자 필요. `focus`는 최대 1,000자 |
| `POST /preparation` | `{stage, fingerprint?}` | 실제 수행한 단계만 `complete`로 저장한 작업·준비 상태 |
| `POST /analysis` | `{answers: {질문ID: 답변}}` | 현재 준비가 모두 완료된 경우 보완 답변을 반영한 최종 `report` |

`/career-target`은 `draft.analysis_mode = "desired_role"`, `draft.career_target = {role_id, label, focus, reference_source:"internal_role_reference"}`를 저장합니다. `draft.role`은 선택한 직무 이름이고 `company`와 `job_text`는 빈 문자열입니다. 가상의 기업이나 공고를 자동으로 만들지 않습니다.

응답의 `preparation`과 `draft.preparation`은 같은 준비 상태를 담습니다.

```json
{
  "fingerprint": "현재 이력서·희망 직무·참고 기준의 SHA256",
  "complete": false,
  "stages": [
    {"id": "resume", "status": "complete", "detail": "이력서 문장·수행 표현 확인"},
    {"id": "role", "status": "pending", "detail": "분석 대기"},
    {"id": "report", "status": "pending", "detail": "분석 대기"}
  ]
}
```

순서대로 `resume`, `role`, `report`를 호출합니다. 프론트엔드는 현재 응답의 fingerprint를 다음 요청마다 보냅니다.

1. `resume`: 저장한 이력서에서 문장, 수행 표현, 수치 표현을 실제 추출합니다. `resume_evidence`에 집계를 담습니다. 경력의 진위나 숙련도를 검증한다는 의미는 아닙니다.
2. `role`: 선택한 직무의 내부 참고 항목을 불러와 `role_reference`에 담습니다.
3. `report`: LangGraph와 기존 근거 분석기를 실행하고 `preliminary_report`, `questions`를 만듭니다. 입력한 관심 분야가 있으면 마지막 보완 질문에 반영합니다. 이 단계는 최종 `draft.report`를 쓰지 않습니다.

각 응답이 성공적으로 반환한 `complete`만 해당 분야의 100%로 표시합니다. 서버는 경과 시간으로 진행률을 추정하지 않습니다. 실패한 단계는 pending 상태로 남으며 성공한 단계 재호출은 실제 분석을 중복 실행하지 않습니다. 서버 완료를 확인하기 전 자동 이동하지 않습니다.

입력을 바꾸면 준비·답변·최종 보고서를 무효화합니다. 오래된 fingerprint 또는 분석 중 다른 탭에서 입력 수정/작업 삭제가 발생하면 `409 preparation_stale`을 반환합니다. 프론트엔드는 작업을 다시 불러오고 현재 입력으로 새 분석을 시작합니다. 저장소는 이전 전체 작업 내용과 비교하는 조건부 갱신으로 늦은 결과가 새 내용을 덮어쓰는 것을 막습니다. 순서를 건너뛴 요청은 400입니다. 로그인 해제는 401, CSRF 오류는 403입니다.

## 기준과 프롬프트 수정

`data/knowledge/career-roles.json`에서 직무 목록·설명·참고 항목을 수정합니다. 직접 입력 직무에는 공통 경험 항목을 사용합니다. 이 파일은 자체 작성한 연습용 자료이며 실제 공고·공식 직업 표준·실시간 API 자료가 아닙니다. 파일 내용이 달라지면 fingerprint가 달라져 재분석이 필요합니다.

기존 세 가지 근거 점수(직무 경험 연결 70, 수행 맥락 20, 수치로 표현한 결과·규모 10)를 유지하며 새로운 숙련도/합격률 계산을 도입하지 않습니다. 관심 분야 입력 자체는 점수를 올리지 않습니다. 희망 직무 보고서에는 `assessment_context:"desired_role"`, `reference_source:"internal_role_reference"`가 붙으며 `job_matches`를 생성하거나 카탈로그 매칭 서비스를 호출하지 않습니다.

기본 rules 모드는 외부 AI 호출 없이 실행됩니다. `.env`에서 명시적으로 설정한 LLM 모드의 코칭은 기존 제한 시간·재시도·규칙 분석 fallback을 그대로 적용합니다. 코칭 실패 후 규칙 결과가 완성된 경우는 성공한 로컬 분석이며 `report.agent.fallback_used`와 오류 코드가 그 사실을 표시합니다. `app/agent/prompts/coaching.md`에는 내부 직무 기준을 실제 공고로 설명하지 않도록 구분 지침이 있습니다. 코칭은 근거 점수를 바꾸지 않습니다.

## 검증

`tests/integration/test_career_preparation.py`는 인증·CSRF, 단계 순서, 서버 완료 조건, 중복 요청, 실패/재시도, 변경 시 초기화, 오래된 분석 저장 방지, 사용자 격리, 재시작 복원, 기존 공고 흐름 전환을 검증합니다. 외부 DB·LLM 제공자 호출은 이 로컬 테스트의 검증 범위에 포함하지 않습니다.
