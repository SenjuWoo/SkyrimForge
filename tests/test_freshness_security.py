"""A GitHub token must never leave HTTPS api.github.com, including on redirects."""
from __future__ import annotations

import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from scripts import check_freshness


class _FakeResponse:
    def __init__(self, payload: bytes = b"{}") -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc) -> None:
        return None


class FreshnessSecurityTests(unittest.TestCase):
    def call(self, url: str) -> urllib.request.Request:
        captured: list[urllib.request.Request] = []

        def fake(request, timeout=0):
            captured.append(request)
            return _FakeResponse()

        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "SENTINEL"}, clear=False), \
                mock.patch.object(check_freshness._OPENER, "open", side_effect=fake):
            check_freshness._get_json(url)
        return captured[0]

    def test_https_github_receives_the_token(self) -> None:
        request = self.call("https://api.github.com/repos/x/y")
        self.assertEqual(request.get_header("Authorization"), "Bearer SENTINEL")

    def test_plain_http_never_receives_the_token(self) -> None:
        request = self.call("http://api.github.com/repos/x/y")
        self.assertIsNone(request.get_header("Authorization"))

    def test_another_host_never_receives_the_token(self) -> None:
        request = self.call("https://github.com/repos/x/y")
        self.assertIsNone(request.get_header("Authorization"))

    def test_cross_origin_redirect_is_refused_without_forwarding(self) -> None:
        hits: list[str | None] = []

        class Target(BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args, **kwargs):
                pass

        target = ThreadingHTTPServer(("127.0.0.1", 0), Target)
        threading.Thread(target=target.serve_forever, daemon=True).start()

        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{target.server_port}/target")
                self.end_headers()

            def log_message(self, *args, **kwargs):
                pass

        source = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        threading.Thread(target=source.serve_forever, daemon=True).start()
        try:
            request = urllib.request.Request(f"http://127.0.0.1:{source.server_port}/r",
                                             headers={"Authorization": "Bearer SENTINEL"})
            with self.assertRaises(urllib.error.HTTPError):
                check_freshness._OPENER.open(request, timeout=5)
            self.assertEqual(hits, [])
        finally:
            source.shutdown()
            target.shutdown()
            source.server_close()
            target.server_close()

    def test_same_origin_redirect_is_followed(self) -> None:
        class Same(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/r":
                    self.send_response(302)
                    self.send_header("Location", "/ok")
                    self.end_headers()
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args, **kwargs):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Same)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/r")
            with check_freshness._OPENER.open(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
