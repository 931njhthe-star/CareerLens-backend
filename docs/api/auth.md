# 로그인 구현과 설정

리플레쉬(refresh.cv)의 공개 로그인 화면에서 관찰한 Google, GitHub, LinkedIn, 이메일 로그인, 이메일 회원가입 및 비밀번호 찾기 흐름을 CareerLens 자체 인증으로 구현했습니다. 원본 서비스의 사용자 DB, 쿠키, API 키 또는 비밀번호를 가져오지 않습니다. 원본 계정의 비밀번호를 이 프로젝트에 입력할 필요가 없습니다.

## 기본 실행

이메일 가입 후 즉시 로컬 프로젝트를 사용할 수 있습니다. 이름은 1~80자, 비밀번호는 8~128자입니다. 교육용 로컬 환경에서는 이메일 소유권 인증을 생략하므로, 가입되었다는 사실을 이메일 소유권의 증거로 사용하면 안 됩니다. 로그인 후 작업 데이터는 UUID 사용자 ID별로 분리합니다.

비밀번호는 Werkzeug scrypt로 해시합니다. 무작위 세션 토큰은 서명된 HttpOnly/SameSite=Lax 쿠키에, 토큰의 SHA-256 해시와 7일 만료는 DATABASE_URL로 선택한 SQLite/PostgreSQL에 저장합니다. 로그아웃하면 서버 측 세션이 삭제되어 이전 쿠키를 다시 보내도 로그인할 수 없습니다. 비밀번호 변경은 해당 사용자의 모든 세션을 폐기합니다. HTTPS PUBLIC_ORIGIN에서는 Secure 쿠키가 자동 적용됩니다.

## API

오류 응답은 `{"error":{"code":"...","message":"한국어 안내"}}`입니다. `GET /api/v1/auth/session`에서 받은 `csrf_token`을 모든 POST/PUT/PATCH/DELETE `/api/*` 요청의 `X-CSRF-Token` 헤더에 넣습니다. 로그인·가입·로그아웃·비밀번호 변경 후 반환되는 새 토큰을 사용합니다. 브라우저 Origin이 있으면 PUBLIC_ORIGIN과 일치해야 합니다.

| 메서드/경로 (`/api/v1/auth` 접두사) | 입력 | 결과 |
| --- | --- | --- |
| GET `/session` | 없음 | user 또는 null, csrf_token, providers, mail_mode |
| POST `/register` | name, email, password | 201, 로그인된 session 응답 |
| POST `/login` | email, password | 200, 로그인된 session 응답 |
| POST `/logout` | `{}` | 200, 익명 session 응답 |
| POST `/forgot-password` | email | 계정 존재 여부와 관계없이 동일 안내 |
| POST `/reset-password` | token, password | 변경 안내 및 익명 session 응답 |
| GET `/oauth/<provider>` | google/github/linkedin | 제공자 인증 화면으로 이동, 미설정은 503 |
| GET `/oauth/<provider>/callback` | 제공자 code/state | 성공 시 `/`, 실패 시 `/?auth_error=...` |

각 인증 동작에는 접속 IP 기준 10분당 30회 제한이 있습니다. 개인 로컬 학습 용도의 제한이며, 다중 사용자 서비스 배포 시 프록시 신뢰 설정과 운영용 제한 정책을 별도로 설계해야 합니다.

## 비밀번호 찾기

SMTP 미설정 시 실제 메일을 보내지 않고 `DATA_DIR/mail/reset-*.eml`에 메일을 저장합니다(DATA_DIR 기본값 `.runtime`). `MAIL_OUTBOX`로 독립 경로를 지정할 수도 있습니다. 메일 파일을 열면 `http://127.0.0.1:5100/?reset_token=...` 링크가 있습니다. 토큰은 15분 동안 한 번만 사용할 수 있고 새 요청은 이전 토큰을 폐기합니다. DB에는 토큰 해시만 저장하며 API 응답에 토큰이나 메일 내용을 노출하지 않습니다. 이 폴더는 Git에서 제외되며 웹으로 제공되지 않습니다. `.eml` 파일에는 재설정 권한이 있으므로 로컬 개인 파일로 취급합니다.

실제 메일 발송이 필요하면 `.env`의 SMTP_HOST, SMTP_PORT, SMTP_FROM, SMTP_USERNAME, SMTP_PASSWORD를 자신의 서버 정보로 설정합니다. 465는 SMTP TLS, 다른 포트는 STARTTLS와 인증서 검증을 사용합니다. 연결 오류는 계정 존재 여부를 노출하지 않도록 일반 안내를 반환하며 서버 로그에 설정 점검 안내만 남깁니다.

## 소셜 로그인 활성화

각 제공자의 개발자 콘솔에서 **자신의 교육용 프로젝트 앱**을 등록한 다음 `.env.example`을 `.env`로 복사하고 CLIENT_ID/CLIENT_SECRET을 설정합니다. 재시작 후 해당 버튼을 사용할 수 있습니다. 키가 없으면 버튼은 준비되지 않은 상태를 표시하며, 로그인 성공을 가장하지 않습니다.

등록할 callback URL은 PUBLIC_ORIGIN 뒤에 다음 경로를 붙인 값입니다.

- Google: `/api/v1/auth/oauth/google/callback`, scope `openid profile email`
- GitHub: `/api/v1/auth/oauth/github/callback`, scope `read:user user:email`
- LinkedIn: `/api/v1/auth/oauth/linkedin/callback`, scope `openid profile email` 및 Sign In with LinkedIn using OpenID Connect 제품 활성화

Authlib가 authorization code/state 흐름을 처리합니다. Google/LinkedIn은 ID 토큰 서명·발급자·대상·만료·nonce를 검증합니다. GitHub는 S256 PKCE와 사용자 API 조회 및 확인된 기본 이메일을 사용합니다. OAuth access token을 프로젝트 DB나 브라우저에 지속 저장하지 않습니다. 같은 이메일로 이미 가입된 계정이 있으면 자동으로 연결하지 않으며 처음 가입한 방법으로 로그인하도록 안내합니다. LinkedIn이 확인된 이메일을 제공하지 않는 계정은 새 OAuth 가입을 허용하지 않고 이메일 가입을 안내합니다.

OAuth 동작은 설정 없는 상태·잘못된 state 차단까지 자동 테스트합니다. 실제 제공자와의 로그인 성공은 사용자의 프로젝트 키와 제공자 등록 없이는 검증할 수 없습니다. 외부 계정이나 앱을 대신 생성하지 않았습니다.

공식 구현 참고: [Authlib Flask OAuth](https://docs.authlib.org/en/latest/oauth2/client/web/flask.html), [GitHub authorization code flow](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps), [LinkedIn OpenID Connect](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2).
