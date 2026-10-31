"""Real-byte multimodal admission and tamper regression for local Jeeves."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from skeleton.jeeves.ai.studio_interaction_contract import (
    JeevesStudioController, StudioEvidenceJournal, StudioInteractionError,
)
from skeleton.jeeves.ai.studio_multimodal_intake import admit_reviewed_media


def pin(data: bytes) -> str:
    return sha256(data).hexdigest()


class ReviewedMultimodalTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.media = self.root / "media"
        self.media.mkdir()
        self.journal = StudioEvidenceJournal(
            self.root / "studio.sqlite", project_id="original-game",
            session_id="capture-session",
        )
        self.addCleanup(self.journal.close)
        self.host = JeevesStudioController(self.journal)
        self.wave = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"test-source-data" * 32
        self.note = ("Reviewed source: a game-world wind cue fades into "
                     "an original orchestral ambience. No spoken dialogue.").encode()
        (self.media / "original.wav").write_bytes(self.wave)
        (self.media / "review.txt").write_bytes(self.note)

    def kwargs(self):
        return {
            "root": self.media, "file_name": "original.wav",
            "expected_sha256": pin(self.wave),
            "source_id": "sound-01", "modality": "audio",
            "rights_scope": "original",
            "sidecar_name": "review.txt", "sidecar_sha256": pin(self.note),
            "decoder_id": "audio-review-v1", "reviewer_id": "human-auditor",
        }

    def test_host_attested_media_and_actual_reviewed_text(self):
        receipt = admit_reviewed_media(self.host, **self.kwargs())
        self.assertEqual(receipt["source_sha256"], pin(self.wave))
        self.assertEqual(receipt["reviewed_observation_sha256"], pin(self.note))
        self.assertFalse(receipt["locally_decoded_by_jeeves"])
        self.assertFalse(receipt["weight_training_performed"])
        rows = self.journal.read()
        self.assertEqual([row["kind"] for row in rows],
                         ["modality_registered", "modality_observation_reviewed"])
        self.assertEqual(rows[-1]["payload"]["source_sha256"], pin(self.wave))
        self.assertEqual(rows[-1]["payload"]["observation"], self.note.decode())
        self.assertEqual(rows[-1]["digest"], receipt["observation_receipt_sha256"])

    def test_reference_only_media_never_enters_context(self):
        bad = self.kwargs()
        bad["rights_scope"] = "reference_only"
        with self.assertRaises(StudioInteractionError):
            admit_reviewed_media(self.host, **bad)
        self.assertEqual(self.journal.read(), ())

    def test_bad_file_hash_refuses_admission(self):
        bad = self.kwargs()
        bad["expected_sha256"] = "0" * 64
        with self.assertRaises(StudioInteractionError):
            admit_reviewed_media(self.host, **bad)
        self.assertEqual(self.journal.read(), ())

    def test_bad_sidecar_hash_refuses_admission_without_partial_event(self):
        bad = self.kwargs()
        bad["sidecar_sha256"] = "1" * 64
        with self.assertRaises(StudioInteractionError):
            admit_reviewed_media(self.host, **bad)
        self.assertEqual(self.journal.read(), ())

    def test_duplicate_source_id_cannot_switch_bytes(self):
        admit_reviewed_media(self.host, **self.kwargs())
        with self.assertRaises(StudioInteractionError):
            admit_reviewed_media(self.host, **self.kwargs())
        self.assertEqual(len(self.journal.read()), 2)

    def test_direct_review_event_injection_is_rejected(self):
        with self.assertRaises(StudioInteractionError):
            self.journal.append("modality_observation_reviewed", {
                "source_id": "forged", "observation": "I saw the full image.",
                "observation_sha256": "0" * 64,
            })
        self.assertEqual(self.journal.read(), ())

    def test_unadmitted_media_cannot_receive_fabricated_review(self):
        with self.assertRaises(StudioInteractionError):
            self.host.review_media_observation(
                source_id="missing", observation=self.note.decode(),
                observation_sha256=pin(self.note), source_sha256=pin(self.wave),
                decoder_id="audio-review-v1", reviewer_id="human-auditor",
            )

    def test_media_path_cannot_escape_project_root(self):
        bad = self.kwargs()
        bad["file_name"] = "../escape.wav"
        with self.assertRaises(StudioInteractionError):
            admit_reviewed_media(self.host, **bad)
        (self.media / "link.wav").symlink_to(self.media / "original.wav")
        bad["file_name"] = "link.wav"
        with self.assertRaises(StudioInteractionError):
            admit_reviewed_media(self.host, **bad)

    def test_disguised_wav_is_rejected(self):
        impostor = b"not a real wave header" * 16
        (self.media / "original.wav").write_bytes(impostor)
        bad = self.kwargs()
        bad["expected_sha256"] = pin(impostor)
        with self.assertRaises(StudioInteractionError):
            admit_reviewed_media(self.host, **bad)

    def test_receipt_mutation_is_visible_to_journal_verification(self):
        admit_reviewed_media(self.host, **self.kwargs())
        with sqlite3.connect(str(self.root / "studio.sqlite")) as db:
            db.execute("UPDATE studio_event SET payload='{}' WHERE sequence=1")
        with self.assertRaises(StudioInteractionError):
            self.journal.read()


if __name__ == "__main__":
    unittest.main()
