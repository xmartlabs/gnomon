"""Build deterministic multi-month copies of the source fixtures."""

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List


HERE = os.path.dirname(os.path.abspath(__file__))


def _month_suffix(month: str) -> str:
    if not re.match(r"^\d{4}-\d{2}$", month):
        raise ValueError("month must be YYYY-MM")
    try:
        datetime.strptime(month + "-15", "%Y-%m-%d")
    except ValueError:
        raise ValueError("month must be a valid YYYY-MM")
    return month.replace("-", "")


def _shift_timestamp(value: str, month: str) -> str:
    match = re.match(r"^\d{4}-\d{2}-\d{2}(.*)$", value)
    if not match:
        return value
    return month + "-15" + match.group(1)


def _rewrite(value: Any, month: str, session_suffix: str,
             in_session_meta: bool = False) -> Any:
    if isinstance(value, list):
        return [_rewrite(item, month, session_suffix, in_session_meta)
                for item in value]
    if not isinstance(value, dict):
        return value

    rewritten: Dict[str, Any] = {}
    for key, item in value.items():
        if key == "timestamp" and isinstance(item, str):
            item = _shift_timestamp(item, month)
        elif key == "sessionId" and isinstance(item, str):
            item = item + "-" + session_suffix
        elif (in_session_meta and key == "id" and isinstance(item, str)):
            # Codex stores the session identity as payload.id rather than a
            # sessionId field in its session_meta record.
            item = item + "-" + session_suffix
        rewritten[key] = _rewrite(item, month, session_suffix,
                                   in_session_meta=(key == "payload"
                                                    and value.get("type") == "session_meta"))
    return rewritten


def _copy_corpus(root: str, source: str, months: List[str]) -> str:
    destination = os.path.join(root, source)
    source_root = os.path.join(HERE, "fixtures", source)
    os.makedirs(destination, exist_ok=True)

    for month in months:
        suffix = _month_suffix(month)
        month_root = os.path.join(destination, month)
        for dirpath, _dirnames, filenames in os.walk(source_root):
            relative = os.path.relpath(dirpath, source_root)
            target_dir = month_root if relative == "." else os.path.join(month_root, relative)
            os.makedirs(target_dir, exist_ok=True)
            for filename in sorted(filenames):
                if not filename.endswith(".jsonl"):
                    continue
                source_path = os.path.join(dirpath, filename)
                target_path = os.path.join(target_dir, filename)
                with open(source_path, "r", encoding="utf-8") as handle:
                    lines = handle.readlines()
                with open(target_path, "w", encoding="utf-8") as handle:
                    for line in lines:
                        if not line.strip():
                            handle.write(line)
                            continue
                        record = json.loads(line)
                        record = _rewrite(record, month, suffix)
                        handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    return destination


def claude_corpus_across_months(root: str, months: List[str]) -> str:
    """Copy the Claude fixtures once per month and return a patched BASE path."""
    return _copy_corpus(root, "claude", months)


def codex_corpus_across_months(root: str, months: List[str]) -> str:
    """Copy the Codex fixtures once per month and return a patched CODEX_DIR."""
    return _copy_corpus(root, "codex", months)
