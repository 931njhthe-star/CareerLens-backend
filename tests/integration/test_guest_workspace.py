"""Guest content never leaves the server until an authenticated atomic claim."""

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from app import create_app
from app.application import workspace as workspace_module
from app.infrastructure.database.guest_repository import GuestCleanup, RETENTION_SECONDS


class GuestWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app({
            "TESTING": True, "SECRET_KEY": "guest-synthetic-test-key",
            "DATABASE": str(Path(self.temp.name) / "guest.sqlite3"),
        })
        self.client = self.app.test_client()
        self.repository = self.app.extensions["guest_service"].repository
        self.resume = (
            "GUEST_PRIVATE_SENTINEL Python과 Flask로 API를 개발했습니다. "
            "SQL 데이터 모델을 설계하고 Docker 배포를 담당했습니다. 처리 시간을 30% 줄였습니다."
        )
        self.posting = self.client.get("/api/v1/job-postings?page_size=1").get_json()["items"][0]

    def mutate(self, path, *, method="POST", client=None, **kwargs):
        client = client or self.client
        token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
        return client.open(path, method=method, headers={"X-CSRF-Token": token}, **kwargs)

    def guest_id(self, client=None):
        with (client or self.client).session_transaction() as state:
            return state.get("guest_id")

    def upload(self, client=None):
        response = self.mutate(
            "/api/v1/guest/resume/upload", client=client,
            data={"file": (BytesIO(self.resume.encode()), "C:/private/guest.txt")},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assert_safe(response.get_json())
        return response.get_json()

    def prepare(self, client=None):
        self.upload(client)
        result = self.mutate(
            "/api/v1/guest/career-target", method="PUT", client=client,
            json={"role_id": "backend"},
        )
        self.assertEqual(result.status_code, 200, result.get_json())
        self.assert_safe(result.get_json())
        result = self.mutate(
            f"/api/v1/guest/job-postings/{self.posting['id']}/select", client=client,
        )
        self.assertEqual(result.status_code, 200, result.get_json())
        self.assert_safe(result.get_json())
        return result.get_json()

    def complete(self, client=None):
        self.prepare(client)
        response = self.mutate("/api/v1/guest/analysis", client=client, json={"answers": {}})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assert_safe(response.get_json())
        self.assertTrue(response.get_json()["completed"])
        self.assertTrue(response.get_json()["report_locked"])
        return response.get_json()

    def register(self, client=None, email="guest-claim@example.test"):
        result = self.mutate(
            "/api/v1/auth/register", client=client,
            json={"email": email, "password": "Guest-Claim-Test-2026!", "name": "가상 사용자"},
        )
        self.assertEqual(result.status_code, 201, result.get_json())
        return result.get_json()["user"]

    def assert_safe(self, payload):
        self.assertEqual(set(payload), {"draft", "questions", "report_locked", "completed", "expires_at", "expired"})
        self.assertEqual(set(payload["draft"]), {
            "resume_attached", "filename", "company", "role", "analysis_mode",
            "career_target", "selected_posting_id",
        })
        for question in payload["questions"]:
            self.assertEqual(set(question), {"id", "prompt", "reason"})
        self.assertNotIn("GUEST_PRIVATE_SENTINEL", str(payload))
        for key in ("resume_text", "report", "answers", "score", "scores", "preparation", "job_text"):
            self.assertNotIn("'" + key + "':", str(payload))

    def test_real_analysis_is_locked_and_every_guest_response_is_allowlisted(self):
        empty = self.client.get("/api/v1/guest/workspace")
        self.assert_safe(empty.get_json())
        self.assertFalse(empty.get_json()["draft"]["resume_attached"])
        self.assertIsNone(self.guest_id())
        self.complete()
        stored = self.repository.load(self.guest_id())["draft"]
        self.assertEqual(stored["resume_text"], self.resume)
        self.assertIsInstance(stored["report"]["score"], (int, float))
        public = self.client.get("/api/v1/guest/workspace")
        self.assert_safe(public.get_json())
        self.assertEqual(public.headers["Cache-Control"], "no-store")
        with self.client.session_transaction() as state:
            self.assertNotIn("GUEST_PRIVATE_SENTINEL", str(dict(state)))
            self.assertGreaterEqual(len(state["guest_id"]), 32)
        self.assertFalse(list(Path(self.temp.name).rglob("*.txt")))

    def test_signup_preserves_guest_and_claim_transfers_original_scores_once(self):
        self.complete()
        guest_id = self.guest_id()
        report = self.repository.load(guest_id)["draft"]["report"]
        user = self.register()
        self.assertEqual(self.guest_id(), guest_id)
        result = self.mutate("/api/v1/guest/claim", json={})
        self.assertEqual(result.status_code, 200, result.get_json())
        self.assertEqual(result.get_json()["draft"]["resume_text"], self.resume)
        for key in ("score", "criteria", "matches", "analysis_mode"):
            self.assertEqual(result.get_json()["draft"]["report"][key], report[key])
        self.assertIsNone(self.repository.load(guest_id))
        self.assertIsNone(self.guest_id())
        self.assertEqual(self.mutate("/api/v1/guest/claim").status_code, 404)
        self.assertIsNotNone(self.app.extensions["workspace_service"].workspace(user["id"])["draft"]["report"])

    def test_large_guest_multipart_never_spools_original_binary_to_disk(self):
        binary = b"synthetic-upload-bytes" * 30_000
        # Construct in memory too: Werkzeug's test multipart encoder itself
        # otherwise spools this fixture while acting as the HTTP client.
        multipart = (
            b'--guest-fixture\r\nContent-Disposition: form-data; name="file"; filename="synthetic.txt"\r\n'
            b"Content-Type: text/plain\r\n\r\n" + binary + b"\r\n--guest-fixture--\r\n"
        )
        with patch("werkzeug.wrappers.request.default_stream_factory") as disk_factory, patch(
            "app.application.workspace.extract_resume", return_value=self.resume
        ) as extract:
            response = self.mutate(
                "/api/v1/guest/resume/upload", data=multipart,
                content_type="multipart/form-data; boundary=guest-fixture",
            )
        self.assertEqual(response.status_code, 200, response.get_json())
        disk_factory.assert_not_called()
        extract.assert_called_once_with("synthetic.txt", binary)

    def test_login_and_oauth_begin_session_preserve_guest_identity(self):
        self.register()
        self.mutate("/api/v1/auth/logout", json={})
        self.complete()
        guest_id = self.guest_id()
        response = self.mutate("/api/v1/auth/login", json={
            "email": "guest-claim@example.test", "password": "Guest-Claim-Test-2026!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.guest_id(), guest_id)
        # OAuth uses the same session rotation; exercise its actual callback.
        user = response.get_json()["user"]
        with patch.object(self.app.extensions["auth_providers"], "identity", return_value={}), patch.object(
            self.app.extensions["auth_service"], "oauth_user", return_value=user
        ):
            self.assertEqual(self.client.get("/api/v1/auth/oauth/google/callback").status_code, 302)
        self.assertEqual(self.guest_id(), guest_id)
        self.assertEqual(self.mutate("/api/v1/guest/claim").status_code, 200)

    def test_guest_isolation_and_claim_requires_authentication(self):
        self.complete()
        first_id = self.guest_id()
        other = self.app.test_client()
        self.assertFalse(other.get("/api/v1/guest/workspace").get_json()["completed"])
        self.assertEqual(self.mutate("/api/v1/guest/claim").status_code, 401)
        self.register(other, "other@example.test")
        self.assertEqual(self.mutate("/api/v1/guest/claim", client=other).status_code, 404)
        self.assertIsNotNone(self.repository.load(first_id))
        self.upload(other)
        self.assertNotEqual(self.guest_id(other), first_id)
        self.mutate("/api/v1/guest/workspace", method="DELETE", client=other)
        self.assertIsNotNone(self.repository.load(first_id))

    def test_guest_cannot_select_private_posting_even_after_login(self):
        self.upload()
        user = self.register()
        private = self.app.extensions["jobs_service"].create({
            "company": "가상 비공개", "role": "개발자", "location": "서울",
            "employment_type": "계약직", "experience_level": "신입", "skills": ["Python"],
            "description": "주요업무\nPython API를 개발하고 SQL 데이터 모델을 설계합니다.\n자격요건\nGit 협업과 테스트 작성 경험이 필요합니다.",
            "source_url": "https://example.test/private",
        }, user["id"])
        before = self.repository.load(self.guest_id())
        response = self.mutate(f"/api/v1/guest/job-postings/{private['id']}/select")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.repository.load(self.guest_id()), before)

    def test_fixed_expiry_does_not_extend_on_upload_edit_or_analysis(self):
        start = int(time.time())
        with patch("app.infrastructure.database.guest_repository.time", return_value=start):
            self.upload()
        guest_id = self.guest_id()
        self.assertEqual(self.repository.load(guest_id)["expires_at"], start + RETENTION_SECONDS)
        with patch("app.infrastructure.database.guest_repository.time", return_value=start + 60):
            self.prepare()
            response = self.mutate("/api/v1/guest/analysis", json={"answers": {}})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.repository.load(guest_id)["expires_at"], start + RETENTION_SECONDS)
        self.register()
        with patch("app.infrastructure.database.guest_repository.time", return_value=start + RETENTION_SECONDS):
            response = self.mutate("/api/v1/guest/claim")
            self.assertEqual(response.status_code, 410)
            self.assertEqual(response.get_json()["error"]["code"], "guest_expired")
        self.assertIsNone(self.repository.load(guest_id))
        self.assertIsNone(self.client.get("/api/v1/workspace").get_json()["draft"]["report"])

    def test_expired_data_is_deleted_without_any_browser_request(self):
        self.upload()
        with self.repository.storage.connection() as db:
            db.execute("UPDATE guest_workspaces SET expires_at=0")
        cleanup = GuestCleanup(self.repository, interval=0.01)
        self.addCleanup(cleanup.stop)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with self.repository.storage.connection() as db:
                count = db.execute("SELECT count(*) AS n FROM guest_workspaces").fetchone()["n"]
            if count == 0:
                break
            time.sleep(0.01)
        self.assertEqual(count, 0)
        cleanup.stop()
        result = self.mutate("/api/v1/guest/analysis", json={"answers": {}})
        self.assertEqual(result.status_code, 410)
        expired = self.client.get("/api/v1/guest/workspace").get_json()
        self.assert_safe(expired)
        self.assertFalse(expired["completed"])
        self.assertTrue(expired["expired"])
        # Login retains the missing pointer, allowing an OAuth/new page to
        # distinguish expiration from a guest who never started an analysis.
        self.register()
        self.assertTrue(self.client.get("/api/v1/guest/workspace").get_json()["expired"])
        discarded = self.mutate("/api/v1/guest/workspace", method="DELETE").get_json()
        self.assertFalse(discarded["expired"])

    def test_late_analysis_cannot_resurrect_discarded_expired_or_claimed_data(self):
        original = workspace_module.analyze
        for event in ("delete", "expire", "claim"):
            with self.subTest(event=event):
                self.prepare()
                guest_id = self.guest_id()
                if event == "claim":
                    self.mutate("/api/v1/guest/analysis", json={"answers": {}})
                def analyze(*args, **kwargs):
                    result = original(*args, **kwargs)
                    if event == "delete":
                        self.repository.delete(guest_id)
                    elif event == "expire":
                        with self.repository.storage.connection() as db:
                            db.execute("UPDATE guest_workspaces SET expires_at=0 WHERE guest_id=?", (guest_id,))
                    else:
                        self.assertEqual(self.repository.claim(guest_id, "synthetic-owner"), "claimed")
                    return result
                with patch("app.application.workspace.analyze", side_effect=analyze):
                    result = self.mutate("/api/v1/guest/analysis", json={"answers": {}})
                self.assertEqual(result.status_code, 410, result.get_json())
                self.assertIsNone(self.repository.load(guest_id))

    def test_claim_is_atomic_under_concurrency_and_incomplete_claim_preserves_data(self):
        self.prepare()
        guest_id = self.guest_id()
        self.register()
        self.assertEqual(self.mutate("/api/v1/guest/claim").status_code, 409)
        self.assertIsNotNone(self.repository.load(guest_id))
        self.mutate("/api/v1/guest/analysis", json={"answers": {}})
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: self.repository.claim(guest_id, "synthetic-owner"), range(2)))
        self.assertEqual(sorted(results), ["claimed", "expired"])

    def test_invalid_inputs_leave_guest_untouched_and_original_member_guards_remain(self):
        self.prepare()
        before = self.repository.load(self.guest_id())
        cases = [
            ("/api/v1/guest/analysis", {"json": {"answers": {"invented": "private answer"}}}),
            ("/api/v1/guest/analysis", {"json": []}),
            ("/api/v1/guest/resume/upload", {"data": {"file": (BytesIO(b"binary\x00data"), "bad.txt")}}),
        ]
        for path, options in cases:
            self.assertEqual(self.mutate(path, **options).status_code, 400)
            self.assertEqual(self.repository.load(self.guest_id()), before)
        for method, path in (("GET", "workspace"), ("POST", "analysis"), ("POST", "resume/upload"), ("PUT", "career-target")):
            self.assertEqual(self.client.open("/api/v1/" + path, method=method).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/guest/analysis", json={}).status_code, 403)
        token = self.client.get("/api/v1/auth/session").get_json()["csrf_token"]
        self.assertEqual(self.client.post("/api/v1/guest/analysis", json={}, headers={
            "X-CSRF-Token": token, "Origin": "https://other.example.test",
        }).status_code, 403)

    def test_rate_limits_allow_distinct_guests_but_bound_cookie_resets(self):
        self.prepare()
        for _ in range(6):
            # Invalid attempts count too; no expensive analysis required here.
            self.assertEqual(self.mutate("/api/v1/guest/analysis", json=[]).status_code, 400)
        response = self.mutate("/api/v1/guest/analysis", json={"answers": {}})
        self.assertEqual(response.status_code, 429)
        other = self.app.test_client()
        self.assertEqual(self.mutate("/api/v1/guest/analysis", client=other, json=[]).status_code, 400)
        for _ in range(53):
            self.assertEqual(self.mutate("/api/v1/guest/analysis", client=self.app.test_client(), json=[]).status_code, 400)
        self.assertEqual(self.mutate("/api/v1/guest/analysis", client=self.app.test_client(), json=[]).status_code, 429)

    def test_revision_guard_keeps_newer_guest_edits(self):
        self.upload()
        guest_id = self.guest_id()
        old = self.repository.load(guest_id)
        edited = {**old["draft"], "filename": "newer.txt"}
        self.assertTrue(self.repository.replace(guest_id, edited, old["revision"]))
        self.assertFalse(self.repository.replace(guest_id, old["draft"], old["revision"]))
        self.assertEqual(self.repository.load(guest_id)["draft"]["filename"], "newer.txt")


if __name__ == "__main__":
    unittest.main()
