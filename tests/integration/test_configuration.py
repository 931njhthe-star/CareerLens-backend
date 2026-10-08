import os
import runpy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app import create_app
from app.core.config import database_location


class ConfigurationTests(unittest.TestCase):
    def test_standalone_server_never_spools_accepted_upload_bodies(self):
        with (
            patch("sys.argv", ["run.py"]),
            patch("dotenv.load_dotenv"),
            patch("app.create_app"),
            patch("waitress.serve") as serve,
            patch("builtins.print"),
        ):
            runpy.run_path(str(Path(__file__).resolve().parents[2] / "run.py"), run_name="__main__")
        self.assertEqual(serve.call_args.kwargs["max_request_body_size"], 11 * 1024 * 1024)
        self.assertGreater(
            serve.call_args.kwargs["inbuf_overflow"], serve.call_args.kwargs["max_request_body_size"]
        )

    def test_sqlite_url_uses_repo_base_independent_of_working_directory(self):
        with TemporaryDirectory() as folder:
            base = Path(folder).resolve()
            resolved = database_location(
                "sqlite:///./data/team%20test.sqlite3", base, base / "runtime"
            )
            self.assertEqual(Path(resolved), base / "data/team test.sqlite3")

    def test_explicit_test_database_overrides_external_database_url(self):
        with (
            TemporaryDirectory() as folder,
            patch.dict(os.environ, {"DATABASE_URL": "postgresql://unreachable.invalid/private"}),
        ):
            database = Path(folder).resolve() / "local.sqlite3"
            app = create_app({"TESTING": True, "SECRET_KEY": "test-key", "DATABASE": str(database)})
            self.assertEqual(app.config["DATABASE"], str(database))
            self.assertEqual(app.config["DATA_DIR"], str(Path(folder).resolve()))
            self.assertTrue(database.is_file())
            self.assertEqual(app.test_client().get("/api/v1/health").status_code, 200)

    def test_postgres_url_uses_independent_local_secret_and_mail_paths(self):
        with (
            TemporaryDirectory() as folder,
            patch("app.application.auth.AuthRepository") as auth_repository,
            patch(
                "app.infrastructure.database.draft_repository.SqliteDraftRepository"
            ) as draft_repository,
            patch("app.infrastructure.database.job_repository.JobRepository") as job_repository,
            patch("app.infrastructure.database.guest_repository.GuestRepository") as guest_repository,
            patch(
                "app.infrastructure.database.resume_example_repository.ResumeExampleRepository"
            ) as resume_repository,
            patch(
                "psycopg.connect",
                side_effect=AssertionError(
                    "Configuration tests must not open external connections"
                ),
            ) as connect,
        ):
            data_dir = Path(folder).resolve() / "private-files"
            app = create_app(
                {
                    "TESTING": True,
                    "SECRET_KEY": None,
                    "DATABASE_URL": "postgres://user:placeholder@db.example.invalid:5432/postgres",
                    "DATA_DIR": str(data_dir),
                    "MAIL_OUTBOX": "",
                }
            )
            self.assertEqual(
                app.config["DATABASE"],
                "postgresql://user:placeholder@db.example.invalid:5432/postgres",
            )
            self.assertEqual(app.config["MAIL_OUTBOX"], str(data_dir / "mail"))
            self.assertEqual((data_dir / "session.key").read_text(encoding="ascii"), app.secret_key)
            self.assertFalse((data_dir / "careerlens.sqlite3").exists())
            for repository in (
                auth_repository,
                draft_repository,
                job_repository,
                guest_repository,
                resume_repository,
            ):
                repository.assert_called_once_with(app.config["DATABASE"])
            resume_repository.return_value.refresh_packaged.assert_called_once()
            connect.assert_not_called()

    def test_blank_database_creates_new_local_store_and_reuses_session_key(self):
        with TemporaryDirectory() as folder:
            config = {"TESTING": True, "DATABASE_URL": "", "DATA_DIR": folder, "SECRET_KEY": None}
            first = create_app(config)
            second = create_app(config)
            self.assertEqual(first.secret_key, second.secret_key)
            self.assertEqual(
                first.config["DATABASE"], str(Path(folder).resolve() / "careerlens.sqlite3")
            )
            self.assertTrue(Path(first.config["DATABASE"]).is_file())

    def test_unsupported_or_memory_database_fails_before_filesystem_use(self):
        with TemporaryDirectory() as folder:
            for value in (
                "https://example.invalid",
                "sqlite:///:memory:",
                "sqlite:///x.sqlite3?mode=ro",
            ):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    database_location(value, folder, folder)


if __name__ == "__main__":
    unittest.main()
