"""Contract test: the self-hosted dashboard against the REAL CLI parsers.

Exact CLI compatibility is the dashboard's top constraint, so this drives the
actual modules in gnomon/upload/ rather than re-stating their expectations in
TypeScript. A drift in query keys, the bearer scheme, the reportUrl key or the
302 status fails here instead of silently in someone's terminal.

Not picked up by `unittest discover` (its default pattern is test*.py); run it
explicitly against a running dashboard:

    TEAM_TOKEN=dev DASHBOARD_BASE=http://localhost:3000 pytest tests/dashboard_contract_test.py -v
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

import pytest

# REAL CLI modules — the contract must hold against these.
from gnomon.upload.auth import _tokens_from_query
from gnomon.upload.mirdash import (
    _history_from_query,
    _upload_summary,
    _uploaded_from_query,
)

BASE = os.environ.get("DASHBOARD_BASE", "http://localhost:3000")
TEAM_TOKEN = os.environ.get("TEAM_TOKEN", "dev")
CALLBACK = "http://127.0.0.1:9/callback"


def _login(count=2, email="contract@example.com"):
    """Submit what the CLI's browser step submits, then parse the redirect with
    the CLI's own parsers."""
    data = urllib.parse.urlencode({
        "team_token": TEAM_TOKEN,
        "name": "Contract Bot",
        "email": email,
        "redirect_uri": CALLBACK,
        "count": str(count),
    }).encode()
    req = urllib.request.Request(f"{BASE}/api/cli-auth", data=data, method="POST")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None  # keep the Location header instead of following it

    opener = urllib.request.build_opener(NoRedirect)
    try:
        opener.open(req)
        pytest.fail("expected a 302 redirect to the loopback callback")
    except urllib.error.HTTPError as exc:
        assert exc.code == 302, f"expected 302, got {exc.code}"
        location = exc.headers["Location"]

    # WHERE the tokens go is half the contract: the CLI only ever reads them off
    # its own loopback listener. A redirect carrying a perfectly-shaped tokens=
    # query to any other host would hand credentials to a third party and leave
    # the CLI waiting forever — and would pass every assertion below.
    target = urllib.parse.urlparse(location)
    expected = urllib.parse.urlparse(CALLBACK)
    assert (target.scheme, target.netloc, target.path) == (
        expected.scheme, expected.netloc, expected.path
    ), f"tokens were redirected to {target.scheme}://{target.netloc}{target.path}, not {CALLBACK}"

    return urllib.parse.parse_qs(target.query)


def test_callback_query_parses_with_the_cli_parsers():
    parsed = _login(count=2)

    tokens = _tokens_from_query(parsed)
    assert isinstance(tokens, list) and len(tokens) == 2
    assert all(isinstance(t, str) and t for t in tokens)
    # One credential per planned upload, not the same string N times.
    assert len(set(tokens)) == 2

    uploaded = _uploaded_from_query(parsed)
    assert isinstance(uploaded, list)


def test_upload_history_is_the_current_contract_generation():
    """A server that omits uploaded_history is parsed as 'legacy' and silently
    drops the CLI back to its pre-contract upload planner."""
    history = _history_from_query(_login(count=1))
    assert history["state"] == "valid", f"got {history['state']}"


def test_real_uploader_ingests_and_returns_a_report_url():
    tokens = _tokens_from_query(_login(count=1))
    summary = {
        # Tz-aware ISO bounds, as gnomon/sources/discovery.py produces them.
        "context": {
            "date_range": ["2026-01-01T00:00:00-03:00", "2026-06-30T00:00:00-03:00"],
            "total_sessions": 10,
            "total_prompts": 100,
            "window_months": 6,
        },
        "score_contract_id": "contract-test",
        "coverage": {"flag": "complete", "indexed": 10, "transcripts": 10},
        "profile": {
            "aq": {"aq_0_100": 88, "tier": "Advanced", "pillars": []},
            "scores": {},
            "model_usage": [],
        },
        "progression_monthly": [
            {"month": "2026-06", "models": [["claude-opus-4-8", 500]], "tokens_total": 1_000_000}
        ],
    }

    # The bearer header, the JSON body and the reportUrl parsing all come from
    # mirdash._upload_summary itself.
    report_url = _upload_summary(BASE, tokens[0], summary)
    assert isinstance(report_url, str), f"expected a legacy reportUrl string, got {report_url!r}"
    assert report_url.startswith("/p/"), report_url

    # After the upload the history the CLI reads back must include that month.
    history = _history_from_query(_login(count=1))
    assert "2026-06" in [m["monthKey"] for m in history["months"]]


def test_a_bad_token_surfaces_the_server_message():
    """The CLI prints the response body verbatim, so it has to be readable."""
    with pytest.raises(RuntimeError) as err:
        _upload_summary(BASE, "not-a-real-token", {"context": {}})
    assert "HTTP 401" in str(err.value)
