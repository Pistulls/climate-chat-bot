"""Run the service locally against the dev data stores:

    uv run python -m climate_chat.service.local [--port 8000]

Each HTTP request becomes a Lambda function URL event for the same handler the Lambda runs.
Settings and secrets come from .env (see .env.example). Listens on 127.0.0.1 only.

One extra, local-only route: GET /api/logs pages through the request logs (LOGS_TABLE) for
the UI's dev-only /logs page. The Lambda never serves it: the logs hold every visitor's
comments, and the public site has no sign-in.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import uuid
from datetime import UTC, date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from climate_chat.service.logs import BadCursor, read_logs

LOGS_PATH = "/api/logs"
LOGS_PAGE_DEFAULT = 25
LOGS_PAGE_MAX = 100


def to_event(method: str, path: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
    return {
        "rawPath": urlsplit(path).path,
        "requestContext": {"http": {"method": method}, "requestId": str(uuid.uuid4())},
        "headers": {k.lower(): v for k, v in headers.items()},
        "body": body.decode("utf-8") if body else None,
        "isBase64Encoded": False,
    }


def serve_logs(app: Any, query: str, today: date) -> tuple[int, dict[str, Any]]:
    """GET /api/logs?limit=25&cursor=... -> (status, JSON body)."""
    params = parse_qs(query)
    try:
        limit = int(params.get("limit", [str(LOGS_PAGE_DEFAULT)])[0])
    except ValueError:
        return 400, {"error": "bad_request", "message": "limit must be a number."}
    limit = max(1, min(limit, LOGS_PAGE_MAX))
    cursor = params.get("cursor", [None])[0]
    try:
        page = read_logs(
            app.log_table,
            today=today,
            days=app.settings.log_ttl_days,
            limit=limit,
            cursor=cursor,
        )
    except BadCursor:
        return 400, {"error": "bad_cursor", "message": "That page link is invalid."}
    except Exception as e:  # local only, so the reason is safe to show: usually AWS sign-in
        hint = " Sign in to AWS (aws sso login) and try again." if "token" in str(e).lower() else ""
        return 503, {
            "error": "logs_unavailable",
            "message": f"Couldn't read {app.settings.logs_table}: {e}.{hint}",
        }
    return 200, {"table": app.settings.logs_table, **page}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    from climate_chat.service.app import build_app

    app = build_app()

    class Handler(BaseHTTPRequestHandler):
        def _serve(self) -> None:
            url = urlsplit(self.path)
            if self.command == "GET" and url.path == LOGS_PATH:
                status, payload = serve_logs(app, url.query, datetime.now(UTC).date())
                self._json(status, payload)
                return
            length = int(self.headers.get("content-length") or 0)
            event = to_event(self.command, self.path, dict(self.headers), self.rfile.read(length))
            response = app.handle(event, None)
            body = response["body"].encode()
            self.send_response(response["statusCode"])
            for key, value in response["headers"].items():
                self.send_header(key, value)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("cache-control", "no-store")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = do_PUT = do_DELETE = _serve

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Climate Chat service on http://127.0.0.1:{args.port}/api/chat (Ctrl-C to stop)")
    print(f"Request logs (local only) on http://127.0.0.1:{args.port}{LOGS_PATH}")
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()


if __name__ == "__main__":
    main()
