"""Authenticated matches derived only from the current user's saved resume."""

from flask import Blueprint, current_app, jsonify, session

from app.core.security import require_login


matching_api = Blueprint("job_matching", __name__, url_prefix="/api/v1")


@matching_api.get("/job-matches")
@require_login
def job_matches():
    service = current_app.extensions["job_matching_service"]
    return jsonify(job_matches=service.for_user(session["user_id"]))
