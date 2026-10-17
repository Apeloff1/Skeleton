"""Multi-year original game run history segmentation, crash safety and integrity.

Synthetic run entries are explicitly source-only fixtures; no external game
emulator, installer, model training or year-long endurance is claimed.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.studio_campaign import _atomic_json
from skeleton.ai.game_builder.studio_campaign_lock import campaign_lock
from skeleton.ai.game_builder.studio_execution_history import (
    ENTRY_SCHEMA, SCHEMA, StudioQualificationHistoryError, _read_history,
)
from skeleton.ai.game_builder.studio_history_segments import (
    MAX_SEGMENTS, SEGMENT_SIZE, StudioHistorySegmentError, audit_segments,
    seal_full_heads,
)

IDENTITY = "a" * 64


def original_run(sequence: int, previous: str | None) -> dict:
    body = {
        "schema": ENTRY_SCHEMA,
        "sequence": sequence,
        "campaign_identity": IDENTITY,
        "run_digest": canonical_digest({"run": sequence}),
        "assurance_report_digest": "b" * 64,
        "previous_entry_digest": previous,
        "verified_stage_attempts": 1,
        "blocked_stage_attempts": 0 if sequence % 3 else 1,
        "unsupported_stage_attempts": 0,
        "native_cpu_divergence_count": 1 if sequence % 7 == 0 else 0,
        "full_release_qualified": False,
        "model_weights_updated": False,
    }
    return {**body, "entry_digest": canonical_digest(body)}


def chain(start: int, end: int, previous: str | None) -> list[dict]:
    result = []
    for sequence in range(start, end + 1):
        item = original_run(sequence, previous)
        previous = item["entry_digest"]
        result.append(item)
    return result


def head(root: Path, rows: list[dict], segments=None):
    body = {
        "schema": SCHEMA, "campaign_identity": IDENTITY,
        "entries": rows,
    }
    if segments is not None:
        body["segments"] = segments
    _atomic_json(root / "qualification_history.json", {
        **body, "history_digest": canonical_digest(body),
    })


class ProductionHistoryMultiYearSegmentsTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def test_old_unsegmented_history_is_read_without_format_migration(self):
        rows = chain(1, 7, None)
        head(self.root, rows)
        result = _read_history(self.root, IDENTITY)
        self.assertEqual(len(result["entries"]), 7)
        self.assertNotIn("segments", result)
        self.assertEqual(result["_archive_stats"]["archive_entry_count"], 0)

    def test_verified_rollover_keeps_every_entry_after_crash_or_resume(self):
        original = chain(1, 64, None)
        head(self.root, original)
        with campaign_lock(self.root):
            validated = _read_history(self.root, IDENTITY)
            self.assertEqual(len(validated["entries"]), SEGMENT_SIZE)
            output, remainder = seal_full_heads(
                self.root, IDENTITY, [], validated["entries"],
                entry_schema=ENTRY_SCHEMA,
            )
            self.assertEqual(len(output), 1)
            self.assertEqual(remainder, [])
            segment = self.root / "qualification_history_segments/segment-00001.json"
            self.assertTrue(segment.is_file())
            before = segment.read_bytes()
            # Crash before writing the head leaves an orphan segment and
            # the last committed journal untouched. Recovery must not delete,
            # overwrite, duplicate or trust an inconsistent sealed file.
            self.assertEqual(len(_read_history(self.root, IDENTITY)["entries"]), 64)
            restored, tail = seal_full_heads(
                self.root, IDENTITY, [], original,
                entry_schema=ENTRY_SCHEMA,
            )
            self.assertEqual(output, restored)
            self.assertEqual(remainder, tail)
            self.assertEqual(before, segment.read_bytes())
            next_run = original_run(65, original[-1]["entry_digest"])
            head(self.root, [next_run], restored)
        measured = _read_history(self.root, IDENTITY)
        stats = measured["_archive_stats"]
        self.assertEqual(stats["archive_entry_count"], 64)
        self.assertEqual(stats["archive_tip"], original[-1]["entry_digest"])
        self.assertEqual(stats["archive_cpu_divergence_count"], 9)
        self.assertEqual(stats["archive_unblocked_runs"], 43)
        self.assertEqual(measured["entries"][0]["sequence"], 65)

    def test_second_archive_retains_exact_global_sequence_and_tip(self):
        rows = chain(1, 129, None)
        with campaign_lock(self.root):
            archive, remaining = seal_full_heads(
                self.root, IDENTITY, [], rows, entry_schema=ENTRY_SCHEMA,
            )
            self.assertEqual(len(archive), 2)
            self.assertEqual(len(remaining), 1)
            head(self.root, remaining, archive)
        report = _read_history(self.root, IDENTITY)
        self.assertEqual(report["_archive_stats"]["archive_entry_count"], 128)
        self.assertEqual(report["entries"][0]["sequence"], 129)
        self.assertEqual(report["entries"][0]["previous_entry_digest"],
                         archive[-1]["last_entry_digest"])
        self.assertEqual(report["_archive_stats"]["segments_remaining"],
                         MAX_SEGMENTS - 2)

    def test_modified_sealed_content_or_header_cannot_be_admitted(self):
        runs = chain(1, 65, None)
        with campaign_lock(self.root):
            archives, tail = seal_full_heads(
                self.root, IDENTITY, [], runs, entry_schema=ENTRY_SCHEMA,
            )
            head(self.root, tail, archives)
        segment = self.root / "qualification_history_segments/segment-00001.json"
        import json
        corrupted = json.loads(segment.read_text(encoding="utf-8"))
        corrupted["entries"][0]["verified_stage_attempts"] += 1
        segment.write_text(json.dumps(corrupted), encoding="utf-8")
        with self.assertRaises(StudioQualificationHistoryError):
            _read_history(self.root, IDENTITY)
        with self.assertRaises(StudioHistorySegmentError):
            audit_segments(
                self.root, IDENTITY, archives, entry_schema=ENTRY_SCHEMA,
            )

    def test_archive_gap_duplicate_or_exhausted_index_fails_closed(self):
        rows = chain(1, 64, None)
        bogus = [{
            "file": "segment-00001.json",
            "segment_digest": "0" * 64,
            "last_entry_digest": "1" * 64,
        }] * MAX_SEGMENTS
        with campaign_lock(self.root):
            with self.assertRaises(StudioHistorySegmentError):
                seal_full_heads(
                    self.root, IDENTITY, bogus, rows,
                    entry_schema=ENTRY_SCHEMA,
                )
            archived, _ = seal_full_heads(
                self.root, IDENTITY, [], rows, entry_schema=ENTRY_SCHEMA,
            )
            with self.assertRaises(StudioHistorySegmentError):
                audit_segments(
                    self.root, IDENTITY, [archived[0], archived[0]],
                    entry_schema=ENTRY_SCHEMA,
                )


if __name__ == "__main__":
    unittest.main()
