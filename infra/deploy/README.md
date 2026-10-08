# 백엔드 배포 준비

배포 업체와 관계없이 Python 3.12와 requirements.txt 의존성이 필요합니다. 현재 소스는 로컬 실행을 기본으로 유지합니다.

```sh
python -m pip install -r requirements.txt
python run.py --host 0.0.0.0 --port 8001
```

Waitress로 실행합니다. `--host` > `BACKEND_HOST` > 127.0.0.1, `--port` > `BACKEND_PORT` > `PORT` > 5101 순서입니다. 0.0.0.0은 배포 환경 내부의 수신 주소이며 브라우저에 입력할 URL이 아닙니다. 공개 HTTPS는 호스팅 서비스 또는 역방향 프록시에서 종료합니다. 로컬 통합 start.bat는 loopback을 유지합니다.

환경변수는 배포 서비스의 비밀 설정 또는 Git에서 제외되는 .env로 주입합니다. `.env.example`에는 실제 키를 넣지 않습니다.

- `DATABASE_URL`: 운영 PostgreSQL 또는 영속 볼륨의 SQLite 파일. 빈 값은 .runtime에 새 DB를 생성합니다. 기존 DB가 자동 업로드되거나 이전되는 것은 아닙니다.
- `DATA_DIR`: 세션 키·개인 파일을 위한 영속 디렉터리. 임시 컨테이너 파일시스템에 저장하지 않습니다.
- `CAREERLENS_SECRET_KEY`: 서비스 재시작·여러 인스턴스에서 동일하게 유지하는 운영 비밀값.
- `PUBLIC_ORIGIN`: 실제 사용자가 접속하는 프론트엔드의 정확한 origin.
- `SESSION_COOKIE_SECURE=1`: 브라우저 화면을 HTTPS로 제공할 때 사용합니다.
- OAuth·SMTP·선택적 LLM 키는 운영자가 별도로 설정합니다. 기본 분석은 rules입니다.

DB 테이블은 현재 저장소 초기화 코드에서 생성합니다. 버전별 운영 마이그레이션과 롤백 체계가 완성되어 있다는 의미는 아닙니다. 배포 전 기존 데이터 백업과 스키마 호환성을 확인해야 합니다. SQLite는 단일 인스턴스와 영속 저장을 전제로 하며 여러 인스턴스 운영에는 PostgreSQL을 사용합니다.

상태 확인: `/api/v1/health`. 이는 외부 AI·메일·OAuth까지 검증하는 종합 준비 상태가 아닙니다. 배포 후 로그인·이력서 저장·분석·보고서 흐름을 검증합니다. 실제 운영 DB/HTTPS/OAuth 검증과 배포는 미수행입니다.
