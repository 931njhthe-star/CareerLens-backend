import re
from email import policy
from email.parser import BytesParser
from urllib.parse import parse_qs, urlsplit

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from flask import Flask, g, jsonify

from app.application.auth import setup_auth
from app.core.security import require_login, token_digest
from app.modules.auth.service import AuthError


def make_app(tmp_path):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-only",
        DATABASE=str(tmp_path / "auth.db"),
        PUBLIC_ORIGIN="http://127.0.0.1:5100",
        MAIL_OUTBOX=str(tmp_path / "mail"),
        GOOGLE_CLIENT_ID="",
        GOOGLE_CLIENT_SECRET="",
        GITHUB_CLIENT_ID="",
        GITHUB_CLIENT_SECRET="",
        LINKEDIN_CLIENT_ID="",
        LINKEDIN_CLIENT_SECRET="",
        SMTP_HOST="",
    )
    setup_auth(app)

    @app.route("/api/v1/private", methods=["GET", "POST"])
    @require_login
    def private():
        return jsonify(user_id=g.user["id"])

    return app


def post(client, path, data):
    token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
    return client.post("/api/v1/auth/" + path, json=data, headers={"X-CSRF-Token": token})


def register(client, email="learner@example.com"):
    return post(
        client, "register", {"name": "학습자", "email": email, "password": "correct horse 42"}
    )


def reset_token(app):
    from pathlib import Path

    messages = sorted(
        Path(app.config["MAIL_OUTBOX"]).glob("*.eml"), key=lambda p: p.stat().st_mtime_ns
    )
    mail = BytesParser(policy=policy.default).parsebytes(messages[-1].read_bytes())
    return re.search(r"reset_token=([A-Za-z0-9_-]+)", mail.get_content()).group(1)


class AuthIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp_path = Path(self.temp.name)
        self.app = make_app(self.tmp_path)

    def test_registration_login_hash_and_identity_isolation(self):
        app = self.app
        alice, bob = app.test_client(), app.test_client()
        first = register(alice)
        second = register(bob, "second@example.com")
        assert first.status_code == second.status_code == 201
        a, b = first.get_json()["user"], second.get_json()["user"]
        assert a["id"] != b["id"]
        assert alice.get("/api/v1/private").get_json()["user_id"] == a["id"]
        assert bob.get("/api/v1/private").get_json()["user_id"] == b["id"]
        row = app.extensions["auth_service"].repository.user_by_email(a["email"])
        assert row["password_hash"].startswith("scrypt:")
        assert "correct horse" not in row["password_hash"]
        assert "password_hash" not in str(first.get_json())
        assert post(alice, "logout", {}).status_code == 200
        assert post(alice, "login", {"email": a["email"], "password": "wrong"}).status_code == 401
        assert (
            post(
                alice, "login", {"email": " LEARNER@EXAMPLE.COM ", "password": "correct horse 42"}
            ).status_code
            == 200
        )

    def test_csrf_and_foreign_origin_are_rejected(self):
        app = self.app
        client = app.test_client()
        assert client.post("/api/v1/auth/login", json={}).status_code == 403
        state = client.get("/api/v1/auth/session").get_json()
        assert state["user"] is None
        assert (
            client.post(
                "/api/v1/auth/register", json={}, headers={"X-CSRF-Token": "wrong"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/auth/register",
                json={},
                headers={"X-CSRF-Token": state["csrf_token"], "Origin": "https://evil.example"},
            ).status_code
            == 403
        )
        assert client.get("/api/v1/private").status_code == 401
        assert client.post("/api/v1/private", json={}).status_code == 401

    def test_logout_revokes_replayed_cookie_and_rotates_csrf(self):
        app = self.app
        client = app.test_client()
        before = client.get("/api/v1/auth/session").get_json()["csrf_token"]
        logged_in = register(client).get_json()
        assert logged_in["csrf_token"] != before
        cookie = client.get_cookie(app.config["SESSION_COOKIE_NAME"]).value
        result = post(client, "logout", {}).get_json()
        assert result["user"] is None and result["csrf_token"] != logged_in["csrf_token"]
        client.set_cookie(app.config["SESSION_COOKIE_NAME"], cookie)
        assert client.get("/api/v1/private").status_code == 401

    def test_user_id_cookie_alone_and_expired_session_cannot_authenticate(self):
        app = self.app
        client = app.test_client()
        user_id = register(client).get_json()["user"]["id"]
        with client.session_transaction() as state:
            state.pop("auth_token")
            state["user_id"] = user_id
        assert client.get("/api/v1/private").status_code == 401
        post(client, "login", {"email": "learner@example.com", "password": "correct horse 42"})
        with app.extensions["auth_service"].repository.connection() as db:
            db.execute("UPDATE auth_sessions SET expires_at=0")
        assert client.get("/api/v1/private").status_code == 401

    def test_reset_token_is_private_single_use_and_revokes_all_sessions(self):
        app = self.app
        client, second = app.test_client(), app.test_client()
        register(client)
        post(second, "login", {"email": "learner@example.com", "password": "correct horse 42"})
        known = post(client, "forgot-password", {"email": "learner@example.com"})
        unknown = post(client, "forgot-password", {"email": "unknown@example.com"})
        assert known.get_json() == unknown.get_json()
        token = reset_token(app)
        assert token not in str(known.get_json())
        with app.extensions["auth_service"].repository.connection() as db:
            assert db.execute("SELECT digest FROM auth_password_resets").fetchone()[
                0
            ] == token_digest(token)
        assert (
            post(
                client, "reset-password", {"token": token, "password": "new correct horse"}
            ).status_code
            == 200
        )
        assert second.get("/api/v1/private").status_code == 401
        assert (
            post(
                client, "reset-password", {"token": token, "password": "another password"}
            ).status_code
            == 400
        )
        assert (
            post(
                client, "login", {"email": "learner@example.com", "password": "correct horse 42"}
            ).status_code
            == 401
        )
        assert (
            post(
                client, "login", {"email": "learner@example.com", "password": "new correct horse"}
            ).status_code
            == 200
        )

    def test_expired_and_replaced_reset_tokens_are_invalid(self):
        app = self.app
        client = app.test_client()
        register(client)
        post(client, "forgot-password", {"email": "learner@example.com"})
        first = reset_token(app)
        post(client, "forgot-password", {"email": "learner@example.com"})
        second = reset_token(app)
        assert first != second
        assert (
            post(
                client, "reset-password", {"token": first, "password": "replacement pass"}
            ).status_code
            == 400
        )
        with app.extensions["auth_service"].repository.connection() as db:
            db.execute("UPDATE auth_password_resets SET expires_at=0")
        assert (
            post(
                client, "reset-password", {"token": second, "password": "replacement pass"}
            ).status_code
            == 400
        )

    def test_providers_unconfigured_do_not_fake_success(self):
        app = self.app
        client = app.test_client()
        state = client.get("/api/v1/auth/session").get_json()
        assert state["mail_mode"] == "local"
        assert [p["id"] for p in state["providers"]] == ["google", "github", "linkedin"]
        assert not any(p["enabled"] for p in state["providers"])
        for provider in ("google", "github", "linkedin"):
            assert client.get("/api/v1/auth/oauth/" + provider).status_code == 503
        assert client.get("/api/v1/auth/oauth/unknown").status_code == 404

    def test_oauth_github_state_rejection_never_contacts_provider(self):
        tmp_path = self.tmp_path
        from requests.sessions import Session

        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-only",
            DATABASE=str(tmp_path / "oauth.db"),
            PUBLIC_ORIGIN="http://127.0.0.1:5100",
            GITHUB_CLIENT_ID="own-project-test-id",
            GITHUB_CLIENT_SECRET="own-project-test-secret",
        )
        setup_auth(app)
        client = app.test_client()
        start = client.get("/api/v1/auth/oauth/github")
        query = parse_qs(urlsplit(start.location).query)
        assert query["client_id"] == ["own-project-test-id"]
        assert query["code_challenge_method"] == ["S256"]
        assert "state" in query

        def no_network(*args, **kwargs):
            raise AssertionError("Rejected OAuth state must not cause a token request")

        network_patch = patch.object(Session, "request", no_network)
        network_patch.start()
        self.addCleanup(network_patch.stop)
        for suffix in ("?code=fake&state=wrong", "?code=fake", "?error=access_denied&state=wrong"):
            response = client.get("/api/v1/auth/oauth/github/callback" + suffix)
            assert response.status_code == 302
            assert "auth_error=" in response.location
            assert client.get("/api/v1/auth/session").get_json()["user"] is None

    def test_oauth_existing_email_never_silently_links_accounts(self):
        app = self.app
        client = app.test_client()
        register(client)
        service = app.extensions["auth_service"]
        with self.assertRaisesRegex(AuthError, "처음 가입한"):
            service.oauth_user(
                "google",
                {"sub": "verified-sub", "email": "learner@example.com", "email_verified": True},
            )
        with self.assertRaisesRegex(AuthError, "확인된 이메일"):
            service.oauth_user(
                "google",
                {"sub": "unverified-sub", "email": "another@example.com", "email_verified": False},
            )

    def test_auth_rate_limit_returns_429(self):
        app = self.app
        client = app.test_client()
        for _ in range(30):
            assert (
                post(client, "login", {"email": "invalid", "password": "anything"}).status_code
                == 400
            )
        assert (
            post(client, "login", {"email": "invalid", "password": "anything"}).status_code == 429
        )

    def test_oidc_missing_email_uses_subject_bound_userinfo(self):
        providers = self.app.extensions["auth_providers"]
        client = MagicMock()
        client.authorize_access_token.return_value = {
            "id_token": "validated-by-authlib",
            "userinfo": {"sub": "subject-one"},
        }
        client.userinfo.return_value = {
            "sub": "subject-one",
            "email": "linked@example.com",
            "email_verified": True,
        }
        with patch.object(providers, "client", return_value=client):
            identity = providers.identity("linkedin")
            self.assertEqual(identity["email"], "linked@example.com")
            self.assertTrue(identity["email_verified"])

    def test_oidc_userinfo_cannot_substitute_another_subject(self):
        providers = self.app.extensions["auth_providers"]
        client = MagicMock()
        client.authorize_access_token.return_value = {
            "id_token": "validated-by-authlib",
            "userinfo": {"sub": "subject-one"},
        }
        client.userinfo.return_value = {
            "sub": "subject-two",
            "email": "wrong@example.com",
            "email_verified": True,
        }
        with patch.object(providers, "client", return_value=client):
            with self.assertRaisesRegex(AuthError, "일치하지"):
                providers.identity("linkedin")
