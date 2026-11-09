"""Study multi-file host admission tests; no libretro core or game is run."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from skeleton.jeeves.game_comparison_media import (
    LocalComparativeMedia, _open_no_symlink,
    prepare_comparison_media,
)
from skeleton.jeeves.game_comparison_schema import (
    ComparativeStudyError, _content_bundle_manifest,
)


def _row(name, path):
    data=path.read_bytes()
    return {
        "name":name,"path":str(path),
        "sha256":hashlib.sha256(data).hexdigest(),
        "size_bytes":len(data),
    }


class LocalComparativeBundleContracts(unittest.TestCase):
    def test_cue_and_track_stream_without_game_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            cue=root/"disc.cue"
            track=root/"track.bin"
            cue.write_text('FILE "track.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n')
            track.write_bytes(bytes(range(256))*24)
            manifest=_content_bundle_manifest(
                {
                    "entrypoint":"disc.cue",
                    "files":[_row("disc.cue",cue),_row("track.bin",track)],
                },
                entry_source_path=str(cue),
                entry_source_sha=hashlib.sha256(cue.read_bytes()).hexdigest(),
            )
            media=LocalComparativeMedia(manifest)
            self.assertEqual(media.bundle.entrypoint,"disc.cue")
            self.assertEqual(len(media.bundle.files),2)
            ref=media.bundle.files["track.bin"]
            self.assertEqual(b"".join(media.reader(ref)),track.read_bytes())
            content_kwargs, sha=prepare_comparison_media({"content_bundle":manifest})
            self.assertEqual(sha,media.bundle_digest)
            self.assertIn("reader",content_kwargs)
            self.assertNotIn("rom_source",content_kwargs)

    def test_reject_mutation_after_admission(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            cue=root/"disc.cue"
            track=root/"track.bin"
            cue.write_text('FILE "track.bin" BINARY\n  TRACK 01 MODE1/2352\n')
            track.write_bytes(b"x"*4096)
            manifest=_content_bundle_manifest(
                {"entrypoint":"disc.cue","files":[_row("disc.cue",cue),_row("track.bin",track)]},
                entry_source_path=str(cue),
                entry_source_sha=hashlib.sha256(cue.read_bytes()).hexdigest(),
            )
            media=LocalComparativeMedia(manifest)
            track.write_bytes(b"y"*4096)
            with self.assertRaises(ComparativeStudyError):
                list(media.reader(media.bundle.files["track.bin"]))

    def test_reject_symlinked_media_components(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            original=root/"disc.bin"
            original.write_bytes(b"safe")
            alias=root/"alias.bin"
            alias.symlink_to(original)
            with self.assertRaises(OSError):
                fd=_open_no_symlink(str(alias))
                import os
                os.close(fd)

    def test_entrypoint_sha_consistency(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"disc.cue"
            path.write_text('FILE "track.bin" BINARY\nTRACK 01 MODE1/2352\n')
            with self.assertRaises(ComparativeStudyError):
                _content_bundle_manifest(
                    {"entrypoint":"disc.cue","files":[_row("disc.cue",path)]},
                    entry_source_path=str(path),
                    entry_source_sha="0"*64,
                )


if __name__=="__main__":
    unittest.main()
