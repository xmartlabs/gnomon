import io
import inspect
import unittest
from unittest.mock import patch

from gnomon.upload import auth
from gnomon.upload import progress_server
from gnomon.upload.progress_server import ProgressServer


class _FakeAuthServer:
    instance = None

    def __init__(self, address, handler_cls):
        self.handler_cls = handler_cls
        self.timeout = None
        self.body = None
        _FakeAuthServer.instance = self

    def handle_request(self):
        handler = self.handler_cls.__new__(self.handler_cls)
        handler.path = "/callback?token=test-token"
        handler.wfile = io.BytesIO()
        handler.send_response = lambda status: None
        handler.send_header = lambda name, value: None
        handler.end_headers = lambda: None
        handler.do_GET()
        self.body = handler.wfile.getvalue()

    def server_close(self):
        pass


class TestAuthBrand(unittest.TestCase):
    def test_capture_cli_token_renders_custom_brand(self):
        with patch.object(auth.http.server, "HTTPServer", _FakeAuthServer):
            tokens, history = auth._capture_cli_token(port=12345, timeout=1, brand="Acme Gnomon")

        body = _FakeAuthServer.instance.body.decode("utf-8")
        self.assertEqual(tokens, ["test-token"])
        self.assertEqual(history["state"], "legacy")
        self.assertIn("<title>Acme Gnomon — authenticated</title>", body)
        self.assertIn("> Acme Gnomon</div>", body)
        self.assertNotIn("xl-ai-insights", body)


class TestProgressBrand(unittest.TestCase):
    def test_progress_page_renders_custom_brand_and_labels(self):
        body = progress_server._render_progress_page(
            brand="Acme Gnomon", auth_url="https://dashboard.example/cli-auth"
        )

        self.assertIn("<title>Acme Gnomon — syncing</title>", body)
        self.assertIn("> Acme Gnomon</div>", body)
        self.assertIn(">Sign in<", body)
        self.assertIn(">Upload<", body)
        self.assertIn("Uploading…", body)
        self.assertNotIn("xl-ai-insights", body)
        self.assertNotIn("Sign in with mirdash", body)
        self.assertNotIn("Upload to mirdash", body)
        self.assertNotIn("Uploading to mirdash", body)

    def test_progress_server_accepts_brand_keyword(self):
        self.assertIn("brand", inspect.signature(ProgressServer.__init__).parameters)


if __name__ == "__main__":
    unittest.main()
