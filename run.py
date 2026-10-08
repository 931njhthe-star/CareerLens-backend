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
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("BACKEND_PORT") or os.environ.get("PORT") or "5101"),
    )
    parser.add_argument("--host", default=os.environ.get("BACKEND_HOST") or "127.0.0.1")
    args = parser.parse_args()
    print(f"CareerLens API listening on {args.host}:{args.port}", flush=True)
    serve(
        create_app(),
        host=args.host,
        port=args.port,
        max_request_body_size=11 * 1024 * 1024,
        # Keep accepted resume requests below Waitress's disk-spill threshold.
        inbuf_overflow=12 * 1024 * 1024,
    )
