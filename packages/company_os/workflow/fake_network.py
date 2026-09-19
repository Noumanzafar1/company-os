"""One local-only HTTP fixture per execution, with no configurable host/URL."""

import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from uuid import UUID

from company_os.long_contracts import LongSpec


class FakeNetwork:
    def __init__(
        self, execution_id: UUID, spec: LongSpec, accept: Callable[[], dict[str, Any]]
    ) -> None:
        self.stop = threading.Event()
        stop = self.stop

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: Any) -> None:
                pass

            def do_GET(self) -> None:
                if self.path != "/" + str(execution_id):
                    self.send_error(404)
                    return
                if spec.handler in {"network_hang", "transient_read_timeout"}:
                    stop.wait(185)
                    return
                if spec.handler == "network_drop":
                    return
                if spec.handler == "network_delayed" and stop.wait(spec.duration_seconds):
                    return
                try:
                    receipt = accept()
                except Exception:
                    self.send_error(409)
                    return
                if spec.handler == "fake_remote_accept_then_hang":
                    stop.wait(185)
                    return
                payload = (
                    b"broken"
                    if spec.handler == "network_malformed"
                    else json.dumps(receipt).encode()
                )
                try:
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except OSError:
                    pass

        class BoundedServer(HTTPServer):
            def get_request(self) -> Any:
                connection, address = super().get_request()
                connection.settimeout(2)
                return connection, address

        self.server = BoundedServer(("127.0.0.1", 0), Handler)
        self.server.timeout = 0.1
        self.port = self.server.server_port

        def serve() -> None:
            while not self.stop.is_set():
                self.server.handle_request()

        self.thread = threading.Thread(target=serve, daemon=True, name="synthetic-loopback")
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=6)
        self.server.server_close()
        if self.thread.is_alive():
            raise RuntimeError("FAKE_SERVER_CLEANUP_FAILED")
