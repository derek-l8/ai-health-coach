"""Small private check-in service; no public hosting or provider connection."""

from __future__ import annotations

import ipaddress
import json
import secrets
import sqlite3
import ssl
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from ai_health_coach.checkins import (
    CheckInConflictError,
    CheckInStore,
    configuration_payload,
    private_database_path,
)
from ai_health_coach.study_protocol import EventConfiguration, StudyValidationError

MAX_BODY_BYTES = 16_384


class CheckInServer(ThreadingHTTPServer):
    """Bind one explicit address and authorize each API request."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        database: Path,
        configuration: EventConfiguration,
        *,
        certificate: Path | None = None,
        private_key: Path | None = None,
    ) -> None:
        ip = ipaddress.ip_address(address[0])
        if ip.version != 4 or ip.is_unspecified or ip.is_multicast:
            raise StudyValidationError(
                "bind an explicit loopback or private IPv4 address"
            )
        if not ip.is_loopback and not ip.is_private:
            raise StudyValidationError(
                "the check-in service only supports private access"
            )
        if bool(certificate) != bool(private_key):
            raise StudyValidationError(
                "HTTPS requires both certificate and private key"
            )
        if not ip.is_loopback and certificate is None:
            raise StudyValidationError("phone access requires an HTTPS certificate")
        self.database = private_database_path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        store = CheckInStore(self.database)
        store.close()
        self.configuration = configuration
        self.token = secrets.token_urlsafe(32)
        self.scheme = "https" if certificate else "http"
        self.tls_context = None
        super().__init__(address, CheckInHandler)
        try:
            if certificate:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                context.load_cert_chain(certificate, private_key)
                self.tls_context = context
        except BaseException:
            self.server_close()
            raise
        host, port = self.server_address
        self.allowed_hosts = {f"{host}:{port}"}
        if ip.is_loopback:
            self.allowed_hosts.add(f"localhost:{port}")
        self.url = f"{self.scheme}://{host}:{port}/#token={self.token}"

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(10)
        if self.tls_context is not None:
            try:
                connection = self.tls_context.wrap_socket(connection, server_side=True)
            except BaseException:
                connection.close()
                raise
        return connection, address


class CheckInHandler(BaseHTTPRequestHandler):
    """Serve packaged assets and one bounded, authenticated submission route."""

    server: CheckInServer

    def log_message(self, format: str, *args: object) -> None:
        # Default HTTP logs can disclose paths, identifiers, and health content.
        return

    def _reply(self, status: int, body: bytes, content_type: str) -> None:
        # Drain small rejected requests so closing the socket does not reset a
        # client that is still sending its body (notably on Windows).
        if self.command == "POST" and not getattr(self, "_body_read", False):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if 0 < length <= MAX_BODY_BYTES * 4:
                    self.rfile.read(length)
            except ValueError, OSError:
                pass
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; "
            "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: dict) -> None:
        self._reply(
            status, json.dumps(value).encode(), "application/json; charset=utf-8"
        )

    def _valid_host(self) -> bool:
        if self.headers.get("Host") not in self.server.allowed_hosts:
            self._json(403, {"error": "host is not allowed"})
            return False
        return True

    def _authorized(self, *, require_origin: bool = False) -> bool:
        if not self._valid_host():
            return False
        origin = self.headers.get("Origin")
        expected = f"{self.server.scheme}://{self.headers['Host']}"
        if (require_origin and not origin) or (origin and origin != expected):
            self._json(403, {"error": "origin is not allowed"})
            return False
        credential = self.headers.get("Authorization", "")
        if not secrets.compare_digest(
            credential.encode(), f"Bearer {self.server.token}".encode()
        ):
            self._json(401, {"error": "open the session link printed by the server"})
            return False
        return True

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/config":
            if self._authorized():
                self._json(200, configuration_payload(self.server.configuration))
            return
        if not self._valid_host():
            return
        assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/time.mjs": ("time.mjs", "text/javascript; charset=utf-8"),
        }
        if path not in assets:
            self._json(404, {"error": "not found"})
            return
        filename, content_type = assets[path]
        body = files("ai_health_coach").joinpath("web", filename).read_bytes()
        self._reply(200, body, content_type)

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/checkins":
            self._json(404, {"error": "not found"})
            return
        if not self._authorized(require_origin=True):
            return
        if self.headers.get_content_type() != "application/json":
            self._json(415, {"error": "send application/json"})
            return
        if self.headers.get("Transfer-Encoding"):
            self._json(400, {"error": "transfer encoding is not supported"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "invalid content length"})
            return
        if not 0 < length <= MAX_BODY_BYTES:
            self._json(413, {"error": "check-in exceeds the request size limit"})
            return
        store = None
        try:
            body = self.rfile.read(length)
            self._body_read = True
            request = json.loads(body)
            store = CheckInStore(self.server.database)
            payload, inserted = store.submit(
                request, self.server.configuration, datetime.now(UTC)
            )
        except (
            json.JSONDecodeError,
            UnicodeDecodeError,
            StudyValidationError,
        ) as error:
            self._json(400, {"error": str(error)})
            return
        except RecursionError:
            self._json(400, {"error": "check-in structure is too deeply nested"})
            return
        except CheckInConflictError as error:
            self._json(409, {"error": str(error)})
            return
        except sqlite3.Error:
            self._json(503, {"error": "storage unavailable; retry the same submission"})
            return
        finally:
            if store is not None:
                store.close()
        self._json(
            201 if inserted else 200,
            {
                "checkin_id": payload["checkin_id"],
                "captured_at": payload["label"]["captured_at"],
                "window_status": payload["window_status"],
                "replayed": not inserted,
            },
        )


def serve_checkins(
    database: Path,
    configuration: EventConfiguration,
    bind: str = "127.0.0.1",
    port: int = 8765,
    certificate: Path | None = None,
    private_key: Path | None = None,
) -> int:
    with CheckInServer(
        (bind, port),
        database,
        configuration,
        certificate=certificate,
        private_key=private_key,
    ) as server:
        print(f"Open this private session link: {server.url}", flush=True)
        print("Keep this terminal open. Press Ctrl+C to stop.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0
