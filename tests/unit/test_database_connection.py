"""Check DB isolation, token concurrency, and the PostgreSQL driver boundary."""
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import psycopg
from app.infrastructure.database.connection import Database
from app.infrastructure.database.auth_repository import AuthRepository
from app.infrastructure.database.draft_repository import DraftRepository


class DatabaseConnectionTests(unittest.TestCase):
    def test_sqlite_databases_belong_to_each_configuration(self):
        with TemporaryDirectory() as folder:
            first = DraftRepository(Path(folder) / 'first.sqlite3')
            second = DraftRepository(Path(folder) / 'second.sqlite3')
            first.save('same-user', {'company': 'Synthetic Team A'})
            self.assertEqual(first.load('same-user')['company'], 'Synthetic Team A')
            self.assertEqual(second.load('same-user')['company'], '')

    def test_reset_token_can_only_be_consumed_once_concurrently(self):
        with TemporaryDirectory() as folder:
            repo = AuthRepository(Path(folder) / 'auth.sqlite3')
            repo.create_user(dict(id='fixture', email='fixture@example.test', name='Fixture', password_hash='old-hash'))
            repo.create_reset('reset-digest', 'fixture', int(time.time()) + 60)
            def consume(_):
                return repo.consume_reset('reset-digest', 'new-hash', int(time.time()))
            with ThreadPoolExecutor(max_workers=2) as workers:
                self.assertEqual(sorted(workers.map(consume, range(2))), [False, True])

    def test_postgres_uses_private_schema_and_bound_values(self):
        initialize, transaction = MagicMock(), MagicMock()
        with patch('psycopg.connect') as connect:
            connect.side_effect = [initialize, transaction]
            db = Database('postgresql://fixture:placeholder@db.example.test/postgres')
            with db.connection() as connection:
                connection.execute('SELECT email FROM auth_users WHERE email=?', ("quote'@example.test",))
                raw = connection.raw
            initialize.execute.assert_any_call('CREATE SCHEMA IF NOT EXISTS careerlens', ())
            raw.execute.assert_any_call('SET search_path TO careerlens')
            raw.execute.assert_any_call('SELECT email FROM auth_users WHERE email=%s', ("quote'@example.test",))
            self.assertEqual(connect.call_args.kwargs['sslmode'], 'require')
            self.assertIsNone(connect.call_args.kwargs['prepare_threshold'])
            raw.commit.assert_called_once()
            raw.close.assert_called_once()

    def test_postgres_failures_do_not_echo_credentials(self):
        with patch('psycopg.connect', side_effect=psycopg.OperationalError('sensitive-password')):
            with self.assertRaises(RuntimeError) as error:
                Database('postgresql://fixture:sensitive-password@db.example.test/postgres')
            self.assertNotIn('sensitive-password', str(error.exception))

    def test_postgres_rolls_back_and_closes_on_error(self):
        initialize, transaction = MagicMock(), MagicMock()
        with patch('psycopg.connect', side_effect=[initialize, transaction]):
            db = Database('postgresql://fixture:placeholder@localhost/postgres')
            with self.assertRaises(ValueError):
                with db.connection():
                    raise ValueError('abort transaction')
            transaction.rollback.assert_called_once()
            transaction.close.assert_called_once()
            transaction.commit.assert_not_called()
