"""Public examples, owner-private manual postings, and account bookmarks."""

from flask import Blueprint, abort, current_app, g, jsonify, request

from app.core.security import require_login


jobs_api = Blueprint("jobs", __name__, url_prefix="/api/v1/job-postings")


def service():
    return current_app.extensions["jobs_service"]


def user_id():
    return g.user["id"] if g.user else None


def found(posting):
    if posting is None:
        abort(404, description="공고를 찾을 수 없습니다.")
    return jsonify(posting=posting)


@jobs_api.get("")
def list_postings():
    if request.args.get("saved") == "1" and not g.user:
        return (
            jsonify(
                error={
                    "code": "authentication_required",
                    "message": "저장한 공고는 로그인 후 볼 수 있습니다.",
                }
            ),
            401,
        )
    return jsonify(service().list(request.args, user_id()))


@jobs_api.get("/<posting_id>")
def get_posting(posting_id):
    return found(service().get(posting_id, user_id()))


@jobs_api.post("")
@require_login
def create_posting():
    return found(service().create(request.get_json(), user_id())), 201


@jobs_api.put("/<posting_id>")
@require_login
def update_posting(posting_id):
    return found(service().update(posting_id, request.get_json(), user_id()))


@jobs_api.delete("/<posting_id>")
@require_login
def delete_posting(posting_id):
    if not service().delete(posting_id, user_id()):
        abort(404, description="수정 가능한 내 공고를 찾을 수 없습니다.")
    return jsonify(deleted=True, id=posting_id)


@jobs_api.post("/<posting_id>/bookmark")
@require_login
def save_bookmark(posting_id):
    return found(service().bookmark(posting_id, user_id(), True))


@jobs_api.post("/<posting_id>/select")
@require_login
def select_for_application(posting_id):
    # Resolve the current, authorized DB record; never trust client-supplied job text.
    posting = service().get(posting_id, user_id())
    if posting is None:
        abort(404, description="공고를 찾을 수 없습니다.")
    workspace = current_app.extensions["workspace_service"]
    return jsonify(
        workspace.save_job(
            user_id(),
            posting["company"],
            posting["role"],
            posting["description"],
            posting_id=posting["id"],
            preserve_target=True,
        )
    )


@jobs_api.delete("/<posting_id>/bookmark")
@require_login
def delete_bookmark(posting_id):
    return found(service().bookmark(posting_id, user_id(), False))
