from __future__ import annotations

import argparse
import json
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api import RAGAPI, ServiceNotReadyError
from src.core.config import Settings


class Handler(BaseHTTPRequestHandler):
    service: RAGAPI

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/healthz":
            self._write(HTTPStatus.NOT_FOUND, {"error": "route not found"})
            return
        self._write(HTTPStatus.OK, {"status": "ok"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/process":
            self._write(HTTPStatus.NOT_FOUND, {"error": "route not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1_048_576:
                raise ValueError("request body must be between 1 and 1048576 bytes")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            self._write(HTTPStatus.OK, self.service.process(payload))
        except (ValueError, json.JSONDecodeError) as error:
            self._write(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception:  # Do not disclose local document or model details to callers.
            self._write(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "RAG processing failed"})

    def log_message(self, format: str, *args: object) -> None:
        print(f"rag-api {self.address_string()} {format % args}")

    def _write(self, status: HTTPStatus, value: dict) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the local Tender Hack RAG pipeline to the backend.")
    parser.add_argument("--host", default=os.getenv("RAG_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("RAG_PORT", "8000")))
    args = parser.parse_args()
    try:
        Handler.service = RAGAPI.from_settings(Settings())
    except ServiceNotReadyError as error:
        raise SystemExit(str(error)) from error
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"RAG API listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
