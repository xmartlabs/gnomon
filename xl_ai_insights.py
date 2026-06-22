"""Legacy import shim. Prefer gnomon.cli.insights."""

from gnomon.cli.insights import *  # noqa: F401,F403
from gnomon.upload.mirdash import (  # noqa: F401
    _MAX_BACKFILL, _DEFAULT_WINDOW_MONTHS, _run_paxel, _upload_summary,
    _resolve_mirdash_base, _resolve_output_dir, _absolutize_dir_flags,
    parse_window, parse_backfill, decide_mode, month_windows,
    _summary_is_empty, _is_report_url,
    _format_summary, _PAXEL_ERROR, _UPLOAD_ERROR, _paxel_until_arg,
    _copy_artifacts, latest_month_with_data,
    _upload_window, _upload_window_web,
)
from gnomon.upload.auth import (  # noqa: F401
    _tokens_from_query, _capture_cli_token, _wait_for_auth_tokens,
    _SHARE_AUTH_TIMEOUT, _WEB_AUTH_TIMEOUT,
)
