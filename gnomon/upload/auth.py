import http.server
import json
import time
import urllib.parse

from gnomon.upload.mirdash import _uploaded_from_query


def _tokens_from_query(parsed_qs):
    """Extract a list of tokens from a parse_qs result dict.

    Looks for 'tokens' first (JSON array); falls back to single 'token'.
    Returns [] if neither is present.  Never raises.
    """
    # Try the batch key first
    raw_tokens = (parsed_qs.get("tokens") or [""])[0]
    if raw_tokens:
        try:
            tokens = json.loads(raw_tokens)
            if isinstance(tokens, list) and tokens:
                return [str(t) for t in tokens]
        except Exception:
            pass  # malformed JSON — fall through to single-token path

    # Fall back to single token
    token = (parsed_qs.get("token") or [""])[0]
    if token:
        return [token]
    return []


# How long _capture_cli_token waits for the browser auth callback before giving up.
_SHARE_AUTH_TIMEOUT = 120
# Web mode keeps a live progress page that offers in-page re-login, so the
# server must outlive a single missed callback. Give the user time to notice,
# close a stray tab, and sign in again without the callback landing on a dead
# port. The user can always Ctrl-C to abort sooner.
_WEB_AUTH_TIMEOUT = 600


_SUCCESS_PAGE = b"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>xl-ai-insights \xe2\x80\x94 authenticated</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Outfit:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
  :root{
    --bg-base:#1a1f27; --bg-surface:#222831; --bg-elev:#2a3038;
    --text-primary:#f0f0f0; --text-secondary:#c7cacf; --text-muted:#85888f;
    --border:rgba(255,255,255,.078); --accent:#ee1a64; --purple:#5d5fee;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{height:100%}
  body{
    background:var(--bg-base);color:var(--text-primary);
    font-family:'Outfit',system-ui,sans-serif;min-height:100vh;
    display:flex;align-items:center;justify-content:center;
    position:relative;overflow:hidden;
  }
  body::before{content:"";position:absolute;top:-30%;right:-10%;width:60vw;height:60vw;
    border-radius:50%;background:radial-gradient(circle,rgba(238,26,100,.16),transparent 60%);
    filter:blur(40px);pointer-events:none}
  body::after{content:"";position:absolute;bottom:-30%;left:-10%;width:55vw;height:55vw;
    border-radius:50%;background:radial-gradient(circle,rgba(93,95,238,.14),transparent 60%);
    filter:blur(40px);pointer-events:none}
  .card{position:relative;z-index:1;width:100%;max-width:460px;margin:24px;
    background:var(--bg-surface);border:1px solid var(--border);border-radius:20px;
    padding:44px 40px;box-shadow:0 2px 8px rgba(0,0,0,.24),0 18px 42px rgba(0,0,0,.28);
    text-align:center}
  .brand{display:flex;align-items:center;justify-content:center;gap:9px;
    font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:15px;
    letter-spacing:-.01em;color:var(--text-secondary);margin-bottom:30px}
  .brand .dot{width:9px;height:9px;border-radius:50%;
    background:linear-gradient(135deg,var(--accent),var(--purple))}
  .check{width:64px;height:64px;border-radius:50%;margin:0 auto 22px;
    display:flex;align-items:center;justify-content:center;
    background:rgba(238,26,100,.12);border:1px solid rgba(238,26,100,.25);
    box-shadow:0 0 0 6px rgba(238,26,100,.05)}
  .check svg{width:30px;height:30px;stroke:var(--accent);stroke-width:2.5;fill:none;
    stroke-linecap:round;stroke-linejoin:round}
  h1{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:26px;
    letter-spacing:-.02em;margin-bottom:12px}
  p.sub{font-size:14.5px;line-height:1.55;color:var(--text-secondary);margin-bottom:26px}
  .term{display:flex;align-items:center;justify-content:center;gap:10px;
    background:var(--bg-elev);border:1px solid var(--border);border-radius:12px;
    padding:13px 16px;font-size:13px;color:var(--text-secondary);
    font-family:'JetBrains Mono',monospace}
  .term svg{width:15px;height:15px;stroke:var(--purple);stroke-width:2;fill:none;
    stroke-linecap:round;stroke-linejoin:round;flex:none}
  .foot{margin-top:22px;font-size:12px;line-height:1.5;color:var(--text-muted)}
  .foot b{color:var(--text-secondary);font-weight:600}
</style>
</head>
<body>
  <div class="card">
    <div class="brand"><span class="dot"></span> xl-ai-insights \xc2\xb7 mirdash</div>
    <div class="check"><svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg></div>
    <h1>You\xe2\x80\x99re authenticated</h1>
    <p class="sub">Signed in with your XL account. Close this tab and head back to your terminal \xe2\x80\x94 it\xe2\x80\x99s computing your build profile and sharing it now.</p>
    <div class="term"><svg viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg> Return to your terminal</div>
    <div class="foot"><b>Prompts and file contents stay on your machine.</b> summary.json includes aggregated usage plus raw skill, MCP server, and model identifiers \xe2\x80\x94 mirdash uses it to generate your recommendations.</div>
  </div>
</body>
</html>
"""


def _capture_cli_token(port=8799, timeout=_SHARE_AUTH_TIMEOUT):
    """Start a one-shot HTTP server on 127.0.0.1:<port>.

    Waits up to *timeout* seconds for a single GET /callback?token=<JWT>
    (and optionally tokens=<url-encoded JSON array>).

    Returns a tuple (tokens, uploaded) where tokens is a list of token strings
    on success (at least one element) or None on timeout or error, and uploaded
    is a list of already-uploaded month dicts (may be empty).
    """
    import http.server

    captured = {}

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            tokens = _tokens_from_query(params)
            if parsed.path == "/callback" and tokens:
                captured["tokens"] = tokens
                captured["uploaded"] = _uploaded_from_query(params)
                body = _SUCCESS_PAGE
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, fmt, *args):  # noqa: suppress access log
            pass

    try:
        server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
        server.timeout = 1  # poll interval for the outer loop
    except OSError as exc:
        print(f"  warning: could not bind localhost:{port} for auth callback: {exc}")
        return (None, [])

    deadline = time.time() + timeout
    try:
        while "tokens" not in captured:
            if time.time() > deadline:
                print(f"  warning: timed out waiting for auth callback after {timeout}s")
                return (None, [])
            server.handle_request()
    finally:
        server.server_close()

    return (captured.get("tokens"), captured.get("uploaded") or [])


_ORIGINAL_CAPTURE_CLI_TOKEN = _capture_cli_token


def _wait_for_auth_tokens(server, port):
    """Prefer progress-server auth, but keep legacy token mocks usable in tests.

    Always returns just the token list (not the uploaded state) — the ProgressServer
    path stores uploaded in server._uploaded; the mock path stashes it there too.
    """
    if _capture_cli_token is not _ORIGINAL_CAPTURE_CLI_TOKEN:
        result = _capture_cli_token(port=port, timeout=_SHARE_AUTH_TIMEOUT)
        # Normalize: updated mocks return (tokens, uploaded); legacy mocks return list.
        if isinstance(result, tuple):
            tokens, uploaded = result
            server._uploaded = uploaded
        else:
            tokens = result
            server._uploaded = []
        return tokens
    return server.wait_for_auth(timeout=_WEB_AUTH_TIMEOUT)
