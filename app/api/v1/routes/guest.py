"""Cookie-scoped guest processing; completed reports are released only by claim."""

from flask import Blueprint, abort, current_app, g, jsonify, request, session

from app.application.guest import GuestError
from app.core.security import new_token, require_login, token_digest

guest_api = Blueprint("guest", __name__, url_prefix="/api/v1/guest")
GUEST_SESSION_KEY = "guest_id"


def service():
    return current_app.extensions["guest_service"]


def body():
    value = request.get_json()
    if not isinstance(value, dict):
        raise ValueError("요청 본문은 JSON 객체여야 합니다.")
    return value


def limit(action, maximum):
    repository = current_app.extensions["auth_service"].repository
    # A coarse socket-peer bucket bounds cookie resets while allowing people
    # sharing the frontend proxy to use their own smaller session allowance.
    identity = session.get(GUEST_SESSION_KEY) or session.get("csrf_token", "")
    buckets = (
        (f"guest:session:{action}:{identity}", maximum),
        (f"guest:peer:{action}:{request.remote_addr or 'local'}", {"upload": 40, "edit": 600, "analysis": 60}[action]),
    )
    for key, allowance in buckets:
        if not repository.allow_attempt(token_digest(key), limit=allowance, window=30 * 60):
            raise GuestError("요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.", "rate_limited", 429)


@guest_api.errorhandler(GuestError)
def guest_error(error):
    return jsonify(error={"code": error.code, "message": str(error)}), error.status


@guest_api.get("/workspace")
def workspace():
    return jsonify(service().workspace(session.get(GUEST_SESSION_KEY)))


@guest_api.post("/resume/upload")
def upload():
    limit("upload", 10)
    file = request.files.get("file")
    if not file or not file.filename:
        raise ValueError("먼저 불러올 이력서 파일을 선택해 주세요.")
    guest_id = session.get(GUEST_SESSION_KEY)
    create = not guest_id or service().repository.load(guest_id) is None
    if create:
        guest_id = new_token()
    result = service().upload(
        guest_id, file.filename, file.read(10 * 1024 * 1024 + 1), create=create
    )
    session[GUEST_SESSION_KEY] = guest_id
    return jsonify(result)


@guest_api.put("/career-target")
def career_target():
    limit("edit", 60)
    data = body()
    return jsonify(service().mutate(
        session.get(GUEST_SESSION_KEY), "save_career_target",
        data.get("role_id"), data.get("role", ""), data.get("focus", ""),
    ))


@guest_api.post("/job-postings/<posting_id>/select")
def select_posting(posting_id):
    limit("edit", 60)
    # Deliberately pass no user ID even if a login has just completed. Guests
    # cannot select private postings by guessing IDs or supplying job bodies.
    posting = current_app.extensions["jobs_service"].get(posting_id, None)
    if posting is None:
        abort(404, description="공고를 찾을 수 없습니다.")
    return jsonify(service().mutate(
        session.get(GUEST_SESSION_KEY), "save_job", posting["company"],
        posting["role"], posting["description"], posting_id=posting["id"],
        preserve_target=True,
    ))


@guest_api.post("/analysis")
def analysis():
    limit("analysis", 6)
    return jsonify(service().mutate(
        session.get(GUEST_SESSION_KEY), "analyze", body().get("answers", {}),
    ))


@guest_api.delete("/workspace")
def discard():
    guest_id = session.get(GUEST_SESSION_KEY)
    if guest_id:
        service().repository.delete(guest_id)
        session.pop(GUEST_SESSION_KEY, None)
    return jsonify(service().response())


@guest_api.post("/claim")
@require_login
def claim():
    guest_id = session.get(GUEST_SESSION_KEY)
    if not guest_id:
        raise GuestError("연결할 비회원 분석 자료가 없습니다.", "guest_missing", 404)
    result = service().repository.claim(guest_id, g.user["id"])
    if result == "incomplete":
        raise GuestError("비회원 분석을 먼저 완료해 주세요.", "guest_incomplete", 409)
    session.pop(GUEST_SESSION_KEY, None)
    if result == "expired":
        raise GuestError("비회원 임시 자료가 만료되었거나 삭제되었습니다. 다시 시작해 주세요.")
    return jsonify(current_app.extensions["workspace_service"].workspace(g.user["id"]))
