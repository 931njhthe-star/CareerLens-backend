"""Version 1 authentication endpoints."""

import smtplib
from urllib.parse import urlencode

from authlib.common.errors import AuthlibBaseError
from flask import Blueprint, current_app, g, jsonify, redirect, request, session
from joserfc.errors import JoseError
from requests.exceptions import RequestException

from app.application.auth import begin_session, limit_auth_attempt, session_payload
from app.modules.auth.service import AuthError


auth_api = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


def payload():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise AuthError("JSON 객체 형식으로 입력해 주세요.")
    return value


@auth_api.get("/session")
def current_session():
    return jsonify(session_payload(current_app))


@auth_api.post("/register")
def register():
    limit_auth_attempt(current_app, "register")
    user = current_app.extensions["auth_service"].register(payload())
    begin_session(current_app, user)
    return jsonify(session_payload(current_app)), 201


@auth_api.post("/login")
def login():
    limit_auth_attempt(current_app, "login")
    user = current_app.extensions["auth_service"].login(payload())
    begin_session(current_app, user)
    return jsonify(session_payload(current_app))


@auth_api.post("/logout")
def logout():
    current_app.extensions["auth_service"].revoke_session(session.get("auth_token"))
    session.clear()
    g.user = None
    return jsonify(session_payload(current_app))


@auth_api.post("/forgot-password")
def forgot_password():
    limit_auth_attempt(current_app, "forgot")
    try:
        current_app.extensions["auth_service"].forgot_password(payload())
    except (OSError, smtplib.SMTPException):
        # The response must not disclose account existence or delivery details.
        current_app.logger.warning(
            "Password reset delivery failed; check local mail/SMTP configuration"
        )
    return jsonify(message="등록된 이메일이라면 비밀번호 재설정 안내를 보냈습니다.")


@auth_api.post("/reset-password")
def reset_password():
    limit_auth_attempt(current_app, "reset")
    current_app.extensions["auth_service"].reset_password(payload())
    session.clear()
    g.user = None
    return jsonify(
        message="비밀번호를 변경했습니다. 새 비밀번호로 로그인해 주세요.",
        **session_payload(current_app),
    )


@auth_api.get("/oauth/<provider>")
def oauth_start(provider):
    limit_auth_attempt(current_app, "oauth")
    client = current_app.extensions["auth_providers"].client(provider)
    callback = current_app.config["PUBLIC_ORIGIN"] + f"/api/v1/auth/oauth/{provider}/callback"
    try:
        return client.authorize_redirect(callback)
    except (AuthlibBaseError, JoseError, RequestException, ValueError):
        raise AuthError(
            "소셜 로그인 제공자에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            "provider_connection_failed",
            503,
        )


@auth_api.get("/oauth/<provider>/callback")
def oauth_callback(provider):
    target = current_app.config["PUBLIC_ORIGIN"] + "/"
    try:
        identity = current_app.extensions["auth_providers"].identity(provider)
        user = current_app.extensions["auth_service"].oauth_user(provider, identity)
        begin_session(current_app, user)
    except AuthError as error:
        return redirect(target + "?" + urlencode({"auth_error": error.message}))
    except (AuthlibBaseError, JoseError, RequestException, ValueError, KeyError):
        return redirect(
            target
            + "?"
            + urlencode({"auth_error": "소셜 로그인을 완료하지 못했습니다. 다시 시도해 주세요."})
        )
    return redirect(target)
