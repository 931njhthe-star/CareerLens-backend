"""Resolve database configuration independently from private runtime files."""

from pathlib import Path
from urllib.parse import unquote


def local_path(value, base_dir):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (Path(base_dir) / path).resolve()


def database_location(value, base_dir, data_dir):
    value = str(value or "").strip()
    if not value:
        return str(Path(data_dir) / "careerlens.sqlite3")
    if value.startswith("postgres://"):
        return "postgresql://" + value[len("postgres://") :]
    if value.startswith("postgresql://"):
        return value
    if value.startswith("sqlite:///"):
        value = unquote(value[len("sqlite:///") :])
        if "?" in value or "#" in value:
            raise ValueError("SQLite DATABASE_URL에는 쿼리나 fragment를 넣지 마세요.")
    elif "://" in value:
        raise ValueError(
            "DATABASE_URL은 sqlite:/// 파일 경로 또는 postgresql:// 연결 주소여야 합니다."
        )
    if not value or value == ":memory:":
        raise ValueError("사용자 자료를 저장할 SQLite 파일 경로를 지정해 주세요.")
    return str(local_path(value, base_dir))


def is_postgres(value):
    return str(value).startswith(("postgresql://", "postgres://"))
