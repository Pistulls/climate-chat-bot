"""Run the service locally against the dev data stores:

    uv run python -m climate_chat.service.local [--port 8000]

Each HTTP request becomes a Lambda function URL event for the same handler the Lambda runs.
Settings and secrets come from .env (see .env.example). Listens on 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import contextlib
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit


def to_event(method: str, path: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
    return {
        "rawPath": urlsplit(path).path,
        "requestContext": {"http": {"method": method}, "requestId": str(uuid.uuid4())},
        "headers": {k.lower(): v for k, v in headers.items()},
        "body": body.decode("utf-8") if body else None,
        "isBase64Encoded": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    from climate_chat.service.app import build_app

    app = build_app()

    class Handler(BaseHTTPRequestHandler):
        def _serve(self) -> None:
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

        do_GET = do_POST = do_PUT = do_DELETE = _serve

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Climate Chat service on http://127.0.0.1:{args.port}/api/chat (Ctrl-C to stop)")
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()


if __name__ == "__main__":
    main()
