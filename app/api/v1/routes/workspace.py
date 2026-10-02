"""Versioned JSON API; domain workflows are assembled in application."""
from flask import Blueprint, current_app, jsonify, request, session

from app.core.security import require_login

api = Blueprint("workspace", __name__, url_prefix="/api/v1")


def service():
    return current_app.extensions["workspace_service"]


def body():
    value = request.get_json()
    if not isinstance(value, dict):
        raise ValueError("요청 본문은 JSON 객체여야 합니다.")
    return value


@api.get("/health")
def health():
    return jsonify(status="ok")


@api.get("/workspace")
@require_login
def workspace():
    return jsonify(service().workspace(session["user_id"]))


@api.put("/resume")
@require_login
def resume():
    return jsonify(service().save_resume(session["user_id"], body().get("resume_text", "")))


@api.post("/resume/upload")
@require_login
def upload():
    file = request.files.get("file")
    if not file or not file.filename:
        raise ValueError("먼저 불러올 이력서 파일을 선택해 주세요.")
    return jsonify(service().upload_resume(session["user_id"], file.filename, file.read(10 * 1024 * 1024 + 1)))


@api.put("/job")
@require_login
def job():
    data = body()
    return jsonify(service().save_job(session["user_id"], data.get("company", ""), data.get("role", ""), data.get("job_text", "")))


@api.get("/questions")
@require_login
def questions():
    return jsonify(questions=service().workspace(session["user_id"])["questions"])


@api.post("/analysis")
@require_login
def analysis():
    return jsonify(service().analyze(session["user_id"], body().get("answers", {})))


@api.post("/example")
@require_login
def example():
    return jsonify(service().example(session["user_id"]))


@api.delete("/workspace")
@require_login
def delete_workspace():
    return jsonify(service().delete(session["user_id"]))
