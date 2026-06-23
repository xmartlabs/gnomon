"""Local progress server for xl-ai-insights.

Extends the one-shot auth callback into a multi-request HTTP server that:
- Captures the auth token from mirdash's redirect
- Serves a progress page with real-time SSE updates
- Shuts down after work completes

No external dependencies — Python 3 stdlib only.
"""

import html
import http.server
import json
import queue
import sys
import threading
import time
import urllib.parse

from gnomon.upload.mirdash import _uploaded_from_query


def _tokens_from_query(parsed_qs):
    raw_tokens = (parsed_qs.get("tokens") or [""])[0]
    if raw_tokens:
        try:
            tokens = json.loads(raw_tokens)
            if isinstance(tokens, list) and tokens:
                return [str(t) for t in tokens]
        except Exception:
            pass
    token = (parsed_qs.get("token") or [""])[0]
    if token:
        return [token]
    return []


_PROGRESS_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>xl-ai-insights — syncing</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Outfit:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
:root{
  --bg-base:#1a1f27;--bg-surface:#222831;--bg-elev:#2a3038;
  --text-primary:#f0f0f0;--text-secondary:#c7cacf;--text-muted:#85888f;
  --border:rgba(255,255,255,.078);--accent:#ee1a64;--accent-light:rgba(238,26,100,.14);
  --purple:#5d5fee;--ok:#34d399;--danger:#f87171;--warn:#fbbf24;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{
  background:var(--bg-base);color:var(--text-primary);
  font-family:'Outfit',system-ui,sans-serif;
  display:flex;align-items:center;justify-content:center;
  position:relative;overflow:hidden;
}
body::before{content:"";position:absolute;top:-30%;right:-10%;width:60vw;height:60vw;
  border-radius:50%;background:radial-gradient(circle,rgba(238,26,100,.16),transparent 60%);
  filter:blur(40px);pointer-events:none}
body::after{content:"";position:absolute;bottom:-30%;left:-10%;width:55vw;height:55vw;
  border-radius:50%;background:radial-gradient(circle,rgba(93,95,238,.14),transparent 60%);
  filter:blur(40px);pointer-events:none}

.card{
  position:relative;z-index:1;width:100%;max-width:460px;margin:24px;
  background:var(--bg-surface);border:1px solid var(--border);border-radius:20px;
  padding:40px 36px;box-shadow:0 2px 8px rgba(0,0,0,.24),0 18px 42px rgba(0,0,0,.28);
  text-align:center;
}
.brand{display:flex;align-items:center;justify-content:center;gap:9px;
  font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:15px;
  letter-spacing:-.01em;color:var(--text-secondary);margin-bottom:26px}
.brand .dot{width:9px;height:9px;border-radius:50%;
  background:linear-gradient(135deg,var(--accent),var(--purple))}

/* --- Icon wrappers --- */
.icon-wrap{width:56px;height:56px;border-radius:50%;margin:0 auto 18px;
  display:flex;align-items:center;justify-content:center;transition:all .4s ease}
.icon-wrap svg{width:26px;height:26px;stroke-width:2.5;fill:none;
  stroke-linecap:round;stroke-linejoin:round}
.icon-progress{background:var(--accent-light);border:1px solid rgba(238,26,100,.25)}
.icon-progress svg{stroke:var(--accent)}
.icon-done{background:rgba(52,211,153,.12);border:1px solid rgba(52,211,153,.25)}
.icon-done svg{stroke:var(--ok)}

h1{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:22px;
  letter-spacing:-.02em;margin-bottom:6px;transition:color .4s}
.sub{font-size:13px;line-height:1.5;color:var(--text-secondary);margin-bottom:4px}

/* --- Steps (single month) --- */
.steps{margin-top:20px;text-align:left;padding:0 4px}
.step{display:flex;align-items:center;gap:11px;padding:10px 0;
  border-bottom:1px solid var(--border);font-size:13px;transition:all .3s}
.step:last-child{border-bottom:none}
.step .si{width:22px;height:22px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;flex-shrink:0;font-size:11px;transition:all .3s}
.step.done .si{background:rgba(52,211,153,.12);color:var(--ok)}
.step.active .si{background:var(--accent-light);color:var(--accent)}
.step.pending .si{background:var(--bg-elev);color:var(--text-muted)}
.step.done{color:var(--text-secondary)}
.step.active{color:var(--text-primary);font-weight:500}
.step.pending{color:var(--text-muted)}

/* Spinner for active step */
.step.active .si{animation:spin 1.2s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

/* Failed step */
.step.failed{color:var(--danger)}
.step.failed .si{background:rgba(248,113,113,.14);color:var(--danger)}

/* Sign-in fallback button */
.signin{display:none;margin:14px auto 4px;padding:11px 20px;border-radius:10px;
  font-family:'Outfit',sans-serif;font-weight:600;font-size:14px;text-decoration:none;
  color:#fff;background:linear-gradient(135deg,var(--accent),var(--purple));
  box-shadow:0 6px 18px rgba(238,26,100,.28);transition:transform .15s,box-shadow .15s}
.signin:not(.hidden){display:inline-block}
.signin:hover{transform:translateY(-1px);box-shadow:0 8px 22px rgba(238,26,100,.36)}

/* --- Batch progress --- */
.batch{display:none}
.batch .ring{width:72px;height:72px;margin:0 auto 14px;position:relative}
.batch .ring svg{width:100%;height:100%;transform:rotate(-90deg)}
.batch .ring .track{fill:none;stroke:var(--bg-elev);stroke-width:5}
.batch .ring .fill{fill:none;stroke:url(#grad);stroke-width:5;stroke-linecap:round;
  transition:stroke-dashoffset .5s ease}
.batch .pct{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:17px}

.pill-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:14px;padding:0 2px}
.pill{border-radius:8px;padding:6px 4px;text-align:center;
  font-family:'JetBrains Mono',monospace;font-size:10px;transition:all .3s}
.pill.done{background:rgba(52,211,153,.1);color:var(--ok);border:1px solid rgba(52,211,153,.2)}
.pill.active{background:var(--accent-light);color:var(--accent);border:1px solid rgba(238,26,100,.3);font-weight:600}
.pill.pending{background:var(--bg-elev);color:var(--text-muted);border:1px solid transparent}
.pill.skip{background:transparent;color:var(--text-muted);border:1px solid var(--border);opacity:.5;
  text-decoration:line-through;font-size:9px}
.pill.failed{background:rgba(248,113,113,.1);color:var(--danger);border:1px solid rgba(248,113,113,.28);font-weight:600}
.pill .pi{display:block;font-size:12px;margin-bottom:2px}
.pill.active .pi{animation:uprise .85s ease-in-out infinite}
@keyframes uprise{
  0%,100%{transform:translateY(0)}
  50%{transform:translateY(-2px)}
}

/* --- Done state --- */
.redir{display:inline-flex;align-items:center;gap:6px;
  font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--purple);
  background:rgba(93,95,238,.08);border:1px solid rgba(93,95,238,.18);
  border-radius:8px;padding:8px 14px;margin-top:14px}
.redir .blink{animation:blink 1.2s step-end infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}

.privacy{margin-top:18px;font-size:11px;line-height:1.5;color:var(--text-muted);
  max-width:380px;margin-left:auto;margin-right:auto}
.privacy b{color:var(--text-secondary);font-weight:600}
.privacy code{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-secondary)}

.hidden{display:none!important}
</style>
</head>
<body>
<svg style="position:absolute;width:0;height:0"><defs>
  <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="#ee1a64"/><stop offset="100%" stop-color="#5d5fee"/>
  </linearGradient>
</defs></svg>

<div class="card">
  <div class="brand"><span class="dot"></span> xl-ai-insights &middot; mirdash</div>

  <!-- Icon (switches between progress and done) -->
  <div id="icon" class="icon-wrap icon-progress">
    <svg id="icon-spin" viewBox="0 0 24 24"><path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"/></svg>
    <svg id="icon-check" class="hidden" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>
  </div>

  <h1 id="title">Waiting for sign-in&hellip;</h1>
  <p class="sub" id="subtitle"></p>

  <!-- Sign-in fallback (revealed if auth hasn't arrived) -->
  <a id="signin" class="signin hidden" href="__AUTH_URL__">Sign in with mirdash</a>

  <!-- Single-month steps (hidden until authenticated — no fake progress pre-login) -->
  <div id="single" class="steps hidden">
    <div class="step done" id="step-auth"><span class="si">&check;</span> <span class="label">Authenticated</span></div>
    <div class="step active" id="step-analyze"><span class="si">&circlearrowleft;</span> <span class="label">Analyzing metrics&hellip;</span></div>
    <div class="step pending" id="step-upload"><span class="si">&middot;</span> <span class="label">Upload to mirdash</span></div>
  </div>

  <!-- Batch progress -->
  <div id="batch" class="batch">
    <div class="ring">
      <svg viewBox="0 0 80 80">
        <circle class="track" cx="40" cy="40" r="35"/>
        <circle class="fill" id="ring-fill" cx="40" cy="40" r="35"
          stroke-dasharray="219.9" stroke-dashoffset="219.9"/>
      </svg>
      <span class="pct" id="ring-count">0/0</span>
    </div>
    <p class="sub" id="batch-sub">months processed</p>
    <div class="pill-grid" id="pill-grid"></div>
  </div>

  <!-- Redirect badge (hidden until done) -->
  <div id="redir" class="redir hidden">
    <span>&rarr; <span id="redir-url"></span></span>
    <span class="blink">&hellip;</span>
  </div>

  <div class="privacy"><b>Your transcripts never leave your machine.</b> Only aggregated usage statistics (<code>summary.json</code>) are uploaded &mdash; mirdash uses them to generate your recommendations.</div>
</div>

<script>
(function(){
  const CIRC = 2 * Math.PI * 35; // ring circumference
  let isBatch = false;
  let total = 1;
  let processed = 0;
  let failed = 0;
  let monthEls = {};
  let mirdashBase = '';
  let authed = false;

  // Reveal the sign-in fallback if auth hasn't arrived shortly after load.
  // Covers the case where the user closed the mirdash login tab and only has
  // this progress page open — they can re-trigger login without re-running.
  setTimeout(function() {
    if (!authed) {
      var btn = document.getElementById('signin');
      if (btn && btn.getAttribute('href') && btn.getAttribute('href') !== '__AUTH_URL__') {
        document.getElementById('subtitle').textContent = 'Login didn\\u2019t open? Sign in to continue.';
        btn.classList.remove('hidden');
      }
    }
  }, 3500);

  function setStep(id, state) {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = 'step ' + state;
    const si = el.querySelector('.si');
    if (state === 'done') si.textContent = '\\u2713';
    else if (state === 'active') si.textContent = '\\u21BB';
    else if (state === 'failed') si.textContent = '\\u2715';
    else si.textContent = '\\u00B7';
  }

  var targetPct = 0;
  var displayPct = 0;
  var tickId = null;

  function renderRing(pct) {
    document.getElementById('ring-fill').setAttribute('stroke-dashoffset', CIRC * (1 - pct / 100));
  }

  function updateRing() {
    targetPct = total > 0 ? Math.round(processed / total * 100) : 0;
    document.getElementById('ring-count').textContent = processed + '/' + total;
    document.getElementById('batch-sub').textContent = processed === 1 ? 'month processed' : 'months processed';
  }

  function startTicker() {
    if (tickId) return;
    tickId = setInterval(function() {
      if (displayPct < targetPct) {
        var delta = targetPct - displayPct;
        var step = Math.max(1, Math.ceil(delta / 4));
        displayPct = Math.min(targetPct, displayPct + step);
        renderRing(displayPct);
      }
    }, 250);
  }

  var MN = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function shortMonth(label) {
    var parts = label.split('-');
    return MN[parseInt(parts[1], 10) - 1] || label;
  }

  function initBatch(months) {
    total = months.length;
    isBatch = true;
    document.getElementById('single').classList.add('hidden');
    document.getElementById('icon').classList.add('hidden');
    document.getElementById('batch').style.display = 'block';
    var grid = document.getElementById('pill-grid');
    months.forEach(function(m) {
      var el = document.createElement('div');
      el.className = 'pill pending';
      el.innerHTML = '<span class="pi">\\u00B7</span>' + shortMonth(m);
      grid.appendChild(el);
      monthEls[m] = el;
    });
    updateRing();
    startTicker();
  }

  function setMonthState(month, label, state) {
    var el = monthEls[month];
    if (!el) return;
    el.className = 'pill ' + state;
    var icon = '\\u00B7';
    if (state === 'done') icon = '\\u2713';
    else if (state === 'active') icon = '\\u21BB';
    else if (state === 'skip') icon = '\\u2014';
    else if (state === 'failed') icon = '\\u2715';
    el.innerHTML = '<span class="pi">' + icon + '</span>' + shortMonth(month);
  }

  function showDone(data) {
    const icon = document.getElementById('icon');
    icon.classList.remove('hidden');
    document.getElementById('icon-spin').classList.add('hidden');
    document.getElementById('icon-check').classList.remove('hidden');

    const uploaded = data.uploaded || 0;
    const failedCount = data.failed || 0;
    const h1 = document.getElementById('title');
    const sub = document.getElementById('subtitle');

    if (data.dryRun) {
      // Dry run: no uploads happened, but months were planned. Don't claim
      // "nothing to upload" — point the user at the terminal for the plan.
      icon.className = 'icon-wrap icon-done';
      h1.textContent = 'Dry run';
      h1.style.color = 'var(--ok)';
      sub.textContent = 'See the terminal for the upload plan \\u2014 nothing was uploaded.';
    } else if (uploaded > 0 && failedCount > 0) {
      // Partial: some uploaded, some failed.
      icon.className = 'icon-wrap icon-progress';
      icon.style.background = 'rgba(251,191,36,.12)';
      icon.style.borderColor = 'rgba(251,191,36,.3)';
      document.getElementById('icon-check').style.stroke = 'var(--warn)';
      h1.textContent = 'Partial upload';
      h1.style.color = 'var(--warn)';
      sub.textContent = uploaded + (uploaded === 1 ? ' month uploaded' : ' months uploaded') + ', ' +
        failedCount + (failedCount === 1 ? ' failed' : ' failed') + ' \\u2014 check your terminal.';
    } else if (failedCount > 0) {
      // Total failure.
      icon.className = 'icon-wrap icon-progress';
      icon.style.background = 'rgba(248,113,113,.12)';
      icon.style.borderColor = 'rgba(248,113,113,.3)';
      document.getElementById('icon-check').style.stroke = 'var(--danger)';
      h1.textContent = 'Upload failed';
      h1.style.color = 'var(--danger)';
      sub.textContent = 'Upload failed \\u2014 check your terminal.';
      if (!isBatch) setStep('step-upload', 'failed');
    } else if (uploaded > 0) {
      icon.className = 'icon-wrap icon-done';
      h1.textContent = 'Profile updated!';
      h1.style.color = 'var(--ok)';
      sub.textContent = uploaded + (uploaded === 1 ? ' month' : ' months') + ' uploaded successfully.';
    } else {
      icon.className = 'icon-wrap icon-progress';
      h1.textContent = 'Nothing to upload';
      h1.style.color = 'var(--text-muted)';
      sub.textContent = 'No activity found in the selected period.';
    }

    if (!isBatch && uploaded > 0 && failedCount === 0) {
      setStep('step-upload', 'done');
    }

    if (data.reportUrl) {
      const fullUrl = data.mirdashBase
        ? data.mirdashBase.replace(/\\/$/, '') + '/' + data.reportUrl.replace(/^\\//, '')
        : data.reportUrl;
      const redir = document.getElementById('redir');
      document.getElementById('redir-url').textContent = fullUrl.replace(/^https?:\\/\\//, '');
      redir.classList.remove('hidden');
      if (!data.noOpen) {
        setTimeout(function(){ window.location = fullUrl; }, 2000);
      }
    }
  }

  const es = new EventSource('/events');

  es.addEventListener('auth_ok', function(e) {
    const data = JSON.parse(e.data);
    authed = true;
    mirdashBase = data.mirdashBase || '';
    var btn = document.getElementById('signin');
    if (btn) btn.classList.add('hidden');
    document.getElementById('title').textContent = 'Processing\\u2026';
    document.getElementById('subtitle').textContent = '';
    if (data.months && data.months.length > 1) {
      initBatch(data.months);
    } else {
      // Reveal the steps only now that auth actually happened.
      document.getElementById('single').classList.remove('hidden');
    }
  });

  es.addEventListener('analyzing', function(e) {
    const d = JSON.parse(e.data);

    if (isBatch) {
      document.getElementById('title').textContent = 'Processing metrics';
      setMonthState(d.month, d.label, 'active');
    } else {
      document.getElementById('title').textContent = 'Processing ' + d.label;
      setStep('step-analyze', 'active');
    }
  });

  es.addEventListener('uploading', function(e) {
    const d = JSON.parse(e.data);
    if (!isBatch) {
      setStep('step-analyze', 'done');
      setStep('step-upload', 'active');
      document.querySelector('#step-upload .label').textContent = 'Uploading to mirdash\\u2026';
    } else {
      setMonthState(d.month, d.label, 'active');
    }
  });

  es.addEventListener('uploaded', function(e) {
    const d = JSON.parse(e.data);
    processed++;
    if (isBatch) {
      setMonthState(d.month, d.label, 'done');
      updateRing();
    } else {
      setStep('step-upload', 'done');
    }
  });

  es.addEventListener('skipped', function(e) {
    const d = JSON.parse(e.data);
    processed++;
    if (isBatch) {
      setMonthState(d.month, d.label, 'skip');
      updateRing();
    }
  });

  es.addEventListener('error_msg', function(e) {
    const d = JSON.parse(e.data);
    processed++;
    failed++;
    if (isBatch) {
      setMonthState(d.month, d.label, 'failed');
      updateRing();
    } else {
      setStep('step-analyze', 'done');
      setStep('step-upload', 'failed');
      var lbl = document.querySelector('#step-upload .label');
      if (lbl) lbl.textContent = 'Upload failed';
    }
  });

  es.addEventListener('done', function(e) {
    const d = JSON.parse(e.data);
    es.close();
    if (tickId) { clearInterval(tickId); tickId = null; }
    if (isBatch) { updateRing(); displayPct = targetPct; renderRing(displayPct); }
    showDone(d);
  });

  es.addEventListener('auth_timeout', function(e) {
    authed = false;
    if (tickId) { clearInterval(tickId); tickId = null; }
    setStep('step-auth', 'failed');
    var lbl = document.querySelector('#step-auth .label');
    if (lbl) lbl.textContent = 'Sign-in expired';
    document.getElementById('title').textContent = 'Sign-in expired';
    document.getElementById('title').style.color = 'var(--text-muted)';
    document.getElementById('subtitle').textContent = 'Re-run the command or sign in above.';
    var btn = document.getElementById('signin');
    if (btn && btn.getAttribute('href') && btn.getAttribute('href') !== '__AUTH_URL__') {
      btn.classList.remove('hidden');
    }
  });

  es.onerror = function() {
    // Server shut down unexpectedly — show a fallback message.
    // If we never authenticated, this is likely the auth window closing; keep
    // the sign-in affordance honest rather than implying work was in progress.
    es.close();
    if (authed) {
      document.getElementById('title').textContent = 'Connection lost';
      document.getElementById('subtitle').textContent = 'Check your terminal for results.';
    }
  };
})();
</script>
</body>
</html>
"""


class ProgressServer:
    """Local HTTP server for auth callback and SSE progress updates."""

    def __init__(self, port=8799, auth_url=""):
        self._port = port
        self._auth_url = auth_url
        self._auth_event = threading.Event()
        self._tokens = None
        self._uploaded = []
        # SSE is broadcast: every connected client gets its own queue, and
        # push_event fans out to all of them. A history buffer lets a client
        # that connects late (or after navigating, e.g. in-page re-login) catch
        # up on prior events — crucially `auth_ok`. A single shared queue would
        # split events across tabs, leaving the UI stuck mid-flow.
        self._clients = []
        self._history = []
        self._clients_lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._server = None
        self._thread = None

        parent = self

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/callback":
                    self._handle_callback(parsed)
                elif parsed.path == "/events":
                    self._handle_sse()
                elif parsed.path == "/":
                    self.send_response(302)
                    self.send_header("Location", "/callback")
                    self.end_headers()
                else:
                    self.send_response(404)
                    self.end_headers()

            def _handle_callback(self, parsed):
                params = urllib.parse.parse_qs(parsed.query)
                tokens = _tokens_from_query(params)
                if tokens and not parent._auth_event.is_set():
                    parent._tokens = tokens
                    parent._uploaded = _uploaded_from_query(params)
                    parent._auth_event.set()
                page = _PROGRESS_PAGE.replace(
                    "__AUTH_URL__", html.escape(parent._auth_url, quote=True)
                )
                body = page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _handle_sse(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                # Register this client and snapshot history atomically so no
                # event is missed or duplicated between replay and registration.
                client_q = queue.Queue()
                with parent._clients_lock:
                    backlog = list(parent._history)
                    parent._clients.append(client_q)

                def _send(evt):
                    line = f"event: {evt['type']}\ndata: {json.dumps(evt['data'])}\n\n"
                    self.wfile.write(line.encode("utf-8"))
                    self.wfile.flush()

                try:
                    for evt in backlog:
                        _send(evt)
                    while not parent._shutdown_event.is_set():
                        try:
                            _send(client_q.get(timeout=15))
                        except queue.Empty:
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    with parent._clients_lock:
                        try:
                            parent._clients.remove(client_q)
                        except ValueError:
                            pass

            def log_message(self, fmt, *args):
                pass

        class _QuietThreadingHTTPServer(http.server.ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                # Browser tabs navigating away / reloading reset their sockets;
                # that's expected churn for the SSE + re-login flow, not a fault.
                exc = sys.exc_info()[1]
                if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
                    return
                super().handle_error(request, client_address)

        self._server = _QuietThreadingHTTPServer(("127.0.0.1", port), _Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self):
        return f"http://localhost:{self._port}"

    @property
    def uploaded(self):
        """Return the list of already-uploaded month dicts from the auth callback."""
        return self._uploaded

    def wait_for_auth(self, timeout=120):
        """Block until auth callback arrives. Returns token list or None."""
        if self._auth_event.wait(timeout=timeout):
            return self._tokens
        return None

    def push_event(self, event_type, data):
        """Broadcast an SSE event to all connected clients and record history."""
        evt = {"type": event_type, "data": data}
        with self._clients_lock:
            self._history.append(evt)
            for client_q in self._clients:
                client_q.put(evt)

    def shutdown(self, delay=1.0):
        """Stop the server after a short delay (lets browser receive final events)."""
        time.sleep(delay)
        self._shutdown_event.set()
        self._server.shutdown()
        self._server.server_close()
