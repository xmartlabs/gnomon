#!/usr/bin/env python3
"""Legacy entrypoint. Prefer: xl-ai-insights --local."""

import importlib as _importlib
import os as _os
import sys as _sys
import types as _types

from gnomon.cli.local import *  # noqa: F401,F403
from gnomon.cli.local import main as _gnomon_main

_script_dir = _os.path.dirname(_os.path.abspath(__file__))
OUT_DIR = _script_dir if _os.path.isdir(_script_dir) and not _script_dir.startswith("/dev") else _os.getcwd()

# Private names that tests access via paxel._ — not exported by wildcard import
from gnomon.config import _pretty_model, _client_version  # noqa: F401
from gnomon.taxonomy import _canon_tool, _extract_clis, _is_compounding_path, _SKILL_MD_RX, _COMPOUNDING_RX  # noqa: F401
from gnomon.sources.discovery import _resolve_source_dir, _DIR_FLAGS, _AGENT_UNSUPPORTED_SOURCES  # noqa: F401
from gnomon.sources.codex import _codex_events, _codex_is_injected, _codex_tool, _patch_files, _patch_churn  # noqa: F401
from gnomon.sources.gemini import _gemini_events  # noqa: F401
from gnomon.sources.cursor import (  # noqa: F401
    _cursor_dedup, _cursor_sqlite_events, _cursor_jsonl_events,
    _cursor_clean_prompt, _cursor_jsonl_meta, _cursor_project_cwd,
    _cursor_tool, _cursor_tool_name,
    _cursor_cwd_from_paths, _cursor_jsonl_tool_paths, _cursor_resolve_cwd,
    _cursor_open_sqlite, _cursor_mcp_servers, _cursor_mcp_name_from_servers,
    _CURSOR_MCP_SERVERS_CACHE, _cursor_chat_meta, _CURSOR_CHAT_META_CACHE,
)
from gnomon.sources.antigravity import _pb_fields  # noqa: F401
from gnomon.analysis.quotes import _crashout_score, _cryptic_score, _POLITE_RE, _safe_quote, _RAGE_RE, _FILLER  # noqa: F401
from gnomon.analysis.metrics import _usage_int  # noqa: F401
from gnomon.output.profile_html import _hero_lead  # noqa: F401
from gnomon.output.summary import _build_profile, _build_noticed_stats  # noqa: F401
from gnomon.scoring.gstack import AQ_PILLAR_NOTES, AQ_AXIS_NOTES  # noqa: F401
from gnomon.scoring.insights import _growth_edges_pool, _signature_moves_pool, _commands_in, _strip_html  # noqa: F401


# Attribute -> list of (module_path, attr_name) targets.
# When a test patches paxel.X, the new value must also reach the gnomon module
# that actually reads X at runtime.
_ATTR_TARGETS = {
    "BASE":         [("gnomon.config", "BASE"), ("gnomon.sources.discovery", "BASE"),
                     ("gnomon.cli.local", "BASE")],
    "OUT_DIR":      [("gnomon.config", "OUT_DIR"), ("gnomon.cli.local", "OUT_DIR"),
                     ("gnomon.output.profile_html", "OUT_DIR"),
                     ("gnomon.output.narrative", "OUT_DIR"),
                     ("gnomon.output.report", "OUT_DIR")],
    "CODEX_DIR":    [("gnomon.sources.discovery", "CODEX_DIR"),
                     ("gnomon.cli.local", "CODEX_DIR")],
    "GEMINI_DIR":   [("gnomon.sources.discovery", "GEMINI_DIR"),
                     ("gnomon.cli.local", "GEMINI_DIR")],
    "ANTIGRAVITY_CLI_DIR": [("gnomon.sources.discovery", "ANTIGRAVITY_CLI_DIR"),
                            ("gnomon.cli.local", "ANTIGRAVITY_CLI_DIR")],
    # antigravity.py binds ANTIGRAVITY_DB by value (from ... import), so the live IDE-export
    # gate (antigravity_summary) reads it there — patch BOTH so tests can neutralize it.
    "ANTIGRAVITY_DB": [("gnomon.sources.discovery", "ANTIGRAVITY_DB"),
                       ("gnomon.sources.antigravity", "ANTIGRAVITY_DB")],
    "PI_DIR":       [("gnomon.sources.discovery", "PI_DIR"),
                     ("gnomon.cli.local", "PI_DIR")],
    "OPENCODE_DIR": [("gnomon.sources.discovery", "OPENCODE_DIR"),
                     ("gnomon.cli.local", "OPENCODE_DIR")],
    "CURSOR_DIR":   [("gnomon.sources.discovery", "CURSOR_DIR"),
                     ("gnomon.sources.cursor", "CURSOR_DIR"),
                     ("gnomon.cli.local", "CURSOR_DIR")],
    "CURSOR_DB":    [("gnomon.sources.discovery", "CURSOR_DB"),
                     ("gnomon.sources.cursor", "CURSOR_DB"),
                     ("gnomon.cli.local", "CURSOR_DB")],
    "git_churn":    [("gnomon.analysis.churn", "git_churn"),
                     ("gnomon.cli.local", "git_churn"),
                     ("gnomon.output.summary", "git_churn")],
}


class _PaxelModule(_types.ModuleType):
    """Module subclass that auto-propagates attribute patches to gnomon internals.

    Tests that do ``mock.patch.multiple(paxel, PI_DIR=..., ...)`` trigger
    ``__setattr__`` here, which forwards each patched value to the gnomon
    modules where the name is actually read at runtime.
    """

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        targets = _ATTR_TARGETS.get(name)
        if targets:
            for mod_path, attr in targets:
                mod = _sys.modules.get(mod_path)
                if mod is None:
                    mod = _importlib.import_module(mod_path)
                setattr(mod, attr, value)

    def __delattr__(self, name):
        """Undo propagation when mock.patch restores the original value."""
        # mock.patch calls delattr then setattr with the original — we must
        # not leave stale values in target modules.  Just let the subsequent
        # setattr re-propagate.
        super().__delattr__(name)


# Replace this module's class so __setattr__ hooks into mock.patch.
_real = _sys.modules[__name__]
_new = _PaxelModule(__name__, __doc__)
_new.__dict__.update(_real.__dict__)
_new.__file__ = _real.__file__
_new.__loader__ = getattr(_real, "__loader__", None)
_new.__spec__ = getattr(_real, "__spec__", None)
_new.__path__ = getattr(_real, "__path__", [])
_new.__package__ = getattr(_real, "__package__", None)
_sys.modules[__name__] = _new


def main():
    """Wrapper that passes output_dir from the (possibly patched) OUT_DIR."""
    me = _sys.modules[__name__]
    out_dir = getattr(me, "OUT_DIR", None)
    _gnomon_main(output_dir=out_dir)


# Attach main to the replacement module so it's accessible as paxel.main
_sys.modules[__name__].main = main


if __name__ == "__main__":
    main()
