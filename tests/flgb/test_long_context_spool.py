"""Source-backed offline long-context custody and crash recovery tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.model_runtime import LongContextSpool
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.tokenization import NativeTokenizer
from skeleton.ai.model_runtime.flgb_model_runtime import TokenSequence
from skeleton.ai.model_runtime.long_context_cli import main as cli_main
from skeleton.ai.model_runtime.long_context_spool import LongContextSpoolError
from skeleton.ai.model_runtime.tokenization import serialize_token_sequence

TOKENIZER = sha256(b"original native tokenizer").hexdigest()
SOURCE = sha256(b"original authored story").hexdigest()


class TestLongContextSpool(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "spool"
        self.spool = LongContextSpool(self.root, disk_reserve_bytes=0)
        self.sequence = TokenSequence(TOKENIZER, tuple(range(30)), SOURCE)

    def stage(self):
        return self.spool.stage(self.sequence)

    def test_canonical_native_tokenizer_can_stage_and_resume(self):
        model = TinyTransformer(
            vocab=("hello", "world"), dim=8, ctx=8, seed=7,
            n_heads=2, n_layers=2, d_ff=16,
        )
        tokenizer = NativeTokenizer(model)
        checkpoint = tokenizer.stage_text("hello world", self.spool)
        receipt, sequence = self.spool.load(
            checkpoint, expected_tokenizer_digest=tokenizer.digest,
        )
        self.assertEqual(receipt.sequence_digest, sequence.digest)
        self.assertEqual(sequence, tokenizer.encode_sequence("hello world"))
        self.assertEqual(self.spool.next_window(
            checkpoint, expected_tokenizer_digest=tokenizer.digest,
            max_tokens=8,
        ).token_ids, sequence.token_ids)

    @unittest.skipUnless(os.name == "posix", "descriptor-relative capacity requires POSIX")
    def test_capacity_snapshot_reports_bounded_payload_free_observation(self):
        start = self.stage()
        before, _ = self.spool.load(start, expected_tokenizer_digest=TOKENIZER)
        snapshot = self.spool.capacity_snapshot(requested_bytes=1)
        self.assertEqual(snapshot["schema"], "skeleton.ai.long-context-capacity.v1")
        self.assertGreater(snapshot["used_bytes"], 0)
        self.assertEqual(snapshot["quota_remaining_bytes"],
                         snapshot["quota_bytes"] - snapshot["used_bytes"])
        self.assertEqual(snapshot["observed_publishable_bytes"],
                         min(snapshot["quota_remaining_bytes"],
                             max(0, snapshot["volume_available_bytes"] -
                                 snapshot["disk_reserve_bytes"])))
        self.assertEqual(snapshot["hardware_qualification"], "not_assessed")
        self.assertIs(snapshot["is_admission_lease"], False)
        self.assertNotIn("token_ids", snapshot)
        self.assertNotIn("sequence_digest", snapshot)
        self.assertEqual(before, self.spool.load(
            start, expected_tokenizer_digest=TOKENIZER)[0])

    @unittest.skipUnless(os.name == "posix", "descriptor-relative capacity requires POSIX")
    def test_capacity_snapshot_holds_when_request_exceeds_quota(self):
        self.stage()
        snapshot = self.spool.capacity_snapshot(
            requested_bytes=self.spool.max_spool_bytes)
        self.assertEqual(snapshot["state"], "hold")
        self.assertIs(snapshot["request_observed_sufficient"], False)

    def test_capacity_snapshot_rejects_invalid_request_types(self):
        for invalid in (-1, True, 1.5, "12", 2**50):
            with self.subTest(invalid=invalid), self.assertRaises(LongContextSpoolError):
                self.spool.capacity_snapshot(requested_bytes=invalid)

    @unittest.skipUnless(os.name == "posix", "descriptor-relative capacity requires POSIX")
    def test_capacity_snapshot_denies_untrusted_inventory_without_token_leak(self):
        self.stage()
        bucket = self.spool.objects / "aa"
        bucket.mkdir(exist_ok=True)
        (bucket / "untrusted").symlink_to(self.root / "absent")
        with self.assertRaises(LongContextSpoolError):
            self.spool.capacity_snapshot()

    @unittest.skipUnless(os.name == "posix", "descriptor-relative capacity requires POSIX")
    def test_capacity_snapshot_fails_closed_on_missing_volume_telemetry(self):
        from unittest.mock import patch
        with patch("skeleton.ai.model_runtime.long_context_spool.os.fstatvfs",
                   side_effect=OSError("probe denied")):
            with self.assertRaisesRegex(LongContextSpoolError, "telemetry"):
                self.spool.capacity_snapshot()

    @unittest.skipUnless(os.name == "posix", "descriptor-relative capacity requires POSIX")
    def test_capacity_snapshot_rejects_malformed_volume_components(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        for blocks, block_size in ((-1, -1), (True, 4096),
                                   (1, False), (1, 0), (2**64, 4096),
                                   (1, "4096")):
            with self.subTest(blocks=blocks, block_size=block_size):
                with patch(
                    "skeleton.ai.model_runtime.long_context_spool.os.fstatvfs",
                    return_value=SimpleNamespace(
                        f_bavail=blocks, f_frsize=block_size,
                    ),
                ):
                    with self.assertRaisesRegex(
                        LongContextSpoolError, "invalid spool volume telemetry",
                    ):
                        self.spool.capacity_snapshot(requested_bytes=1)

    @unittest.skipUnless(os.name == "posix", "descriptor-relative capacity requires POSIX")
    def test_cli_capacity_emits_no_token_payload(self):
        output = StringIO()
        with redirect_stdout(output):
            code = cli_main(["--root", str(self.root),
                             "--tokenizer-digest", TOKENIZER,
                             "capacity", "--request-bytes", "16"])
        self.assertEqual(code, 0)
        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["schema"], "skeleton.ai.long-context-capacity.v1")
        self.assertNotIn("token_ids", output.getvalue())
        self.assertFalse(receipt["is_admission_lease"])

    @unittest.skipUnless(os.name == "posix", "POSIX flock required")
    def test_publication_lock_rejects_regressed_or_invalid_monotonic_clock(self):
        from unittest.mock import patch

        for value in (True, -1, "not-a-clock"):
            with self.subTest(value=value):
                with patch("skeleton.ai.model_runtime.long_context_spool.monotonic_ns",
                           return_value=value):
                    with self.assertRaisesRegex(
                        LongContextSpoolError, "invalid spool lock clock"
                    ):
                        self.stage()
        with patch("skeleton.ai.model_runtime.long_context_spool.monotonic_ns",
                   side_effect=(100, 99)):
            with patch("fcntl.flock", side_effect=BlockingIOError()):
                with self.assertRaisesRegex(
                    LongContextSpoolError, "spool lock monotonic clock unavailable or regressed"
                ):
                    self.stage()

    @unittest.skipUnless(os.name == "posix", "POSIX flock required")
    def test_publication_lock_has_attempt_bound_when_clock_freezes(self):
        from unittest.mock import patch

        with patch("skeleton.ai.model_runtime.long_context_spool.monotonic_ns",
                   return_value=100):
            with patch("skeleton.ai.model_runtime.long_context_spool.sleep") as sleeper:
                with patch("fcntl.flock", side_effect=BlockingIOError()) as locker:
                    with self.assertRaisesRegex(
                        LongContextSpoolError, "spool publication lock contention"
                    ):
                        self.stage()
        self.assertLessEqual(locker.call_count, 201)
        self.assertLessEqual(sleeper.call_count, 200)
        self.assertFalse(any(self.spool.objects.rglob("[0-9a-f]" * 64)))

    @unittest.skipUnless(os.name == "posix", "descriptor-relative publication requires POSIX")
    def test_actual_publication_denies_malformed_volume_telemetry(self):
        """A positive-looking product of invalid counters must never admit writes."""
        from types import SimpleNamespace
        from unittest.mock import patch

        invalid = ((-2, -4096), (-1, 4096), (1, -4096),
                   (True, 4096), (1, False), (2**64, 4096))
        for blocks, block_size in invalid:
            with self.subTest(blocks=blocks, block_size=block_size):
                with patch("skeleton.ai.model_runtime.long_context_spool.os.fstatvfs",
                           return_value=SimpleNamespace(
                               f_bavail=blocks, f_frsize=block_size)):
                    with self.assertRaisesRegex(
                        LongContextSpoolError, "invalid spool volume telemetry"
                    ):
                        self.stage()
                # Denied writes must not publish either a sequence or a receipt.
                self.assertFalse(any(self.spool.objects.rglob("[0-9a-f]" * 64)))
                self.assertFalse(any(self.spool.checkpoints.rglob("[0-9a-f]" * 64)))

    @unittest.skipUnless(os.name == "posix", "descriptor-relative publication requires POSIX")
    def test_actual_publication_denies_missing_volume_telemetry(self):
        from unittest.mock import patch

        for error in (OSError("unavailable"), ValueError("unavailable"),
                      OverflowError("unavailable"), TypeError("unavailable")):
            with self.subTest(error=type(error).__name__):
                with patch("skeleton.ai.model_runtime.long_context_spool.os.fstatvfs",
                           side_effect=error):
                    with self.assertRaisesRegex(
                        LongContextSpoolError, "spool volume telemetry unavailable"
                    ):
                        self.stage()
        self.assertFalse(any(self.spool.objects.rglob("[0-9a-f]" * 64)))

    def test_stage_and_resume_across_process_object(self):
        start = self.stage()
        restored = LongContextSpool(self.root, disk_reserve_bytes=0)
        receipt, sequence = restored.load(start, expected_tokenizer_digest=TOKENIZER)
        self.assertEqual(receipt.cursor, 0)
        self.assertEqual(sequence, self.sequence)
        self.assertEqual(restored.stage(self.sequence), start)

    def test_token_window_allocation_is_bounded_independently_of_spool_size(self):
        checkpoint = self.stage()
        with self.assertRaisesRegex(LongContextSpoolError, "max_tokens"):
            self.spool.next_window(
                checkpoint, expected_tokenizer_digest=TOKENIZER,
                max_tokens=4097,
            )
        strict = LongContextSpool(
            self.root, max_window_tokens=4, disk_reserve_bytes=0,
        )
        self.assertEqual(
            strict.next_window(
                checkpoint, expected_tokenizer_digest=TOKENIZER, max_tokens=4,
            ).token_ids, (0, 1, 2, 3),
        )
        with self.assertRaisesRegex(LongContextSpoolError, "max_tokens"):
            strict.next_window(
                checkpoint, expected_tokenizer_digest=TOKENIZER, max_tokens=5,
            )
        for invalid in (0, True, -1, 65537):
            with self.subTest(invalid=invalid), self.assertRaises(LongContextSpoolError):
                LongContextSpool(
                    self.root, max_window_tokens=invalid, disk_reserve_bytes=0,
                )
        # A denied oversized read never advances immutable custody.
        self.assertEqual(
            self.spool.load(
                checkpoint, expected_tokenizer_digest=TOKENIZER,
            )[0].cursor, 0,
        )

    def test_bounded_windows_and_explicit_progress(self):
        current = self.stage()
        for expected_start in (0, 8, 16, 24):
            window = self.spool.next_window(current,
                expected_tokenizer_digest=TOKENIZER, max_tokens=8)
            self.assertEqual(window.start, expected_start)
            self.assertEqual(window.source_sequence_digest, self.sequence.digest)
            current = self.spool.advance(current,
                expected_tokenizer_digest=TOKENIZER, consumed_tokens=len(window.token_ids))
        self.assertIsNone(self.spool.next_window(current,
            expected_tokenizer_digest=TOKENIZER, max_tokens=8))

    def test_immutable_branching_from_same_parent(self):
        start = self.stage()
        a = self.spool.advance(start, expected_tokenizer_digest=TOKENIZER, consumed_tokens=1)
        b = self.spool.advance(start, expected_tokenizer_digest=TOKENIZER, consumed_tokens=2)
        self.assertNotEqual(a, b)
        self.assertEqual(self.spool.load(start, expected_tokenizer_digest=TOKENIZER)[0].cursor, 0)
        self.assertEqual(self.spool.load(a, expected_tokenizer_digest=TOKENIZER)[0].cursor, 1)

    def test_concurrent_identical_stage_is_idempotent(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.stage(), range(8)))
        self.assertEqual(len(set(results)), 1)

    def test_reject_tokenizer_identity_drift(self):
        start = self.stage()
        with self.assertRaises(LongContextSpoolError):
            self.spool.load(start, expected_tokenizer_digest=SOURCE)

    def test_reject_mutated_sequence_bytes(self):
        start = self.stage()
        receipt, _ = self.spool.load(start, expected_tokenizer_digest=TOKENIZER)
        path = self.spool._path("object", receipt.object_digest)
        path.write_bytes(b"corrupt")
        with self.assertRaises(LongContextSpoolError):
            self.spool.load(start, expected_tokenizer_digest=TOKENIZER)

    def test_reject_mutated_checkpoint_bytes(self):
        start = self.stage()
        path = self.spool._path("checkpoint", start)
        data = json.loads(path.read_text())
        data["cursor"] = 7
        path.write_text(json.dumps(data))
        with self.assertRaises(LongContextSpoolError):
            self.spool.load(start, expected_tokenizer_digest=TOKENIZER)

    def test_reject_missing_parent(self):
        start = self.stage()
        child = self.spool.advance(start, expected_tokenizer_digest=TOKENIZER, consumed_tokens=1)
        self.spool._path("checkpoint", start).unlink()
        with self.assertRaises(LongContextSpoolError):
            self.spool.load(child, expected_tokenizer_digest=TOKENIZER)

    def test_reject_overadvance_and_invalid_types(self):
        start = self.stage()
        for value in (0, -1, True, 31):
            with self.subTest(value=value), self.assertRaises(LongContextSpoolError):
                self.spool.advance(start, expected_tokenizer_digest=TOKENIZER,
                                   consumed_tokens=value)

    def test_spool_quota_blocks_new_object_without_overwriting_old_receipt(self):
        if os.name != "posix":
            self.skipTest("POSIX descriptor-relative quota inventory")
        canonical = serialize_token_sequence(self.sequence)
        # Genesis object plus its checkpoint fit, but another source does not.
        start = self.stage()
        used = self.spool._spool_usage_locked()
        capped = LongContextSpool(
            self.root, disk_reserve_bytes=0, max_spool_bytes=used + 1,
        )
        other = TokenSequence(TOKENIZER, tuple(range(29)), SOURCE)
        self.assertGreater(len(serialize_token_sequence(other)), 1)
        with self.assertRaisesRegex(LongContextSpoolError, "byte quota"):
            capped.stage(other)
        self.assertEqual(
            self.spool.load(start, expected_tokenizer_digest=TOKENIZER)[1],
            self.sequence,
        )
        self.assertEqual(capped.stage(self.sequence), start)

    def test_spool_quota_counts_orphan_temps_and_rejects_untrusted_entries(self):
        if os.name != "posix":
            self.skipTest("POSIX descriptor-relative quota inventory")
        start = self.stage()
        used = self.spool._spool_usage_locked()
        path = self.spool._path("checkpoint", start)
        orphan = path.parent / ("." + start + "." + "f" * 16 + ".tmp")
        orphan.write_bytes(b"orphan quota")
        orphan.chmod(0o600)
        self.assertEqual(
            self.spool._spool_usage_locked(), used + len(b"orphan quota"),
        )
        orphan.unlink()
        rogue = path.parent / "rogue-link"
        rogue.symlink_to(path)
        with self.assertRaisesRegex(LongContextSpoolError, "quota object"):
            self.spool._spool_usage_locked()
        rogue.unlink()

    def test_spool_quota_configuration_denies_invalid_values(self):
        for invalid in (0, -1, True, 1024 ** 4 + 1):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                LongContextSpoolError, "max_spool_bytes",
            ):
                LongContextSpool(
                    self.root, disk_reserve_bytes=0, max_spool_bytes=invalid,
                )

    def test_reject_tight_disk_reserve(self):
        blocked = LongContextSpool(self.root / "reserved", disk_reserve_bytes=2**60)
        with self.assertRaises(LongContextSpoolError):
            blocked.stage(self.sequence)

    def test_reject_hardlinked_immutable_object_and_checkpoint(self):
        if os.name != "posix" or not hasattr(os, "link"):
            self.skipTest("POSIX hardlink inode validation")
        start = self.stage()
        receipt, _ = self.spool.load(
            start, expected_tokenizer_digest=TOKENIZER,
        )
        for kind, digest in (("object", receipt.object_digest),
                             ("checkpoint", start)):
            with self.subTest(kind=kind):
                path = self.spool._path(kind, digest)
                alias = Path(self.directory.name) / ("alias-" + kind)
                try:
                    os.link(path, alias)
                except (OSError, NotImplementedError):
                    self.skipTest("hardlink unavailable")
                try:
                    with self.assertRaisesRegex(LongContextSpoolError, "owner or mode"):
                        self.spool.load(start, expected_tokenizer_digest=TOKENIZER)
                    if kind == "object":
                        with self.assertRaisesRegex(LongContextSpoolError, "owner or mode"):
                            self.stage()
                finally:
                    alias.unlink()


    def test_reject_symlinked_object(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        start = self.stage()
        receipt, _ = self.spool.load(start, expected_tokenizer_digest=TOKENIZER)
        path = self.spool._path("object", receipt.object_digest)
        saved = path.with_name("original")
        path.rename(saved)
        try:
            path.symlink_to(saved)
        except (OSError, NotImplementedError):
            self.skipTest("symlink permission unavailable")
        with self.assertRaises(LongContextSpoolError):
            self.spool.load(start, expected_tokenizer_digest=TOKENIZER)

    def test_posix_publish_lock_symlink_cannot_redirect_spool_writes(self):
        if os.name != "posix":
            self.skipTest("POSIX no-follow publication lock")
        target = Path(self.directory.name) / "untrusted-lock-target"
        target.write_bytes(b"unchanged")
        lock = self.root / ".publish.lock"
        lock.symlink_to(target)
        with self.assertRaises(LongContextSpoolError):
            self.stage()
        self.assertEqual(target.read_bytes(), b"unchanged")

    def test_posix_publish_lock_rejects_untrusted_mode(self):
        if os.name != "posix":
            self.skipTest("POSIX private publication lock")
        start = self.stage()
        lock = self.root / ".publish.lock"
        lock.chmod(0o644)
        with self.assertRaisesRegex(LongContextSpoolError, "owner or mode"):
            self.spool.advance(
                start, expected_tokenizer_digest=TOKENIZER, consumed_tokens=1,
            )

    def test_posix_bucket_replacement_cannot_redirect_pinned_io(self):
        if os.name != "posix":
            self.skipTest("POSIX directory-fd contract")
        start = self.stage()
        receipt, _ = self.spool.load(start, expected_tokenizer_digest=TOKENIZER)
        bucket = self.spool._path("object", receipt.object_digest).parent
        moved = bucket.with_name(bucket.name + "-saved")
        bucket.rename(moved)
        target = Path(self.directory.name) / "untrusted"
        target.mkdir()
        bucket.symlink_to(target, target_is_directory=True)
        with self.assertRaises(LongContextSpoolError):
            self.spool.load(start, expected_tokenizer_digest=TOKENIZER)
        self.assertEqual(list(target.iterdir()), [])

    def test_posix_root_replacement_keeps_inode_pinned(self):
        if os.name != "posix":
            self.skipTest("POSIX directory-fd contract")
        start = self.stage()
        old_root = self.root.with_name("original-root")
        self.root.rename(old_root)
        adversary = Path(self.directory.name) / "other-root"
        adversary.mkdir()
        self.root.symlink_to(adversary, target_is_directory=True)
        checkpoint, sequence = self.spool.load(
            start, expected_tokenizer_digest=TOKENIZER,
        )
        self.assertEqual(sequence, self.sequence)
        self.assertEqual(checkpoint.cursor, 0)
        self.assertEqual(list(adversary.iterdir()), [])

    def test_posix_closed_root_fails_closed(self):
        if os.name != "posix":
            self.skipTest("POSIX directory-fd contract")
        self.spool.close()
        with self.assertRaises(LongContextSpoolError):
            self.spool.stage(self.sequence)

    def test_reject_symlinked_root(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        link = Path(self.directory.name) / "link"
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink permission unavailable")
        with self.assertRaises(LongContextSpoolError):
            LongContextSpool(link)


    def test_posix_symlinked_ancestor_rejected_before_root_creation(self):
        if os.name != "posix":
            self.skipTest("POSIX no-follow ancestry contract")
        outside = Path(self.directory.name) / "outside"
        outside.mkdir()
        alias = Path(self.directory.name) / "alias"
        alias.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(LongContextSpoolError):
            LongContextSpool(alias / "new-spool", disk_reserve_bytes=0)
        self.assertEqual(list(outside.iterdir()), [])

    def test_posix_selected_sequence_ancestor_symlink_rejected(self):
        if os.name != "posix":
            self.skipTest("POSIX no-follow selected source contract")
        from skeleton.ai.model_runtime.long_context_spool import read_selected_sequence
        trusted = Path(self.directory.name) / "trusted"
        trusted.mkdir()
        (trusted / "tokens.json").write_bytes(serialize_token_sequence(self.sequence))
        alias = Path(self.directory.name) / "source-alias"
        alias.symlink_to(trusted, target_is_directory=True)
        with self.assertRaises(OSError):
            read_selected_sequence(alias / "tokens.json", limit=4096)
        self.assertEqual(
            read_selected_sequence(trusted / "tokens.json", limit=4096),
            serialize_token_sequence(self.sequence),
        )

    def test_selected_source_rejects_mutation_during_bounded_read(self):
        if os.name != "posix":
            self.skipTest("POSIX selected-source identity fence")
        from unittest.mock import patch
        from skeleton.ai.model_runtime.long_context_spool import read_selected_sequence
        source = Path(self.directory.name) / "mutating-tokens.json"
        source.write_bytes(serialize_token_sequence(self.sequence))
        original_read = os.read
        changed = False

        def mutate_after_read(fd, count):
            nonlocal changed
            result = original_read(fd, count)
            if not changed:
                changed = True
                with source.open("ab") as output:
                    output.write(b"!")
            return result

        with patch(
            "skeleton.ai.model_runtime.long_context_spool.os.read",
            side_effect=mutate_after_read,
        ):
            with self.assertRaisesRegex(LongContextSpoolError, "changed during read"):
                read_selected_sequence(source, limit=4096)
        self.assertTrue(changed)

    def test_selected_source_rejects_name_replacement_during_read(self):
        if os.name != "posix":
            self.skipTest("POSIX descriptor-relative selected-source name fence")
        from unittest.mock import patch
        from skeleton.ai.model_runtime.long_context_spool import read_selected_sequence
        source = Path(self.directory.name) / "replaceable-tokens.json"
        canonical = serialize_token_sequence(self.sequence)
        source.write_bytes(canonical)
        original_read = os.read
        replaced = False

        def replace_name_after_read(fd, count):
            nonlocal replaced
            result = original_read(fd, count)
            if not replaced:
                replaced = True
                source.rename(source.with_name("previous-tokens.json"))
                source.write_bytes(canonical)
            return result

        with patch(
            "skeleton.ai.model_runtime.long_context_spool.os.read",
            side_effect=replace_name_after_read,
        ):
            with self.assertRaisesRegex(LongContextSpoolError, "path changed during read"):
                read_selected_sequence(source, limit=4096)
        self.assertTrue(replaced)

    def test_selected_source_rejects_oversize_before_read(self):
        from unittest.mock import patch
        from skeleton.ai.model_runtime.long_context_spool import read_selected_sequence
        source = Path(self.directory.name) / "oversize-tokens.json"
        source.write_bytes(b"x" * 128)
        with patch(
            "skeleton.ai.model_runtime.long_context_spool.os.read",
            side_effect=AssertionError("oversize source must not be read"),
        ):
            with self.assertRaisesRegex(LongContextSpoolError, "byte budget"):
                read_selected_sequence(source, limit=64)

    def test_cli_stage_inspect_window_advance(self):
        sequence_file = Path(self.directory.name) / "tokens.json"
        sequence_file.write_bytes(serialize_token_sequence(self.sequence))
        def invoke(*args):
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(cli_main(["--root", str(self.root),
                    "--tokenizer-digest", TOKENIZER, *args]), 0)
            return json.loads(output.getvalue())
        start = invoke("stage", "--sequence-file", str(sequence_file))["checkpoint"]
        self.assertEqual(invoke("inspect", "--checkpoint", start)["total_tokens"], 30)
        self.assertEqual(invoke("window", "--checkpoint", start,
                                "--max-tokens", "3")["window"]["token_ids"], [0, 1, 2])
        child = invoke("advance", "--checkpoint", start,
                       "--consumed-tokens", "3")["checkpoint"]
        self.assertEqual(invoke("window", "--checkpoint", child,
                                "--max-tokens", "3")["window"]["token_ids"], [3, 4, 5])

    def test_audited_window_rejects_missing_grandparent_before_tokens(self):
        genesis = self.stage()
        first = self.spool.advance(
            genesis, expected_tokenizer_digest=TOKENIZER, consumed_tokens=2,
        )
        second = self.spool.advance(
            first, expected_tokenizer_digest=TOKENIZER, consumed_tokens=3,
        )
        self.assertEqual(
            self.spool.audited_next_window(
                second, expected_tokenizer_digest=TOKENIZER,
                max_tokens=2, max_checkpoints=3,
            ).token_ids, (5, 6),
        )
        self.spool._path("checkpoint", genesis).unlink()
        # Ordinary immediate-parent validation is insufficient to detect this.
        self.assertEqual(
            self.spool.next_window(
                second, expected_tokenizer_digest=TOKENIZER, max_tokens=2,
            ).token_ids, (5, 6),
        )
        with self.assertRaises(LongContextSpoolError):
            self.spool.audited_next_window(
                second, expected_tokenizer_digest=TOKENIZER,
                max_tokens=2, max_checkpoints=3,
            )
        with self.assertRaises(LongContextSpoolError):
            self.spool.audited_advance(
                second, expected_tokenizer_digest=TOKENIZER,
                consumed_tokens=1, max_checkpoints=3,
            )

    def test_audited_window_and_advance_require_complete_bounded_history(self):
        genesis = self.stage()
        first = self.spool.audited_advance(
            genesis, expected_tokenizer_digest=TOKENIZER, consumed_tokens=2,
        )
        second = self.spool.audited_advance(
            first, expected_tokenizer_digest=TOKENIZER, consumed_tokens=3,
        )
        with self.assertRaisesRegex(LongContextSpoolError, "audit bound"):
            self.spool.audited_next_window(
                second, expected_tokenizer_digest=TOKENIZER,
                max_tokens=2, max_checkpoints=2,
            )
        with self.assertRaisesRegex(LongContextSpoolError, "audit bound"):
            self.spool.audited_advance(
                second, expected_tokenizer_digest=TOKENIZER,
                consumed_tokens=1, max_checkpoints=2,
            )
        self.assertEqual(
            self.spool.audited_next_window(
                second, expected_tokenizer_digest=TOKENIZER,
                max_tokens=2, max_checkpoints=3,
            ).token_ids, (5, 6),
        )
        with self.assertRaises(LongContextSpoolError):
            self.spool.audited_next_window(
                second, expected_tokenizer_digest=SOURCE,
                max_tokens=2, max_checkpoints=3,
            )

    def test_cli_window_denies_corrupt_history_and_does_not_print_tokens(self):
        genesis = self.stage()
        first = self.spool.advance(
            genesis, expected_tokenizer_digest=TOKENIZER, consumed_tokens=2,
        )
        second = self.spool.advance(
            first, expected_tokenizer_digest=TOKENIZER, consumed_tokens=2,
        )
        self.spool._path("checkpoint", genesis).unlink()
        output = StringIO()
        with redirect_stdout(output):
            with self.assertRaises(SystemExit) as failure:
                cli_main([
                    "--root", str(self.root), "--tokenizer-digest", TOKENIZER,
                    "window", "--checkpoint", second, "--max-tokens", "2",
                ])
        self.assertEqual(failure.exception.code, 2)
        self.assertEqual(output.getvalue(), "")

    def test_bounded_history_audit_survives_restart_and_rejects_missing_ancestor(self):
        start = self.stage()
        child = self.spool.advance(
            start, expected_tokenizer_digest=TOKENIZER, consumed_tokens=3,
        )
        grandchild = self.spool.advance(
            child, expected_tokenizer_digest=TOKENIZER, consumed_tokens=5,
        )
        restarted = LongContextSpool(self.root, disk_reserve_bytes=0)
        audit = restarted.audit_history(
            grandchild, expected_tokenizer_digest=TOKENIZER,
        )
        self.assertEqual(audit["checkpoints_verified"], 3)
        self.assertEqual(audit["genesis_digest"], start)
        self.assertEqual(audit["cursor"], 8)
        self.assertTrue(audit["complete"])
        self.assertFalse(audit["trusted_publisher_attested"])
        with self.assertRaisesRegex(LongContextSpoolError, "audit bound"):
            restarted.audit_history(
                grandchild, expected_tokenizer_digest=TOKENIZER,
                max_checkpoints=2,
            )
        with self.assertRaises(LongContextSpoolError):
            restarted.audit_history(
                grandchild, expected_tokenizer_digest=SOURCE,
            )
        self.spool._path("checkpoint", start).unlink()
        with self.assertRaises(LongContextSpoolError):
            restarted.audit_history(
                grandchild, expected_tokenizer_digest=TOKENIZER,
            )

    def test_cli_history_audit_exposes_no_tokens(self):
        start = self.stage()
        child = self.spool.advance(
            start, expected_tokenizer_digest=TOKENIZER, consumed_tokens=2,
        )
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(cli_main([
                "--root", str(self.root), "--tokenizer-digest", TOKENIZER,
                "audit", "--checkpoint", child, "--max-checkpoints", "2",
            ]), 0)
        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["checkpoints_verified"], 2)
        self.assertEqual(receipt["cursor"], 2)
        self.assertNotIn("token_ids", output.getvalue())

    def test_byte_budget_and_invalid_checkpoint(self):
        tiny = LongContextSpool(self.root / "tiny",
            max_sequence_bytes=1, disk_reserve_bytes=0)
        with self.assertRaises(LongContextSpoolError):
            tiny.stage(self.sequence)
        with self.assertRaises(LongContextSpoolError):
            self.spool.load("not-a-digest", expected_tokenizer_digest=TOKENIZER)

    def test_uncommitted_temporary_file_does_not_change_resume(self):
        start = self.stage()
        path = self.spool._path("checkpoint", start)
        (path.parent / ".interrupted.tmp").write_bytes(b"partial")
        self.assertEqual(self.spool.load(start, expected_tokenizer_digest=TOKENIZER)[0].cursor, 0)



    def test_crash_recovery_reclaims_single_link_partial_temp(self):
        if os.name != "posix":
            self.skipTest("POSIX descriptor custody required")
        start = self.stage()
        bucket = self.spool._path("checkpoint", start).parent
        orphan = bucket / ("." + start + "." + "a" * 16 + ".tmp")
        orphan.write_bytes(b"interrupted")
        orphan.chmod(0o600)
        recovered = LongContextSpool(self.root, disk_reserve_bytes=0)
        result = recovered.recover_abandoned_temps(kind="checkpoint", digest=start)
        self.assertEqual(result["removed"], 1)
        self.assertEqual(result["bytes_reclaimed"], len(b"interrupted"))
        self.assertFalse(orphan.exists())
        self.assertEqual(recovered.load(start, expected_tokenizer_digest=TOKENIZER)[0].cursor, 0)

    def test_crash_recovery_removes_published_temp_link_only(self):
        if os.name != "posix":
            self.skipTest("POSIX descriptor custody required")
        start = self.stage()
        final = self.spool._path("checkpoint", start)
        orphan = final.parent / ("." + start + "." + "b" * 16 + ".tmp")
        os.link(final, orphan)
        result = self.spool.recover_abandoned_temps(kind="checkpoint", digest=start)
        self.assertEqual(result["removed"], 1)
        self.assertEqual(result["bytes_reclaimed"], 0)
        self.assertTrue(final.exists())
        self.assertEqual(final.stat().st_nlink, 1)

    def test_crash_recovery_rejects_external_hardlink_and_symlink(self):
        if os.name != "posix":
            self.skipTest("POSIX descriptor custody required")
        start = self.stage()
        bucket = self.spool._path("checkpoint", start).parent
        outsider = bucket / "unrelated"
        outsider.write_bytes(b"other")
        outsider.chmod(0o600)
        orphan = bucket / ("." + start + "." + "c" * 16 + ".tmp")
        os.link(outsider, orphan)
        with self.assertRaisesRegex(LongContextSpoolError, "hardlink"):
            self.spool.recover_abandoned_temps(kind="checkpoint", digest=start)
        orphan.unlink()
        orphan.symlink_to(outsider)
        with self.assertRaises(LongContextSpoolError):
            self.spool.recover_abandoned_temps(kind="checkpoint", digest=start)
        self.assertEqual(outsider.read_bytes(), b"other")

    def test_crash_recovery_denies_excess_entries_before_deletion(self):
        if os.name != "posix":
            self.skipTest("POSIX descriptor custody required")
        start = self.stage()
        bucket = self.spool._path("checkpoint", start).parent
        for i in range(3):
            orphan = bucket / ("." + start + "." + f"{i:016x}" + ".tmp")
            orphan.write_bytes(b"x")
            orphan.chmod(0o600)
        with self.assertRaisesRegex(LongContextSpoolError, "entry bound"):
            self.spool.recover_abandoned_temps(
                kind="checkpoint", digest=start, max_entries=2,
            )
        self.assertEqual(len(list(bucket.glob(".*.tmp"))), 3)
        result = self.spool.recover_abandoned_temps(kind="checkpoint", digest=start)
        self.assertEqual(result["removed"], 3)


    def test_crash_recovery_is_automatic_for_same_digest_publish(self):
        if os.name != "posix":
            self.skipTest("POSIX descriptor custody required")
        start = self.stage()
        checkpoint = self.spool.load(start, expected_tokenizer_digest=TOKENIZER)[0]
        path = self.spool._path("object", checkpoint.object_digest)
        orphan = path.parent / ("." + checkpoint.object_digest + "." + "d" * 16 + ".tmp")
        orphan.write_bytes(b"orphaned before publish")
        orphan.chmod(0o600)
        self.assertEqual(self.stage(), start)
        self.assertFalse(orphan.exists())

    def test_crash_recovery_byte_budget_is_cumulative(self):
        if os.name != "posix":
            self.skipTest("POSIX descriptor custody required")
        start = self.stage()
        bucket = self.spool._path("checkpoint", start).parent
        for i in range(2):
            orphan = bucket / ("." + start + "." + f"{i:016x}" + ".tmp")
            orphan.write_bytes(b"abc")
            orphan.chmod(0o600)
        with self.assertRaisesRegex(LongContextSpoolError, "byte bound"):
            self.spool.recover_abandoned_temps(
                kind="checkpoint", digest=start, max_bytes=5,
            )
        self.assertEqual(len(list(bucket.glob(".*.tmp"))), 2)
        self.assertTrue((bucket / ("." + start + "." + f"{1:016x}" + ".tmp")).exists())


    def test_inherited_spool_descriptor_cannot_publish_or_resume(self):
        if os.name != "posix":
            self.skipTest("POSIX process ownership required")
        from unittest.mock import patch
        checkpoint = self.stage()
        with patch(
            "skeleton.ai.model_runtime.long_context_spool.os.getpid",
            return_value=os.getpid() + 10000,
        ):
            with self.assertRaisesRegex(LongContextSpoolError, "forked spool"):
                self.spool.stage(self.sequence)
            with self.assertRaisesRegex(LongContextSpoolError, "forked spool"):
                self.spool.load(checkpoint, expected_tokenizer_digest=TOKENIZER)
            with self.assertRaisesRegex(LongContextSpoolError, "forked spool"):
                self.spool.recover_abandoned_temps(
                    kind="checkpoint", digest=checkpoint,
                )
        self.assertEqual(
            self.spool.load(checkpoint, expected_tokenizer_digest=TOKENIZER)[0].cursor,
            0,
        )

    def test_posix_world_readable_root_is_rejected(self):
        if os.name != "posix":
            self.skipTest("POSIX ownership and mode contract")
        self.spool.close()
        self.root.chmod(0o755)
        with self.assertRaisesRegex(LongContextSpoolError, "root permissions"):
            LongContextSpool(self.root, disk_reserve_bytes=0)

    def test_posix_world_readable_bucket_is_rejected(self):
        if os.name != "posix":
            self.skipTest("POSIX ownership and mode contract")
        start = self.stage()
        bucket = self.spool._path("checkpoint", start).parent
        bucket.chmod(0o755)
        with self.assertRaisesRegex(LongContextSpoolError, "bucket"):
            self.spool.load(start, expected_tokenizer_digest=TOKENIZER)

    def test_posix_world_readable_object_is_never_accepted(self):
        if os.name != "posix":
            self.skipTest("POSIX ownership and mode contract")
        start = self.stage()
        checkpoint, _ = self.spool.load(
            start, expected_tokenizer_digest=TOKENIZER,
        )
        path = self.spool._path("object", checkpoint.object_digest)
        path.chmod(0o644)
        with self.assertRaisesRegex(LongContextSpoolError, "owner or mode"):
            self.spool.load(start, expected_tokenizer_digest=TOKENIZER)
        with self.assertRaisesRegex(LongContextSpoolError, "owner or mode"):
            self.spool.stage(self.sequence)


    def test_posix_temp_name_swap_during_link_never_publishes_trusted_progress(self):
        if os.name != "posix":
            self.skipTest("POSIX inode custody required")
        from unittest.mock import patch
        original_link = os.link

        def replace_temp_before_link(src, dst, **kwargs):
            bucket_fd = kwargs["src_dir_fd"]
            os.unlink(src, dir_fd=bucket_fd)
            forged_fd = os.open(
                src, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600, dir_fd=bucket_fd,
            )
            try:
                os.write(forged_fd, b"forged replacement")
            finally:
                os.close(forged_fd)
            return original_link(src, dst, **kwargs)

        with patch(
            "skeleton.ai.model_runtime.long_context_spool.os.link",
            side_effect=replace_temp_before_link,
        ):
            with self.assertRaisesRegex(LongContextSpoolError, "publication temp replaced"):
                self.stage()
        # The digest-addressed rogue final is never silently accepted.
        with self.assertRaises(LongContextSpoolError):
            self.stage()

    def test_posix_final_inode_replacement_after_link_is_not_a_receipt(self):
        if os.name != "posix":
            self.skipTest("POSIX inode custody required")
        from unittest.mock import patch
        original_link = os.link

        def replace_final_after_link(src, dst, **kwargs):
            original_link(src, dst, **kwargs)
            bucket_fd = kwargs["dst_dir_fd"]
            os.unlink(dst, dir_fd=bucket_fd)
            rogue_fd = os.open(
                dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600, dir_fd=bucket_fd,
            )
            try:
                os.write(rogue_fd, b"forged final")
            finally:
                os.close(rogue_fd)

        with patch(
            "skeleton.ai.model_runtime.long_context_spool.os.link",
            side_effect=replace_final_after_link,
        ):
            with self.assertRaisesRegex(LongContextSpoolError, "published spool inode mismatch"):
                self.stage()
        with self.assertRaises(LongContextSpoolError):
            self.stage()


if __name__ == "__main__":
    unittest.main()
