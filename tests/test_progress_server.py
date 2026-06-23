import json
import unittest
import urllib.parse
import urllib.request

import progress_server


class TestBatchProgressRing(unittest.TestCase):
    def test_real_checkpoints_catch_up_smoothly_without_snap(self):
        page = progress_server._PROGRESS_PAGE

        self.assertNotIn("function snapToTarget()", page)
        self.assertNotIn("snapToTarget();", page)
        self.assertIn("var delta = targetPct - displayPct;", page)
        self.assertIn("var step = Math.max(1, Math.ceil(delta / 4));", page)
        self.assertIn("displayPct = Math.min(targetPct, displayPct + step);", page)
        self.assertIn("}, 250);", page)

    def test_batch_progress_uses_month_counts_not_percent_labels(self):
        page = progress_server._PROGRESS_PAGE

        self.assertIn('<span class="pct" id="ring-count">0/0</span>', page)
        self.assertNotIn('id="ring-pct"', page)
        self.assertNotIn("pct + '%'", page)
        self.assertNotIn("function setMidTarget(index)", page)
        self.assertNotIn("setMidTarget(d.index);", page)
        self.assertIn(
            "document.getElementById('ring-count').textContent = processed + '/' + total;",
            page,
        )


class TestHonestInitialState(unittest.TestCase):
    """The page must not claim states (authenticated / analyzing) that haven't happened."""

    def test_steps_hidden_until_authenticated(self):
        page = progress_server._PROGRESS_PAGE
        # The step list (Analyzing / Uploading) must not show before login — it
        # starts hidden and is only revealed on auth_ok.
        self.assertIn('<div id="single" class="steps hidden">', page)
        self.assertIn("document.getElementById('single').classList.remove('hidden');", page)

    def test_waiting_title_is_honest(self):
        page = progress_server._PROGRESS_PAGE
        self.assertIn('<h1 id="title">Waiting for sign-in&hellip;</h1>', page)

    def test_signin_button_has_auth_url_placeholder(self):
        page = progress_server._PROGRESS_PAGE
        self.assertIn('id="signin"', page)
        self.assertIn("__AUTH_URL__", page)

    def test_auth_ok_marks_authenticated(self):
        page = progress_server._PROGRESS_PAGE
        self.assertIn("authed = true;", page)

    def test_auth_timeout_handler_present(self):
        page = progress_server._PROGRESS_PAGE
        self.assertIn("addEventListener('auth_timeout'", page)


class TestFailedState(unittest.TestCase):
    """Upload failures must render as a distinct 'failed' state, not 'skip' or success."""

    def test_failed_visual_state_defined(self):
        page = progress_server._PROGRESS_PAGE
        self.assertIn(".pill.failed", page)
        self.assertIn(".step.failed", page)

    def test_error_msg_marks_failed_and_counts(self):
        page = progress_server._PROGRESS_PAGE
        self.assertIn("failed++;", page)
        self.assertIn("setMonthState(d.month, d.label, 'failed');", page)
        # 'skip' is still used for genuinely-empty windows, but failed is now distinct.
        self.assertIn("setMonthState(d.month, d.label, 'skip');", page)

    def test_showdone_uses_failed_count(self):
        page = progress_server._PROGRESS_PAGE
        self.assertIn("data.failed", page)
        self.assertIn("Partial upload", page)
        self.assertIn("Upload failed", page)

    def test_active_pill_icon_matches_single_month_spinner(self):
        page = progress_server._PROGRESS_PAGE
        self.assertIn(".pill.active .pi{animation:spin 1.2s linear infinite}", page)
        # batch mode reuses same animated refresh glyph as single-month mode.
        self.assertIn("if (state === 'active') icon = '\\u21BB';", page)


class TestDryRunDone(unittest.TestCase):
    """P3: showDone() must handle a dry-run done event without claiming
    'nothing to upload' — months were planned, just not uploaded."""

    def test_showdone_has_dryrun_branch(self):
        page = progress_server._PROGRESS_PAGE
        self.assertIn("if (data.dryRun)", page)
        self.assertIn("Dry run", page)

    def test_dryrun_branch_precedes_nothing_to_upload(self):
        """The dryRun branch must come BEFORE the 'Nothing to upload' fallback so
        a dry-run with planned months never falls through to it."""
        page = progress_server._PROGRESS_PAGE
        self.assertLess(page.index("if (data.dryRun)"), page.index("Nothing to upload"))


class TestAuthUrlInjection(unittest.TestCase):
    """The served page must embed the real auth_url so the sign-in button works."""

    def test_callback_page_injects_auth_url(self):
        auth_url = "https://mirdash.example.com/cli-auth?redirect_uri=x"
        server = progress_server.ProgressServer(port=8811, auth_url=auth_url)
        try:
            with urllib.request.urlopen(f"{server.url}/callback", timeout=5) as resp:
                body = resp.read().decode("utf-8")
        finally:
            server.shutdown(delay=0)
        self.assertIn(auth_url, body)
        self.assertNotIn("__AUTH_URL__", body)


class TestSSEBroadcast(unittest.TestCase):
    """Every connected SSE client must receive every event (no competitive queue),
    and a late-joining client must replay prior history (so it never misses auth_ok)."""

    def _read_events(self, url, expected, timeout=5):
        """Open an SSE stream and collect `expected` event lines, then close."""
        import time as _t
        events = []
        resp = urllib.request.urlopen(url, timeout=timeout)
        deadline = _t.time() + timeout
        while len(events) < expected and _t.time() < deadline:
            line = resp.readline().decode("utf-8")
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())
        resp.close()
        return events

    def test_two_clients_both_receive_event(self):
        server = progress_server.ProgressServer(port=8813)
        try:
            # Two concurrent SSE clients.
            r1 = urllib.request.urlopen(f"{server.url}/events", timeout=5)
            r2 = urllib.request.urlopen(f"{server.url}/events", timeout=5)
            server.push_event("auth_ok", {"message": "hi"})

            def first_event(resp):
                import time as _t
                deadline = _t.time() + 5
                while _t.time() < deadline:
                    line = resp.readline().decode("utf-8")
                    if line.startswith("event:"):
                        return line.split(":", 1)[1].strip()
                return None

            e1 = first_event(r1)
            e2 = first_event(r2)
            r1.close()
            r2.close()
            self.assertEqual(e1, "auth_ok")
            self.assertEqual(e2, "auth_ok")
        finally:
            server.shutdown(delay=0)

    def test_late_client_replays_history(self):
        server = progress_server.ProgressServer(port=8814)
        try:
            # Event pushed BEFORE any client connects.
            server.push_event("auth_ok", {"message": "hi"})
            server.push_event("analyzing", {"label": "2025-12"})
            events = self._read_events(f"{server.url}/events", expected=2)
            self.assertEqual(events[:2], ["auth_ok", "analyzing"])
        finally:
            server.shutdown(delay=0)


class TestUploadedFromCallback(unittest.TestCase):
    """Integration: GET /callback with uploaded param populates server.uploaded."""

    def _fetch_callback(self, server, qs):
        """GET /callback?<qs> and return the response body (discarded)."""
        with urllib.request.urlopen(f"{server.url}/callback?{qs}", timeout=5) as resp:
            resp.read()

    def test_callback_with_uploaded_populates_server_uploaded(self):
        """A valid uploaded param is parsed and stored on the server."""
        server = progress_server.ProgressServer(port=8821)
        try:
            uploaded_data = [{"monthKey": "2025-11", "uploadedAt": 1700000000}]
            qs = urllib.parse.urlencode({
                "token": "tok123",
                "uploaded": json.dumps(uploaded_data),
            })
            self._fetch_callback(server, qs)
            self.assertEqual(server.uploaded, uploaded_data)
        finally:
            server.shutdown(delay=0)

    def test_callback_without_uploaded_gives_empty_list(self):
        """When uploaded is absent from the callback, server.uploaded is []."""
        server = progress_server.ProgressServer(port=8822)
        try:
            self._fetch_callback(server, "token=tok456")
            self.assertEqual(server.uploaded, [])
        finally:
            server.shutdown(delay=0)

    def test_callback_with_malformed_uploaded_gives_empty_list(self):
        """Malformed uploaded JSON does not raise — server.uploaded is [] and token is captured."""
        server = progress_server.ProgressServer(port=8823)
        try:
            qs = urllib.parse.urlencode({
                "token": "tok789",
                "uploaded": "not-valid-json{{",
            })
            self._fetch_callback(server, qs)
            self.assertEqual(server.uploaded, [])
            # Tokens must still be captured despite bad uploaded.
            self.assertIsNotNone(server._tokens)
            self.assertIn("tok789", server._tokens)
        finally:
            server.shutdown(delay=0)


if __name__ == "__main__":
    unittest.main()
