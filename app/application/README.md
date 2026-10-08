# Application 계층

HTTP 요청과 비동기 작업을 실제 업무 흐름으로 연결하는 위치입니다.
분석 실행 조정, 사용자 승인 확인, 그래프 실행, 결과 저장과 트랜잭션 경계를 이 계층에서 조합합니다.
현재 workspace.py가 이력서·공고·질문·모의지원 저장 흐름을 조립하고 auth.py가 인증 서비스·미들웨어를 조립합니다. 분석은 외부 호출 없는 모듈 규칙을 직접 실행합니다.

## 호출 규칙

- `api`와 `workers`는 application의 유스케이스를 호출합니다.
- application은 모듈의 서비스와 저장소 인터페이스를 사용하고, 필요할 때 agent 그래프를 실행합니다.
- application의 조립 지점에서 DB·저장소·LLM 등의 구현을 생성해 서비스·그래프에 주입합니다.
- agent의 노드·도구는 modules의 규칙, retrieval, integrations를 호출합니다.
- modules의 규칙·서비스는 application, agent, API, 제공자 구현을 import하지 않습니다.
- agent는 application의 실행 조정 함수를 import하지 않습니다.

분석 실행 조정 파일이 그래프를 호출하고 그래프 노드가 그 조정 파일을 다시 호출하는 구조를 금지합니다.
예를 들어 `application/analysis.py`는 그래프를 실행하고, 그래프 노드는 `modules/analysis/matching`, `validation`, `reporting`의 규칙을 호출합니다.
해당 규칙은 입력과 결과만 다루며 그래프 실행 방식과 HTTP 요청을 알지 않습니다.

일반 인증·CRUD는 application에서 모듈 서비스를 조합해 처리하고, 전체 흐름을 LangGraph에 넣지 않습니다.

## 팀원별 실행 설정

`run.py`가 각자의 `.env`를 읽고 app factory가 DATABASE_URL을 해석합니다. 명시적 테스트 DATABASE 경로는 환경 DB 주소보다 우선합니다. `DATA_DIR`/`MAIL_OUTBOX`는 원격 DB와 독립된 로컬 개인 파일 경로입니다. 저장소 구현은 동일 인터페이스로 SQLite/PostgreSQL을 처리하며, 공유본에는 개인 데이터나 마이그레이션 파일을 넣지 않습니다.
