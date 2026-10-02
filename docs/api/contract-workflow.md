# API 명세 전달 절차

백엔드 API의 요청·응답 계약 원본은 `contracts/openapi/v1/openapi.json`입니다.
현재 Flask 구현의 라우트·입력 검증·반환 구조를 기준으로 관리하는 OpenAPI 3.1 문서이며, 서버에서 자동 생성하는 명세는 아닙니다. 라우트를 바꿀 때 이 원본도 함께 수정하고 테스트와 대조합니다.
현재 계약 버전 1.1.0은 인증 8개와 작업 흐름 9개, 총 17개 HTTP 동작을 포함합니다. 1.0.0 작업 흐름 계약은 이전 릴리스로 보존합니다.

## 백엔드에서 릴리스 산출물 만들기

백엔드 저장소에서 다음 명령을 실행합니다.

```powershell
pwsh -File scripts/export-api-contract.ps1 -Source contracts/openapi/v1/openapi.json -Version 1.1.0
```

도구는 OpenAPI 3.x 기본 구조와 `info.version`을 확인한 뒤 다음 파일을 생성합니다.

```text
contracts/openapi/v1.1.0/
├── openapi.json
└── manifest.json
```

manifest에는 계약 버전과 OpenAPI JSON의 SHA-256 해시가 들어갑니다.
같은 버전에 다른 내용이 들어오면 덮어쓰지 않습니다. 계약이 바뀌면 버전을 올려 새 산출물을 만듭니다.
이 도구는 기본 구조·버전·무결성을 검사합니다. 별도로 구현된 경로·메서드가 명세에 있는지, 요청 제한·응답 상태·스키마 참조가 코드와 일치하는지 검토하고 API 통합 테스트를 실행합니다. 전체 OpenAPI 의미·하위 호환성 자동 검증기는 아직 도입하지 않았습니다.

## 두 저장소 사이 전달

1. 백엔드 테스트와 명세 내보내기를 통과한 산출물을 검토합니다.
2. 로컬 개발에서는 버전별 `openapi.json`과 `manifest.json`을 전달합니다. 원격 배포가 필요하면 해당 산출물을 저장소 릴리스 또는 CI artifact에 게시합니다.
3. 프론트엔드는 해당 릴리스의 `openapi.json` URL 또는 다운로드한 파일을 명시적으로 입력해 동기화합니다.
4. 프론트엔드 snapshot과 계약 lock 변경을 함께 검토·커밋하고 UI/API 연동 테스트를 수행합니다.

프론트엔드의 실행·빌드가 백엔드의 로컬 체크아웃 경로에 의존하지 않게 합니다.
GitHub에서 받은 두 저장소의 원격 주소는 유지되어 있습니다. 이 작업에서는 로컬 코드와 계약을 작성·검증했으며 원격 push·태그·릴리스 업로드는 수행하지 않았습니다.

## 프론트엔드에서 받기

프론트엔드 저장소에서 다음 명령을 실행합니다.

```text
node scripts/sync-api-contract.mjs --source <릴리스-URL-또는-다운로드한-JSON> --version 1.1.0
node scripts/sync-api-contract.mjs --check
```

프론트엔드는 `src/shared/api/openapi.json`과 `contract-lock.json`을 관리합니다.
현재 프론트엔드는 API 클라이언트 코드로 이 JSON 계약을 호출하며 자동 타입/클라이언트 생성기는 사용하지 않습니다. snapshot·lock의 버전/해시와 실제 로그인·모의지원 연동을 함께 검증합니다.
호환성이 깨지는 변경은 major, 기존 요청과 응답을 유지하는 기능 추가는 minor, 설명·오류 수정처럼 호환성을 유지하는 수정은 patch로 구분합니다.
계약 버전은 각 저장소의 애플리케이션 버전과 구분합니다.

`contracts/schemas`에 별도 JSON Schema가 필요하면 이 OpenAPI의 `components.schemas`에서 추출하고 중복 원본을 만들지 않습니다. 인증 설정·메일 동작·OAuth 제한은 [인증 안내](auth.md)에 설명되어 있습니다.
