"""Job catalog behavior, privacy, validation, persistence and CSRF boundaries."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app import create_app


class JobPostingApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = {
            "TESTING": True,
            "SECRET_KEY": "catalog-test-only",
            "DATABASE": str(Path(self.temp.name) / "jobs.sqlite3"),
        }
        self.app = create_app(self.config)
        self.guest = self.app.test_client()
        self.alice = self.register("alice@example.test")
        self.bob = self.register("bob@example.test")
        self.payload = {
            "company": "내 연습 회사",
            "role": "Python 개발자",
            "location": "내 전용 지역",
            "employment_type": "계약직",
            "experience_level": "신입",
            "skills": ["Python", "SQLite"],
            "description": "주요업무\nPython API를 개발하고 SQL 데이터 모델을 설계합니다.\n자격요건\nGit 협업과 테스트 작성 경험이 필요합니다.",
            "source_url": "https://example.com/jobs/1",
        }

    def register(self, email):
        client = self.app.test_client()
        result = self.mutate(
            client,
            "POST",
            "/api/v1/auth/register",
            json={"email": email, "password": "Job-Catalog-test-2026!", "name": "테스트"},
        )
        self.assertEqual(result.status_code, 201)
        return client

    def mutate(self, client, method, url, **kwargs):
        token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
        return client.open(url, method=method, headers={"X-CSRF-Token": token}, **kwargs)

    def create(self, client=None):
        result = self.mutate(
            client or self.alice, "POST", "/api/v1/job-postings", json=self.payload
        )
        self.assertEqual(result.status_code, 201, result.get_json())
        return result.get_json()["posting"]

    def test_public_catalog_has_600_explicit_examples_and_safe_metadata(self):
        result = self.guest.get("/api/v1/job-postings?page_size=50").get_json()
        self.assertEqual(result["total"], 600)
        self.assertEqual(len({p["id"] for p in result["items"]}), 50)
        for page in range(2, 13):
            result["items"].extend(
                self.guest.get(f"/api/v1/job-postings?page_size=50&page={page}").get_json()["items"]
            )
        self.assertEqual(len(result["items"]), 600)
        self.assertEqual(len({posting["id"] for posting in result["items"]}), 600)
        for posting in result["items"]:
            self.assertEqual(posting["source_type"], "example")
            self.assertTrue(
                "예시 기업" in posting["company"] or posting["company"].startswith("가상 ")
            )
            self.assertIn("가상", posting["description"])
            self.assertTrue(posting["source_url"].startswith("https://"))
            self.assertNotIn("owner_id", posting)
            self.assertFalse(posting["is_owner"])
            self.assertFalse(posting["is_saved"])

    def test_role_filter_uses_db_titles_and_preserves_private_scope(self):
        self.payload["role"] = "백엔드 개발자 비공개"
        private = self.create()
        result = self.guest.get("/api/v1/job-postings?role_id=backend&page_size=50").get_json()
        self.assertGreater(result["total"], 0)
        self.assertLess(result["total"], 600)
        self.assertNotIn(private["id"], [item["id"] for item in result["items"]])
        self.assertTrue(
            all(
                any(term in item["role"].lower() for term in ["백엔드", "backend", "서버 개발"])
                for item in result["items"]
            )
        )
        self.assertEqual(self.guest.get("/api/v1/job-postings?role_id=unknown").status_code, 400)
        self.assertEqual(self.guest.get("/api/v1/job-postings?role_id=custom").status_code, 400)
        self.assertEqual(
            self.guest.get(
                "/api/v1/job-postings", query_string={"role_id": "custom", "role": "%' OR 1=1 --"}
            ).get_json()["total"],
            0,
        )

    def test_select_requires_auth_csrf_resume_and_current_visible_posting(self):
        posting = self.create()
        path = "/api/v1/job-postings/" + posting["id"] + "/select"
        self.assertEqual(self.mutate(self.guest, "POST", path, json={}).status_code, 401)
        self.assertEqual(self.mutate(self.bob, "POST", path, json={}).status_code, 404)
        self.assertEqual(self.alice.post(path, json={}).status_code, 403)
        self.assertEqual(self.mutate(self.alice, "POST", path, json={}).status_code, 400)
        self.assertEqual(
            self.mutate(
                self.alice, "POST", "/api/v1/job-postings/missing/select", json={}
            ).status_code,
            404,
        )

    def test_same_resume_yields_posting_specific_scores_and_resets_previous_report(self):
        resume = "Python과 Flask로 서버 API를 개발했습니다. SQL로 데이터 모델을 설계하고 조회 시간을 30% 줄였습니다. Git 협업과 테스트 작성을 담당했습니다."
        self.mutate(self.alice, "PUT", "/api/v1/resume", json={"resume_text": resume})
        self.mutate(self.alice, "PUT", "/api/v1/career-target", json={"role_id": "backend"})
        one = self.create()
        self.payload.update(
            role="브랜드 디자이너",
            description="주요업무\n브랜드 디자인과 시각 디자인을 담당합니다.\n자격요건\nFigma와 Illustrator로 그래픽 디자인을 수행한 경험이 필요합니다.",
        )
        two = self.create()
        scores = []
        for posting in [one, two]:
            response = self.mutate(
                self.alice,
                "POST",
                f"/api/v1/job-postings/{posting['id']}/select",
                json={"description": "조작된 클라이언트 내용"},
            )
            self.assertEqual(response.status_code, 200)
            draft = response.get_json()["draft"]
            self.assertEqual(draft["resume_text"], resume)
            self.assertEqual(draft["job_text"], posting["description"])
            self.assertEqual(draft["selected_posting_id"], posting["id"])
            self.assertEqual(draft["career_target"]["role_id"], "backend")
            self.assertIsNone(draft["report"])
            self.assertEqual(draft["answers"], {})
            report = self.mutate(
                self.alice, "POST", "/api/v1/analysis", json={"answers": {}}
            ).get_json()["report"]
            scores.append(report["score"])
            self.assertEqual([item["max_score"] for item in report["criteria"]], [70, 20, 10])
            self.assertEqual(report["score"], sum(item["score"] for item in report["criteria"]))
        self.assertGreater(scores[0], scores[1])

    def test_filtering_pagination_empty_results_and_literal_search(self):
        first = self.guest.get("/api/v1/job-postings?page_size=5").get_json()
        second = self.guest.get("/api/v1/job-postings?page_size=5&page=2").get_json()
        self.assertEqual(len(first["items"]), 5)
        self.assertTrue(
            {p["id"] for p in first["items"]}.isdisjoint(p["id"] for p in second["items"])
        )
        result = self.guest.get(
            "/api/v1/job-postings",
            query_string={
                "q": "python",
                "location": "서울",
                "employment_type": "정규직",
                "experience_level": "신입",
                "skill": "python",
                "page_size": "50",
            },
        ).get_json()
        self.assertIn("example-backend-python", [p["id"] for p in result["items"]])
        self.assertTrue(
            all(
                p["location"] == "서울" and p["employment_type"] == "정규직"
                for p in result["items"]
            )
        )
        self.assertEqual(self.guest.get("/api/v1/job-postings?page=100").get_json()["items"], [])
        self.payload["description"] += "\n근무조건\n가상 검토 진행률 50%_완료 표기를 사용합니다."
        literal = self.create()
        for query in ("%", "_"):
            result = self.alice.get("/api/v1/job-postings", query_string={"q": query}).get_json()
            self.assertEqual(result["total"], 1)
            self.assertEqual(result["items"][0]["id"], literal["id"])
        self.assertEqual(
            self.guest.get("/api/v1/job-postings", query_string={"q": "' OR 1=1 --"}).get_json()[
                "total"
            ],
            0,
        )

    def test_private_create_update_delete_and_cross_account_isolation(self):
        posting = self.create()
        path = "/api/v1/job-postings/" + posting["id"]
        self.assertTrue(posting["is_owner"])
        self.assertEqual(posting["source_type"], "manual")
        for client in (self.guest, self.bob):
            self.assertEqual(client.get(path).status_code, 404)
            listing = client.get("/api/v1/job-postings?page_size=50").get_json()
            self.assertEqual(listing["total"], 600)
            self.assertNotIn("내 전용 지역", listing["filters"]["locations"])
        for method, suffix in (
            ("PUT", ""),
            ("DELETE", ""),
            ("POST", "/bookmark"),
            ("DELETE", "/bookmark"),
        ):
            self.assertEqual(
                self.mutate(self.bob, method, path + suffix, json=self.payload).status_code, 404
            )
        changed = {**self.payload, "role": "데이터 개발자", "skills": ["SQL", "Python"]}
        result = self.mutate(self.alice, "PUT", path, json=changed)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()["posting"]["role"], "데이터 개발자")
        self.assertEqual(result.get_json()["posting"]["skills"], changed["skills"])
        self.mutate(self.alice, "POST", path + "/bookmark")
        self.assertEqual(
            self.mutate(self.alice, "DELETE", path).get_json(),
            {"deleted": True, "id": posting["id"]},
        )
        self.assertEqual(self.alice.get(path).status_code, 404)
        self.assertEqual(self.alice.get("/api/v1/job-postings?saved=1").get_json()["total"], 0)

    def test_bookmarks_are_idempotent_persisted_and_account_private(self):
        path = "/api/v1/job-postings/example-backend-python"
        for _ in range(2):
            self.assertTrue(
                self.mutate(self.alice, "POST", path + "/bookmark").get_json()["posting"][
                    "is_saved"
                ]
            )
        self.assertEqual(self.alice.get("/api/v1/job-postings?saved=1").get_json()["total"], 1)
        self.assertEqual(self.bob.get("/api/v1/job-postings?saved=1").get_json()["total"], 0)
        self.assertFalse(self.guest.get(path).get_json()["posting"]["is_saved"])
        with self.alice.session_transaction() as session:
            owner = session["user_id"]
        restarted = create_app(self.config)
        self.assertEqual(
            restarted.extensions["jobs_service"].list({"saved": "1"}, owner)["total"], 1
        )
        self.assertEqual(restarted.extensions["jobs_service"].list({})["total"], 600)
        for _ in range(2):
            self.assertFalse(
                self.mutate(self.alice, "DELETE", path + "/bookmark").get_json()["posting"][
                    "is_saved"
                ]
            )

    def test_examples_cannot_be_modified_or_deleted(self):
        for method in ("PUT", "DELETE"):
            self.assertEqual(
                self.mutate(
                    self.alice,
                    method,
                    "/api/v1/job-postings/example-backend-python",
                    json=self.payload,
                ).status_code,
                404,
            )

    def test_example_refresh_preserves_bookmarks_and_user_owned_content(self):
        manual = self.create()
        example = self.guest.get("/api/v1/job-postings/example-backend-python").get_json()[
            "posting"
        ]
        self.mutate(self.alice, "POST", "/api/v1/job-postings/example-backend-python/bookmark")
        repository = self.app.extensions["jobs_service"].repository
        repository.seed(
            [
                {**example, "role": "수정된 예시 직무", "skills": ["Python", "SQL"]},
                {**manual, "role": "잘못된 덮어쓰기"},
            ]
        )
        refreshed = self.alice.get("/api/v1/job-postings/example-backend-python").get_json()[
            "posting"
        ]
        self.assertEqual(refreshed["role"], "수정된 예시 직무")
        self.assertEqual(refreshed["skills"], ["Python", "SQL"])
        self.assertTrue(refreshed["is_saved"])
        self.assertEqual(
            self.alice.get("/api/v1/job-postings/" + manual["id"]).get_json()["posting"], manual
        )

    def test_auth_and_csrf_required_for_mutation(self):
        self.assertEqual(self.guest.get("/api/v1/job-postings?saved=1").status_code, 401)
        for method, path in (
            ("POST", "/api/v1/job-postings"),
            ("PUT", "/api/v1/job-postings/example-backend-python"),
            ("DELETE", "/api/v1/job-postings/example-backend-python"),
            ("POST", "/api/v1/job-postings/example-backend-python/bookmark"),
        ):
            self.assertEqual(
                self.guest.open(path, method=method, json=self.payload).status_code, 401
            )
            self.assertEqual(
                self.alice.open(path, method=method, json=self.payload).status_code, 403
            )

    def test_invalid_input_preserves_existing_posting(self):
        posting = self.create()
        path = "/api/v1/job-postings/" + posting["id"]
        cases = [
            [],
            None,
            {**self.payload, "company": ""},
            {**self.payload, "description": "short"},
            {**self.payload, "skills": "Python"},
            {**self.payload, "skills": ["x"] * 21},
            {**self.payload, "source_url": "javascript:alert(1)"},
            {**self.payload, "source_url": "file:///tmp/a"},
            {**self.payload, "source_url": "https://user:secret@example.com"},
            {**self.payload, "source_url": "https://example.com:bad/path"},
            {**self.payload, "source_url": "https://example.com/\npath"},
        ]
        for payload in cases:
            result = self.mutate(
                self.alice, "PUT", path, data=json.dumps(payload), content_type="application/json"
            )
            self.assertEqual(result.status_code, 400, payload)
            self.assertEqual(self.alice.get(path).get_json()["posting"], posting)

    def test_invalid_query_values_are_rejected(self):
        for query in (
            {"page": "0"},
            {"page": "-1"},
            {"page": "1.5"},
            {"page_size": "51"},
            {"saved": "yes"},
            {"page": "10000000"},
            {"q": "a" * 201},
        ):
            self.assertEqual(
                self.guest.get("/api/v1/job-postings", query_string=query).status_code, 400, query
            )

    def test_forged_owner_and_source_type_are_ignored(self):
        result = self.mutate(
            self.alice,
            "POST",
            "/api/v1/job-postings",
            json={
                **self.payload,
                "owner_id": "someone-else",
                "source_type": "example",
                "id": "example-backend-python",
            },
        )
        posting = result.get_json()["posting"]
        self.assertTrue(posting["id"].startswith("manual-"))
        self.assertEqual(posting["source_type"], "manual")
        self.assertTrue(posting["is_owner"])
        self.assertNotIn("owner_id", posting)

    def test_selection_uses_existing_resume_to_analysis_flow(self):
        self.assertEqual(self.mutate(self.alice, "POST", "/api/v1/example").status_code, 200)
        posting = self.guest.get("/api/v1/job-postings/example-backend-python").get_json()[
            "posting"
        ]
        selected = self.mutate(
            self.alice,
            "PUT",
            "/api/v1/job",
            json={
                "company": posting["company"],
                "role": posting["role"],
                "job_text": posting["description"],
            },
        )
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(selected.get_json()["draft"]["job_text"], posting["description"])
        self.assertEqual(
            self.mutate(self.alice, "POST", "/api/v1/analysis", json={"answers": {}}).status_code,
            200,
        )


if __name__ == "__main__":
    unittest.main()
