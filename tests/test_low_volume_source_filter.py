import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock
from tests._clock import legacy_all_history

import gnomon.cli.insights as insights
import gnomon.cli.local as local
import gnomon.upload.mirdash as mirdash


WINDOW_SINCE = "2026-06-01"
WINDOW_UNTIL = "2026-06-30"


def _event(session_id, timestamp):
    return {
        "type": "user",
        "sessionId": session_id,
        "timestamp": timestamp,
        "message": {"role": "user", "content": "do the work"},
    }


def _write_events(root, name, events):
    path = os.path.join(root, f"{name}.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event) + "\n")
    return path


def _source_events(name, session_ids, timestamp="2026-06-15T12:00:00Z"):
    return [(name, sid, timestamp) for sid in session_ids]


class TestLowVolumeSourceFiltering(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="gnomon-low-volume-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _sources(self, *groups):
        out = []
        for source, session_id, timestamp in [item for group in groups for item in group]:
            path = next((p for p in out if p[0] == source), None)
            if path is None:
                fp = _write_events(self.root, source, [])
                path = (source, fp, "claude")
                out.append(path)
            with open(path[1], "a", encoding="utf-8") as fh:
                fh.write(json.dumps(_event(session_id, timestamp)) + "\n")
        return out

    def _run_local(self, sources, extra=()):
        out = os.path.join(self.root, "out-" + str(len(os.listdir(self.root))))
        os.makedirs(out)
        selected = list(dict.fromkeys(source for source, _, _ in sources))
        argv = selected + ["--summary", "--no-open", f"--since={WINDOW_SINCE}",
                           f"--until={WINDOW_UNTIL}"] + list(extra)
        with legacy_all_history(), \
                mock.patch.object(local, "discover_sources", return_value=sources), \
                mock.patch.object(local, "antigravity_summary", return_value=None), \
                mock.patch.object(local, "_coverage_month_index", return_value={}), \
                contextlib.redirect_stdout(io.StringIO()):
            local.main(argv, output_dir=out)
        with open(os.path.join(out, "stats.json"), encoding="utf-8") as fh:
            stats = json.load(fh)
        with open(os.path.join(out, "summary.json"), encoding="utf-8") as fh:
            summary = json.load(fh)
        return stats, summary

    def test_nine_sessions_are_excluded_and_ten_are_included(self):
        sources = self._sources(
            _source_events("claude", [f"low-{i}" for i in range(9)]),
            _source_events("codex", [f"good-{i}" for i in range(10)]),
        )
        stats, _ = self._run_local(sources)
        self.assertEqual(set(stats["corpus"]["sources"]), {"codex"})
        self.assertEqual(stats["volume"]["total_sessions"], 10)

    def test_duplicate_session_ids_count_once(self):
        sources = self._sources(
            _source_events("claude", ["same"] * 10 + [f"other-{i}" for i in range(8)]),
        )
        stats, _ = self._run_local(sources)
        self.assertEqual(stats["corpus"]["sources"], {})
        self.assertEqual(stats["volume"]["total_sessions"], 0)

    def test_outside_window_events_do_not_count_toward_threshold(self):
        sources = self._sources(
            _source_events("claude", [f"inside-{i}" for i in range(9)])
            + _source_events("claude", ["outside-a", "outside-b"], "2026-05-31T23:59:59Z"),
        )
        stats, _ = self._run_local(sources)
        self.assertEqual(stats["corpus"]["sources"], {})
        self.assertEqual(stats["volume"]["total_sessions"], 0)

    def test_unbounded_local_analysis_uses_full_history_without_summary_flag(self):
        sources = self._sources(
            _source_events("claude", [f"low-{i}" for i in range(9)]),
            _source_events("codex", [f"good-{i}" for i in range(10)]),
        )
        out = os.path.join(self.root, "out-unbounded")
        os.makedirs(out)
        with legacy_all_history(), \
                mock.patch.object(local, "discover_sources", return_value=sources), \
                mock.patch.object(local, "antigravity_summary", return_value=None), \
                mock.patch.object(local, "_coverage_month_index", return_value={}), \
                contextlib.redirect_stdout(io.StringIO()):
            local.main(
                ["claude", "codex", "--no-open"],
                output_dir=out,
            )
        with open(os.path.join(out, "stats.json"), encoding="utf-8") as fh:
            stats = json.load(fh)
        self.assertEqual(set(stats["corpus"]["sources"]), {"codex"})
        self.assertEqual(stats["volume"]["total_sessions"], 10)

    def test_mixed_sources_filter_only_low_volume_from_final_aggregate(self):
        sources = self._sources(
            _source_events("claude", [f"low-{i}" for i in range(9)]),
            _source_events("codex", [f"good-{i}" for i in range(10)]),
        )
        stats, summary = self._run_local(sources)
        self.assertEqual(set(stats["corpus"]["sources"]), {"codex"})
        self.assertEqual(set(stats["scoring_inputs_by_source"]), {"codex"})
        self.assertEqual(summary["context"]["sources"], ["codex"])

    def test_include_low_volume_retains_low_volume_sources(self):
        sources = self._sources(
            _source_events("claude", [f"low-{i}" for i in range(9)]),
        )
        stats, summary = self._run_local(sources, extra=("--include-low-volume",))
        self.assertEqual(set(stats["corpus"]["sources"]), {"claude"})
        self.assertEqual(stats["volume"]["total_sessions"], 9)
        self.assertEqual(summary["context"]["sources"], ["claude"])

    def test_include_low_volume_still_requires_in_window_activity(self):
        sources = self._sources(
            _source_events("claude", [f"old-{i}" for i in range(9)],
                           "2026-05-31T23:59:59Z"),
        )
        stats, summary = self._run_local(sources, extra=("--include-low-volume",))
        self.assertEqual(stats["corpus"]["sources"], {})
        self.assertEqual(stats["volume"]["total_sessions"], 0)
        self.assertEqual(summary["context"]["sources"], [])

    def test_antigravity_cli_and_ide_are_filtered_as_separate_sources(self):
        sources = self._sources(
            _source_events("antigravity", [f"cli-{i}" for i in range(9)]),
            _source_events("antigravity-ide", [f"ide-{i}" for i in range(10)]),
        )
        stats, _ = self._run_local(sources)
        self.assertEqual(set(stats["corpus"]["sources"]), {"antigravity-ide"})
        self.assertEqual(stats["volume"]["total_sessions"], 10)

    def test_all_filtered_sources_write_empty_summary_and_upload_skips(self):
        sources = self._sources(
            _source_events("claude", [f"low-{i}" for i in range(9)]),
        )
        _stats, summary = self._run_local(sources)
        self.assertEqual(summary["context"]["total_sessions"], 0)
        self.assertTrue(summary["context"]["date_range"][0])
        with mock.patch.object(mirdash, "_run_paxel", return_value=summary), \
                mock.patch.object(mirdash, "_upload_summary") as upload:
            result = mirdash._upload_window(
                "https://mirdash", "token", "/tmp/paxel.py", [],
                WINDOW_SINCE, "2026-07-01", "2026-06", False, True,
            )
        self.assertEqual(result, (None, None))
        upload.assert_not_called()


    def _run_local_sidecar(self, sources, extra=()):
        out = os.path.join(self.root, "out-sidecar-" + str(len(os.listdir(self.root))))
        os.makedirs(out)
        argv = ["claude", "codex", "--summary", "--no-open", f"--since={WINDOW_SINCE}",
                f"--until={WINDOW_UNTIL}"] + list(extra)
        stdout = io.StringIO()
        with legacy_all_history(), \
                mock.patch.object(local, "discover_sources", return_value=sources), \
                mock.patch.object(local, "antigravity_summary", return_value=None), \
                mock.patch.object(local, "_coverage_month_index", return_value={}), \
                contextlib.redirect_stdout(stdout):
            local.main(argv, output_dir=out)
        with open(os.path.join(out, local.LOW_VOLUME_FILE), encoding="utf-8") as fh:
            return json.load(fh), stdout.getvalue()

    def test_low_volume_drops_are_reported_in_sidecar_and_stdout(self):
        sources = self._sources(
            _source_events("claude", [f"low-{i}" for i in range(4)]),
            _source_events("codex", [f"good-{i}" for i in range(10)]),
        )
        sidecar, stdout = self._run_local_sidecar(sources)
        self.assertEqual(sidecar, {"threshold": 10, "dropped": {"claude": 4}})
        self.assertIn("low-volume: left out claude (4 sessions)", stdout)
        self.assertIn("--include-low-volume", stdout)

    def test_include_low_volume_reports_no_drops(self):
        sources = self._sources(
            _source_events("claude", [f"low-{i}" for i in range(4)]),
        )
        sidecar, stdout = self._run_local_sidecar(sources, extra=("--include-low-volume",))
        self.assertEqual(sidecar["dropped"], {})
        self.assertNotIn("low-volume:", stdout)


class TestLowVolumeUploadReporting(unittest.TestCase):
    LOW = {"threshold": 10, "dropped": {"claude": 4, "cursor": 2}}

    @staticmethod
    def _summary(sessions):
        return {"context": {"total_sessions": sessions,
                            "date_range": ["2026-06-01", "2026-06-30"]}}

    def _upload_window(self, summary):
        stdout = io.StringIO()
        with mock.patch.object(mirdash, "_run_paxel", return_value=summary), \
                mock.patch.object(mirdash, "_upload_summary",
                                  return_value={"reportUrl": "/r"}) as upload, \
                contextlib.redirect_stdout(stdout):
            result = mirdash._upload_window(
                "https://mirdash", "token", "/tmp/paxel.py", [],
                WINDOW_SINCE, "2026-07-01", "2026-06", False, False,
            )
        return result, upload, stdout.getvalue()

    def test_empty_window_emptied_by_filter_is_low_volume_not_no_activity(self):
        summary = dict(self._summary(0), _low_volume=self.LOW)
        (result, _), upload, stdout = self._upload_window(summary)
        self.assertTrue(mirdash._is_low_volume(result))
        self.assertEqual(result["dropped"], {"claude": 4, "cursor": 2})
        self.assertIn("below the low-volume threshold (sessions: claude 4, cursor 2)", stdout)
        upload.assert_not_called()

    def test_empty_window_without_drops_stays_no_activity(self):
        summary = dict(self._summary(0), _low_volume={"threshold": 10, "dropped": {}})
        (result, _), _, stdout = self._upload_window(summary)
        self.assertIsNone(result)
        self.assertIn("no activity", stdout)

    def test_sidecar_never_reaches_the_uploaded_payload(self):
        summary = dict(self._summary(12), _low_volume=self.LOW)
        (result, _), upload, _ = self._upload_window(summary)
        self.assertEqual(result, {"reportUrl": "/r"})
        self.assertNotIn("_low_volume", upload.call_args.args[2])

    def test_web_window_pushes_low_volume_skip(self):
        server = mock.MagicMock()
        summary = dict(self._summary(0), _low_volume=self.LOW)
        with mock.patch.object(mirdash, "_run_paxel", return_value=summary), \
                mock.patch.object(mirdash, "_upload_summary") as upload:
            result = mirdash._upload_window_web(
                "https://mirdash", "token", "/tmp/paxel.py", [],
                WINDOW_SINCE, "2026-07-01", "2026-06", False, server, 0, 1,
            )
        self.assertTrue(mirdash._is_low_volume(result))
        upload.assert_not_called()
        event, payload = server.push_event.call_args.args
        self.assertEqual(event, "skipped")
        self.assertEqual(payload["reason"], "low volume")

    def test_final_notice_lists_each_month(self):
        notice = mirdash._format_low_volume_notice({
            "2026-10": {"outcome": "low_volume", "threshold": 10, "dropped": {"claude": 6}},
            "2026-09": {"outcome": "low_volume", "threshold": 10,
                        "dropped": {"claude": 4, "cursor": 2}},
        })
        self.assertIn("sessions were found", notice)
        self.assertLess(notice.index("2026-09: claude 4, cursor 2"),
                        notice.index("2026-10: claude 6"))
        self.assertIn("--include-low-volume", notice)
        self.assertNotIn("no sessions found", notice)


class TestAntigravityLowVolumeGate(unittest.TestCase):
    def _run_gate(self, summary, extra=()):
        root = tempfile.mkdtemp(prefix="gnomon-antigravity-gate-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        export_path = os.path.join(root, "ide_steps_export.json")
        with mock.patch.object(local, "discover_sources", return_value=[]), \
                mock.patch.object(local, "antigravity_summary", return_value=summary), \
                mock.patch.object(local, "export_antigravity_ide", return_value=None) as export, \
                contextlib.redirect_stdout(io.StringIO()):
            local.main(["antigravity-ide", f"--since={WINDOW_SINCE}",
                        f"--until={WINDOW_UNTIL}", "--no-open", *extra],
                       output_dir=root)
        self.assertFalse(os.path.exists(export_path))
        return export

    def test_metadata_with_no_window_activity_does_not_fetch(self):
        export = self._run_gate({
            "conversations": 0,
            "first": "2026-06-15T12:00:00+00:00",
            "last": "2026-06-15T12:00:00+00:00",
        })
        export.assert_not_called()

    def test_sufficient_window_activity_fetches(self):
        export = self._run_gate({
            "conversations": 10,
            "first": "2026-06-01T12:00:00+00:00",
            "last": "2026-06-15T12:00:00+00:00",
        })
        export.assert_called_once()

    def test_include_low_volume_fetches_low_activity(self):
        export = self._run_gate({
            "conversations": 1,
            "first": "2026-06-15T12:00:00+00:00",
            "last": "2026-06-15T12:00:00+00:00",
        }, extra=("--include-low-volume",))
        export.assert_called_once()

    def test_discarded_antigravity_summary_is_not_published(self):
        root = tempfile.mkdtemp(prefix="gnomon-antigravity-empty-summary-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        summary = {
            "conversations": 1,
            "first": "2026-06-15T12:00:00+00:00",
            "last": "2026-06-15T12:00:00+00:00",
        }
        with mock.patch.object(local, "discover_sources", return_value=[]), \
                mock.patch.object(local, "antigravity_summary", return_value=summary), \
                mock.patch.object(local, "export_antigravity_ide", return_value=None), \
                contextlib.redirect_stdout(io.StringIO()):
            local.main(["antigravity-ide", f"--since={WINDOW_SINCE}",
                        f"--until={WINDOW_UNTIL}", "--no-open"], output_dir=root)
        with open(os.path.join(root, "stats.json"), encoding="utf-8") as fh:
            stats = json.load(fh)
        self.assertIsNone(stats["corpus"]["antigravity_experimental"])


class TestAntigravitySummaryWindow(unittest.TestCase):
    @staticmethod
    def _varint(value):
        out = bytearray()
        while value > 0x7F:
            out.append((value & 0x7F) | 0x80)
            value >>= 7
        out.append(value)
        return bytes(out)

    @classmethod
    def _field_bytes(cls, field, payload):
        return cls._varint((field << 3) | 2) + cls._varint(len(payload)) + payload

    @classmethod
    def _field_varint(cls, field, value):
        return cls._varint(field << 3) + cls._varint(value)

    def test_state_summary_counts_only_conversations_in_window(self):
        from gnomon.sources.antigravity import _antigravity_summary_from_buf

        inside = self._field_bytes(1, b"8b28368c-3a97-4e69-9b4e-b4bd5bed063b")
        inside += self._field_varint(2, 1781006400)  # 2026-06-09 UTC
        duplicate_outside = self._field_bytes(
            1, b"8b28368c-3a97-4e69-9b4e-b4bd5bed063b")
        duplicate_outside += self._field_varint(2, 1775006400)  # same UUID, before window
        outside = self._field_bytes(1, b"9b28368c-3a97-4e69-9b4e-b4bd5bed063b")
        outside += self._field_varint(2, 1775006400)  # before the window
        payload = (self._field_bytes(1, duplicate_outside)
                   + self._field_bytes(1, inside)
                   + self._field_bytes(1, outside))
        since = datetime(2026, 6, 1, tzinfo=timezone.utc)
        until = datetime(2026, 7, 1, tzinfo=timezone.utc)
        summary = _antigravity_summary_from_buf(payload, since, until)
        self.assertEqual(summary["conversations"], 1)


class TestInsightsLowVolumeForwarding(unittest.TestCase):
    def test_include_low_volume_reaches_monthly_paxel_arguments(self):
        with mock.patch.object(insights, "_enforce_cli_freshness"), \
                mock.patch.object(insights, "_maybe_offer_retention"), \
                mock.patch.object(insights, "_main_console") as console:
            insights.main(["--console", "--no-open", "--include-low-volume"])
        forwarded = console.call_args.args[4]
        self.assertIn("--include-low-volume", forwarded)

    def test_include_low_volume_reaches_direct_local_arguments(self):
        with mock.patch("gnomon.cli.local.main") as local_main:
            insights.main(["--local", "--include-low-volume"])
        self.assertIn("--include-low-volume", local_main.call_args.kwargs["argv"])


if __name__ == "__main__":
    unittest.main()
