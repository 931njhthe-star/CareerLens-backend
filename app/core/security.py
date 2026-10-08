"""Shared password, token and authentication helpers."""

from functools import wraps
from hashlib import sha256
from secrets import token_urlsafe

from flask import g, jsonify
from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password):
    return generate_password_hash(password, method="scrypt")


def verify_password(encoded, password):
    return check_password_hash(encoded, password)


def new_token():
    return token_urlsafe(32)


def token_digest(token):
    return sha256(token.encode("utf-8")).hexdigest()


def require_login(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not getattr(g, "user", None):
            return (
                jsonify(
                    error={"code": "authentication_required", "message": "로그인이 필요합니다."}
                ),
                401,
            )
        return view(*args, **kwargs)

    return wrapped
