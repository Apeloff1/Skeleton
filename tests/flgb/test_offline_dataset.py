"""Real offline document -> curated corpus -> native CPU model acceptance."""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.app.local_ai import load_native_checkpoint
from skeleton.app.local_ai_dataset import (
    DATASET_SCHEMA,
    OfflineDatasetError,
    prepare_native_dataset,
    verify_native_dataset,
)
from skeleton.app.local_ai_training import train_local_text
from skeleton.cortex.port import tokens


def _sources(root: Path) -> Path:
    source = root / "source"
    source.mkdir()
    (source / "a.txt").write_text(
        "user hello assistant alpha\nuser world assistant beta\n",
        encoding="utf-8",
    )
    (source / "b.txt").write_text(
        "world beta alpha hello\nworld assistant user alpha\n",
        encoding="utf-8",
    )
    (source / "c.txt").write_text(
        "assistant beta world user\nbeta hello alpha world\n",
        encoding="utf-8",
    )
    (source / "d.txt").write_text(
        "hello alpha user beta\nbeta assistant hello world\n",
        encoding="utf-8",
    )
    return source


class TestNativeDatasetCuration(unittest.TestCase):
    def test_document_split_is_reproducible_and_source_bound(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _sources(root)
            result = prepare_native_dataset(source, root / "out-a", seed=13)
            again = prepare_native_dataset(source, root / "out-b", seed=13)
            self.assertEqual(result["dataset_id"], again["dataset_id"])
            self.assertEqual(result["training_sha256"], again["training_sha256"])
            self.assertEqual(result["validation_sha256"], again["validation_sha256"])
            self.assertTrue(result["disjoint_document_split"])
            self.assertEqual(result["source_count"], 4)
            self.assertEqual(result["training_sources"], 3)
            self.assertEqual(result["validation_sources"], 1)
            self.assertGreater(result["training_tokens"], 0)
            self.assertGreater(result["validation_tokens"], 0)
            manifest = json.loads((root / "out-a" / "dataset.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], DATASET_SCHEMA)
            self.assertEqual(manifest["dataset_id"], result["dataset_id"])
            self.assertFalse(manifest["model_quality_certified"])
            self.assertFalse(manifest["historical_data_disjointness_proven"])
            training = (root / "out-a" / "train.txt").read_bytes()
            validation = (root / "out-a" / "validation.txt").read_bytes()
            self.assertEqual(result["training_sha256"], hashlib.sha256(training).hexdigest())
            self.assertEqual(result["validation_sha256"], hashlib.sha256(validation).hexdigest())
            train_sequences = {tokens(line) for line in training.decode().splitlines()}
            validation_sequences = {tokens(line) for line in validation.decode().splitlines()}
            self.assertFalse(train_sequences & validation_sequences)

    def test_real_prepared_corpus_trains_and_loads_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _sources(root)
            curated = prepare_native_dataset(source, root / "prepared")
            artifact = root / "checkpoint.json"
            trained = train_local_text(curated["train_file"], artifact, epochs=1)
            verified = load_native_checkpoint(artifact)
            self.assertEqual(verified.model_digest, trained.model_digest)
            self.assertEqual(verified.tokenizer_digest, trained.tokenizer_digest)
            self.assertGreater(trained.training_steps, 0)
            self.assertTrue(artifact.is_file())
            self.assertEqual(
                trained.source_sha256,
                curated["training_sha256"],
            )

    def test_cli_and_frozen_launcher_have_same_dataset_path(self) -> None:
        from skeleton.app.cli import run_app_cli
        from skeleton.app.windows_launcher import main as frozen_main

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _sources(root)
            output = StringIO()
            with redirect_stdout(output):
                status = run_app_cli([
                    "local-ai", "--prepare-dataset", str(source),
                    "--dataset-output", str(root / "first"), "--split-seed", "13",
                    "--validation-percent", "25", "--json",
                ])
            self.assertEqual(status, 0, output.getvalue())
            info = json.loads(output.getvalue())
            self.assertEqual(info["source_count"], 4)
            output = StringIO()
            with redirect_stdout(output):
                status = frozen_main([
                    "--offline-command", "local-ai",
                    "--prepare-dataset", str(source),
                    "--dataset-output", str(root / "second"),
                    "--split-seed", "13", "--json",
                ])
            self.assertEqual(status, 0, output.getvalue())
            self.assertEqual(
                json.loads(output.getvalue())["dataset_id"],
                info["dataset_id"],
            )

    def test_refuses_duplicate_normalized_sources_without_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _sources(root)
            (source / "d.txt").write_text(
                "USER: hello, ASSISTANT alpha\nworld alpha beta hello\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(OfflineDatasetError, "duplicate normalized"):
                prepare_native_dataset(source, root / "output")
            self.assertFalse((root / "output").exists())

    def test_rejects_identical_source_bytes_and_hardlinks(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _sources(root)
            (source / "d.txt").write_bytes((source / "a.txt").read_bytes())
            with self.assertRaises(OfflineDatasetError):
                prepare_native_dataset(source, root / "not-created")
            self.assertFalse((root / "not-created").exists())
            (source / "d.txt").unlink()
            os.link(source / "a.txt", source / "d.txt")
            with self.assertRaisesRegex(OfflineDatasetError, "same underlying file"):
                prepare_native_dataset(source, root / "not-created")
            self.assertFalse((root / "not-created").exists())

    def test_rejects_symlinks_unknown_entries_and_preexisting_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _sources(root)
            target = root / "occupied"
            target.mkdir()
            (target / "keep.txt").write_text("DO NOT MODIFY", encoding="utf-8")
            with self.assertRaisesRegex(OfflineDatasetError, "must not exist"):
                prepare_native_dataset(source, target)
            self.assertEqual((target / "keep.txt").read_text(), "DO NOT MODIFY")
            odd = source / "ignore.json"
            odd.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(OfflineDatasetError, "only flat .txt"):
                prepare_native_dataset(source, root / "not-created")
            odd.unlink()
            link = source / "link.txt"
            try:
                link.symlink_to(source / "a.txt")
            except OSError:
                self.skipTest("symlinks unsupported")
            with self.assertRaises(OfflineDatasetError):
                prepare_native_dataset(source, root / "not-created")

    def test_detects_changed_originals_before_output_publication(self) -> None:
        import skeleton.app.local_ai_dataset as module

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _sources(root)
            original_scan = module._scan_sources

            def mutate_after_scan(selected):
                snapshot = original_scan(selected)
                (source / "a.txt").write_text(
                    "user alpha beta assistant\n", encoding="utf-8",
                )
                return snapshot

            with patch.object(module, "_scan_sources", side_effect=mutate_after_scan):
                with self.assertRaisesRegex(OfflineDatasetError, "source changed"):
                    prepare_native_dataset(source, root / "not-created")
            self.assertFalse((root / "not-created").exists())

    def test_no_manifest_on_interrupted_publication(self) -> None:
        import skeleton.app.local_ai_dataset as module

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _sources(root)
            dest = root / "attempt"
            original_writer = module._write_exclusive
            count = 0

            def interrupted(path, data):
                nonlocal count
                count += 1
                if count == 2:
                    raise OSError("simulated write interruption")
                return original_writer(path, data)

            with patch.object(module, "_write_exclusive", new=interrupted):
                with self.assertRaisesRegex(OfflineDatasetError, "publish"):
                    prepare_native_dataset(source, dest)
            self.assertFalse(dest.exists())
            self.assertEqual(count, 2)

    def test_readonly_verification_checks_prepared_data_and_originals(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _sources(root)
            out = root / "curated"
            expected = prepare_native_dataset(source, out, seed=13)
            prepared = verify_native_dataset(out)
            with_sources = verify_native_dataset(out, original_sources=source)
            self.assertEqual(expected["dataset_id"], prepared["dataset_id"])
            self.assertTrue(prepared["prepared_outputs_verified"])
            self.assertFalse(prepared["original_sources_verified"])
            self.assertTrue(with_sources["original_sources_verified"])
            self.assertFalse(with_sources["historical_data_disjointness_proven"])
            self.assertFalse(with_sources["model_quality_certified"])
            before = {item.name: item.read_bytes() for item in out.iterdir()}
            self.assertEqual(before, {item.name: item.read_bytes() for item in out.iterdir()})

    def test_byte_level_corruption_of_output_cannot_pass_manifest_verification(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _sources(root)
            out = root / "curated"
            prepare_native_dataset(source, out)
            train_path = out / "train.txt"
            before = train_path.read_bytes()
            train_path.write_bytes(before.replace(b"world", b"alpha", 1))
            with self.assertRaises(OfflineDatasetError):
                verify_native_dataset(out)
            train_path.write_bytes(before)
            manifest_path = out / "dataset.json"
            old = manifest_path.read_bytes()
            tampered = json.loads(old)
            tampered["dataset_id"] = "0" * 64
            manifest_path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaises(OfflineDatasetError):
                verify_native_dataset(out)
            manifest_path.write_bytes(old)
            self.assertTrue(verify_native_dataset(out)["prepared_outputs_verified"])

    def test_original_source_modification_cannot_forge_verified_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _sources(root)
            out = root / "curated"
            prepare_native_dataset(source, out)
            (source / "a.txt").write_text(
                "user beta assistant alpha\nuser world assistant beta\n",
                encoding="utf-8",
            )
            self.assertTrue(verify_native_dataset(out)["prepared_outputs_verified"])
            with self.assertRaises(OfflineDatasetError):
                verify_native_dataset(out, original_sources=source)

    def test_manifest_duplicate_fields_or_symlink_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _sources(root)
            out = root / "curated"
            prepare_native_dataset(source, out)
            manifest = out / "dataset.json"
            original = manifest.read_bytes()
            manifest.write_bytes(original.replace(
                b'"schema":', b'"schema":"duplicate","schema":', 1,
            ))
            with self.assertRaisesRegex(OfflineDatasetError, "duplicate"):
                verify_native_dataset(out)
            manifest.write_bytes(original)
            train = out / "train.txt"
            saved = train.read_bytes()
            train.unlink()
            external = root / "outside.txt"
            external.write_bytes(saved)
            try:
                train.symlink_to(external)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaises(OfflineDatasetError):
                verify_native_dataset(out)

    def test_verification_cli_and_frozen_exe_are_readonly(self) -> None:
        from skeleton.app.cli import run_app_cli
        from skeleton.app.windows_launcher import main as frozen_main

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _sources(root)
            out = root / "curated"
            prepare_native_dataset(source, out)
            original = {p.name: p.read_bytes() for p in out.iterdir()}
            output = StringIO()
            with redirect_stdout(output):
                code = run_app_cli([
                    "local-ai", "--verify-dataset", str(out),
                    "--verify-sources", str(source), "--json",
                ])
            self.assertEqual(code, 0, output.getvalue())
            self.assertTrue(json.loads(output.getvalue())["original_sources_verified"])
            output = StringIO()
            with redirect_stdout(output):
                code = frozen_main([
                    "--offline-command", "local-ai", "--verify-dataset",
                    str(out), "--json",
                ])
            self.assertEqual(code, 0, output.getvalue())
            self.assertFalse(json.loads(output.getvalue())["original_sources_verified"])
            self.assertEqual(original, {p.name: p.read_bytes() for p in out.iterdir()})
            for invalid in (
                ["--verify-sources", str(source)],
                ["--verify-dataset", str(out), "--model", "checkpoint.json"],
                ["--verify-dataset", str(out), "--train-corpus", "train.txt"],
                ["--verify-dataset", str(out), "--split-seed", "10"],
            ):
                with redirect_stdout(StringIO()):
                    self.assertEqual(run_app_cli(["local-ai", *invalid]), 2)

    def test_rejects_invalid_budgets_and_mixed_cli_modes(self) -> None:
        from skeleton.app.cli import run_app_cli

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _sources(root)
            for bad_percent in (0, 9, 51, 101, True):
                with self.subTest(percent=bad_percent):
                    with self.assertRaises(OfflineDatasetError):
                        prepare_native_dataset(
                            source, root / "unused", validation_percent=bad_percent,
                        )
                    self.assertFalse((root / "unused").exists())
            with self.assertRaises(OfflineDatasetError):
                prepare_native_dataset(source, root / "unused", seed=-1)
            with self.assertRaises(OfflineDatasetError):
                prepare_native_dataset(source, root / "unused", seed=2**32)
            for args in (
                ["--prepare-dataset", str(source)],
                ["--dataset-output", str(root / "unused")],
                ["--prepare-dataset", str(source), "--dataset-output", str(root / "unused"), "--model", "checkpoint.json"],
                ["--validation-percent", "35"],
                ["--split-seed", "99"],
                ["--prepare-dataset", str(source), "--dataset-output", str(root / "unused"), "--epochs", "2"],
            ):
                with self.subTest(args=args):
                    with redirect_stdout(StringIO()):
                        self.assertEqual(run_app_cli(["local-ai", *args]), 2)


if __name__ == "__main__":
    unittest.main()
