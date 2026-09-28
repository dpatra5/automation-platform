"""``apitest`` / ``python -m apitest``: run the API server."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from apitest.config import Settings
from apitest.main import create_app

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="apitest", description="Run the API Testing Tool server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None, help="default 8002 [env: APIT_PORT]")
    parser.add_argument("--db", default=None, help="SQLAlchemy URL [env: APIT_DB_URL]")
    parser.add_argument("--static-dir", default=None, help="serve the built frontend [env: APIT_STATIC_DIR]")
    parser.add_argument(
        "--allow-no-auth",
        action="store_true",
        help="permit a non-loopback host without APIT_TOKEN (not recommended)",
    )
    args = parser.parse_args(argv)

    settings = Settings.from_env(
        port=args.port,
        db_url=args.db,
        static_dir=Path(args.static_dir) if args.static_dir else None,
    )
    if args.host not in _LOOPBACK and not settings.token and not args.allow_no_auth:
        parser.error("refusing to bind a non-loopback host without APIT_TOKEN (see --allow-no-auth)")
    uvicorn.run(create_app(settings), host=args.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
