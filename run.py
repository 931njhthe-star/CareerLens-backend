"""Standalone local API entrypoint. Start the frontend for the user interface."""
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from waitress import serve
from app import create_app


if __name__ == "__main__":
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    parser = argparse.ArgumentParser(description="Run the local CareerLens API")
    parser.add_argument("--port", type=int, default=int(os.environ.get("BACKEND_PORT") or "5101"))
    port = parser.parse_args().port
    print(f"CareerLens API: http://127.0.0.1:{port}", flush=True)
    serve(create_app(), host="127.0.0.1", port=port, max_request_body_size=11 * 1024 * 1024)
