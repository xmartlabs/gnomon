import os
import re
from datetime import datetime

from gnomon.sources.discovery import ANTIGRAVITY_DB


def _pb_varint(buf, i):
    val = shift = 0
    while i < len(buf):
        b = buf[i]; i += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, i
        shift += 7
    raise ValueError("truncated varint")


def _pb_fields(buf):
    """Decode one protobuf message into [(field_no, wire_type, value)]. Raises on
    malformed input -- callers treat any raise as 'not a message'."""
    i, out = 0, []
    while i < len(buf):
        key, i = _pb_varint(buf, i)
        f, w = key >> 3, key & 7
        if f == 0:
            raise ValueError("field 0")
        if w == 0:
            v, i = _pb_varint(buf, i)
        elif w == 1:
            v, i = buf[i:i + 8], i + 8
        elif w == 2:
            ln, i = _pb_varint(buf, i)
            if i + ln > len(buf):
                raise ValueError("truncated bytes")
            v, i = buf[i:i + ln], i + ln
        elif w == 5:
            v, i = buf[i:i + 4], i + 4
        else:
            raise ValueError(f"wire type {w}")
        out.append((f, w, v))
    return out


_UUID_RX = re.compile(rb"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def antigravity_summary():
    """Best-effort read of Antigravity's local conversation metadata. Returns
    {"conversations": n, "first": iso, "last": iso} or None. Fully local, read-only."""
    if not os.path.exists(ANTIGRAVITY_DB):
        return None
    try:
        import sqlite3
        import base64
        con = sqlite3.connect(f"file:{ANTIGRAVITY_DB}?mode=ro&immutable=1", uri=True)
        row = con.execute("SELECT value FROM ItemTable WHERE key="
                          "'jetskiStateSync.agentManagerInitState'").fetchone()
        con.close()
        if not row or not row[0]:
            return None
        raw = row[0]
        buf = base64.b64decode(raw if isinstance(raw, (bytes, bytearray)) else str(raw))
        tmin = tmax = None

        def _scan_ts(b, depth=0):
            nonlocal tmin, tmax
            if depth > 6:
                return
            for _f, w, v in _pb_fields(b):
                if w == 0 and 1.3e9 < v < 2.2e9:        # plausible unix seconds
                    ts = datetime.fromtimestamp(v).astimezone()
                    tmin = ts if tmin is None or ts < tmin else tmin
                    tmax = ts if tmax is None or ts > tmax else tmax
                elif w == 2:
                    try:
                        _scan_ts(v, depth + 1)
                    except Exception:
                        pass

        convs = 0
        for f, w, root in _pb_fields(buf):
            if f != 1 or w != 2:
                continue
            try:
                children = _pb_fields(root)
            except Exception:
                continue
            for cf, cw, cv in children:
                if cf != 1 or cw != 2:
                    continue
                try:
                    inner = _pb_fields(cv)
                except Exception:
                    continue
                # a conversation record leads with its uuid as field 1
                if any(g == 1 and gw == 2 and _UUID_RX.match(gv)
                       for g, gw, gv in inner):
                    convs += 1
                    _scan_ts(cv)
        if not convs:
            return None
        return {"conversations": convs,
                "first": tmin.isoformat() if tmin else None,
                "last": tmax.isoformat() if tmax else None}
    except Exception:
        return None
