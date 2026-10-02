"""CareerLens Flask API application factory."""
import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from app.core.config import database_location, is_postgres, local_path

BASE_DIR = Path(__file__).resolve().parents[1]


def create_app(test_config=None):
    app = Flask(__name__)
    data_dir = local_path(os.environ.get("DATA_DIR") or os.environ.get("PROJECT2_DATA_DIR") or ".runtime", BASE_DIR)
    app.config.update(
        SECRET_KEY=os.environ.get("CAREERLENS_SECRET_KEY"),
        DATABASE=os.environ.get("DATABASE_URL") or "",
        DATA_DIR=str(data_dir),
        MAX_CONTENT_LENGTH=11 * 1024 * 1024,
        MAX_FORM_MEMORY_SIZE=11 * 1024 * 1024,
        SESSION_COOKIE_NAME="careerlens_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    )
    if test_config:
        app.config.update(test_config)
        if "DATABASE_URL" in test_config and "DATABASE" not in test_config:
            app.config["DATABASE"] = test_config["DATABASE_URL"]
    app.config["DATA_DIR"] = str(local_path(app.config["DATA_DIR"], BASE_DIR))
    app.config["DATABASE"] = database_location(app.config["DATABASE"], BASE_DIR, app.config["DATA_DIR"])
    # Legacy test configurations use an explicit temp database path. Keep their
    # runtime artifacts isolated too, even if a remote DATABASE_URL is set.
    if test_config and "DATABASE" in test_config and "DATA_DIR" not in test_config and not is_postgres(app.config["DATABASE"]):
        app.config["DATA_DIR"] = str(Path(app.config["DATABASE"]).parent)
    Path(app.config["DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    if not is_postgres(app.config["DATABASE"]):
        Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    if not app.config["SECRET_KEY"]:
        secret_path = Path(app.config["DATA_DIR"]) / "session.key"
        try:
            with secret_path.open("x", encoding="ascii") as handle:
                handle.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        app.config["SECRET_KEY"] = secret_path.read_text(encoding="ascii").strip()
    app.json.ensure_ascii = False

    from app.application.auth import setup_auth
    from app.application.workspace import WorkspaceService
    from app.infrastructure.database.draft_repository import SqliteDraftRepository
    from app.api.v1.routes.workspace import api

    setup_auth(app)
    app.extensions["workspace_service"] = WorkspaceService(SqliteDraftRepository(app.config["DATABASE"]), BASE_DIR / "data/examples")
    app.register_blueprint(api)

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.errorhandler(ValueError)
    def validation_error(error):
        return jsonify(error={"code": "validation_error", "message": str(error)}), 400

    @app.errorhandler(RequestEntityTooLarge)
    def upload_too_large(error):
        return jsonify(error={"code": "upload_too_large", "message": "파일 크기가 너무 큽니다. 10MB 이하의 파일을 선택해 주세요."}), 413

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error={"code": error.name.lower().replace(" ", "_"), "message": error.description}), error.code

    return app
