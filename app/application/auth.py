"""Compose the auth service and enforce session/CSRF rules for the Flask API."""
import hmac
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from flask import g, jsonify, request, session

from app.core.security import new_token, token_digest
from app.infrastructure.database.auth_repository import AuthRepository
from app.integrations.email.delivery import PasswordMailer
from app.integrations.oauth.providers import OAuthProviders, PROVIDERS
from app.modules.auth.service import AuthService, AuthError


def setup_auth(app):
    config_keys = ["PUBLIC_ORIGIN", "MAIL_OUTBOX", "SMTP_HOST", "SMTP_PORT", "SMTP_FROM", "SMTP_USERNAME", "SMTP_PASSWORD"]
    config_keys += [f"{provider.upper()}_{suffix}" for provider in PROVIDERS for suffix in ("CLIENT_ID", "CLIENT_SECRET")]
    for key in config_keys:
        if key not in app.config and os.environ.get(key):
            app.config[key] = os.environ[key]
    app.config.setdefault("PUBLIC_ORIGIN", "http://127.0.0.1:5100")
    app.config["PUBLIC_ORIGIN"] = app.config["PUBLIC_ORIGIN"].rstrip("/")
    origin = urlsplit(app.config["PUBLIC_ORIGIN"])
    if origin.scheme not in ("http", "https") or not origin.netloc or origin.path or origin.query or origin.fragment or origin.username:
        raise ValueError("PUBLIC_ORIGIN must contain only an http(s) origin, without a path or credentials")
    # Database URLs are never filesystem locations. The factory supplies
    # DATA_DIR; legacy standalone SQLite tests retain their temp-path fallback.
    if not app.config.get("MAIL_OUTBOX"):
        data_dir = app.config.get("DATA_DIR")
        if not data_dir:
            database = str(app.config["DATABASE"])
            data_dir = Path(database).parent if "://" not in database else Path(app.root_path).parent / ".runtime"
        app.config["MAIL_OUTBOX"] = str(Path(data_dir).resolve() / "mail")
    else:
        mail_path = Path(app.config["MAIL_OUTBOX"]).expanduser()
        if not mail_path.is_absolute():
            mail_path = Path(app.root_path).parent / mail_path
        app.config["MAIL_OUTBOX"] = str(mail_path.resolve())
    app.config.setdefault("AUTH_SESSION_SECONDS", 7 * 24 * 60 * 60)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if origin.scheme == "https":
        app.config["SESSION_COOKIE_SECURE"] = True
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=app.config["AUTH_SESSION_SECONDS"])
    repository = AuthRepository(app.config["DATABASE"])
    mailer = PasswordMailer(app.config)
    app.extensions["auth_service"] = AuthService(repository, mailer, app.config["AUTH_SESSION_SECONDS"])
    app.extensions["auth_providers"] = OAuthProviders(app)

    @app.before_request
    def authenticate_and_check_csrf():
        service = app.extensions["auth_service"]
        g.user = service.read_session(session.get("auth_token"))
        if g.user:
            session["user_id"] = g.user["id"]
        else:
            session.pop("user_id", None)
            session.pop("auth_token", None)
        if request.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
            if not request.path.startswith("/api/v1/auth/") and not g.user:
                return jsonify(error={"code": "authentication_required", "message": "로그인이 필요합니다."}), 401
            token = request.headers.get("X-CSRF-Token", "")
            expected = session.get("csrf_token", "")
            if not expected or not token or not hmac.compare_digest(expected.encode(), token.encode()):
                return jsonify(error={"code": "csrf_invalid", "message": "요청이 만료되었습니다. 새로고침 후 다시 시도해 주세요."}), 403
            request_origin = request.headers.get("Origin")
            if request_origin and request_origin.rstrip("/") != app.config["PUBLIC_ORIGIN"]:
                return jsonify(error={"code": "origin_invalid", "message": "허용되지 않은 사이트에서 보낸 요청입니다."}), 403

    @app.after_request
    def auth_response_headers(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.errorhandler(AuthError)
    def auth_error(error):
        return jsonify(error={"code": error.code, "message": error.message}), error.status

    from app.api.v1.routes.auth import auth_api
    app.register_blueprint(auth_api)


def session_payload(app):
    session.setdefault("csrf_token", new_token())
    return {"user": g.user, "csrf_token": session["csrf_token"],
            "providers": app.extensions["auth_providers"].list(),
            "mail_mode": app.extensions["auth_service"].mailer.mode}


def begin_session(app, user):
    service = app.extensions["auth_service"]
    service.revoke_session(session.get("auth_token"))
    session.clear()
    session["auth_token"] = service.new_session(user)
    session["user_id"] = user["id"]
    session["csrf_token"] = new_token()
    session.permanent = True
    g.user = user


def limit_auth_attempt(app, action):
    # Trust the socket peer, not untrusted X-Forwarded-For headers.
    bucket = token_digest(f"{action}:{request.remote_addr or 'local'}")
    if not app.extensions["auth_service"].repository.allow_attempt(bucket):
        raise AuthError("요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.", "rate_limited", 429)
