"""Authentication rules; persistence and delivery are injected by application."""
import re
import time
from uuid import uuid4

from app.core.security import hash_password, verify_password, new_token, token_digest


class AuthError(Exception):
    def __init__(self, message, code="invalid_input", status=400):
        super().__init__(message)
        self.message, self.code, self.status = message, code, status


def clean_email(value):
    if not isinstance(value, str):
        raise AuthError("올바른 이메일 주소를 입력해 주세요.")
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value):
        raise AuthError("올바른 이메일 주소를 입력해 주세요.")
    return value


def clean_password(value):
    if not isinstance(value, str) or not 8 <= len(value) <= 128:
        raise AuthError("비밀번호는 8~128자로 입력해 주세요.")
    return value


def public_user(user):
    return {key: user[key] for key in ("id", "email", "name")} if user else None


class AuthService:
    def __init__(self, repository, mailer, session_seconds=604800):
        self.repository, self.mailer = repository, mailer
        self.session_seconds = session_seconds
        self.dummy_hash = hash_password(new_token())

    def register(self, data):
        email, password = clean_email(data.get("email")), clean_password(data.get("password"))
        name = data.get("name", "")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise AuthError("이름을 1~80자로 입력해 주세요.")
        user = {"id": str(uuid4()), "email": email, "name": name.strip(), "password_hash": hash_password(password)}
        if not self.repository.create_user(user):
            raise AuthError("이미 가입된 이메일입니다. 로그인 또는 비밀번호 찾기를 이용해 주세요.", "email_exists", 409)
        return public_user(user)

    def login(self, data):
        email = clean_email(data.get("email"))
        password = data.get("password")
        if not isinstance(password, str) or len(password) > 128:
            raise AuthError("이메일 또는 비밀번호가 올바르지 않습니다.", "invalid_credentials", 401)
        user = self.repository.user_by_email(email)
        encoded = (user or {}).get("password_hash") or self.dummy_hash
        valid = verify_password(encoded, password)
        if not user or not user.get("password_hash") or not valid:
            raise AuthError("이메일 또는 비밀번호가 올바르지 않습니다.", "invalid_credentials", 401)
        return public_user(user)

    def new_session(self, user):
        token = new_token()
        self.repository.create_session(token_digest(token), user["id"], int(time.time()) + self.session_seconds)
        return token

    def read_session(self, token):
        return public_user(self.repository.session_user(token_digest(token), int(time.time()))) if token else None

    def revoke_session(self, token):
        if token:
            self.repository.revoke_session(token_digest(token))

    def forgot_password(self, data):
        email = clean_email(data.get("email"))
        user = self.repository.user_by_email(email)
        # OAuth-only users continue with their provider. Never create a local password here.
        if user and user.get("password_hash"):
            token = new_token()
            self.repository.create_reset(token_digest(token), user["id"], int(time.time()) + 900)
            self.mailer.send_reset(email, token)

    def reset_password(self, data):
        password = clean_password(data.get("password"))
        token = data.get("token")
        if not isinstance(token, str) or not 20 <= len(token) <= 256:
            raise AuthError("재설정 링크가 만료되었거나 이미 사용되었습니다.", "invalid_reset_token")
        if not self.repository.consume_reset(token_digest(token), hash_password(password), int(time.time())):
            raise AuthError("재설정 링크가 만료되었거나 이미 사용되었습니다.", "invalid_reset_token")

    def oauth_user(self, provider, identity):
        subject = identity.get("sub")
        if not subject or not isinstance(subject, str) or len(subject) > 255:
            raise AuthError("소셜 로그인 계정을 확인할 수 없습니다.", "oauth_identity_invalid")
        existing = self.repository.oauth_user(provider, subject)
        if existing:
            return public_user(existing)
        if identity.get("email_verified") is not True:
            raise AuthError("소셜 계정에서 확인된 이메일을 제공하지 않았습니다. 이메일 로그인을 이용해 주세요.", "oauth_email_unverified")
        email = clean_email(identity.get("email"))
        if self.repository.user_by_email(email):
            # Local educational registrations do not verify email ownership, so never auto-link.
            raise AuthError("이미 가입된 이메일입니다. 처음 가입한 로그인 방법을 이용해 주세요.", "oauth_account_exists", 409)
        name = str(identity.get("name") or email.split("@")[0])[:80]
        user = {"id": str(uuid4()), "email": email, "name": name, "password_hash": None}
        if not self.repository.create_oauth_user(user, provider, subject):
            raise AuthError("이미 가입된 이메일입니다. 처음 가입한 로그인 방법을 이용해 주세요.", "oauth_account_exists", 409)
        return public_user(user)
