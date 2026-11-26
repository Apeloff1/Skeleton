"""Offline scale and hostile-input acceptance; synthetic URLs are fixtures only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.webcrawler.source_catalogue_bulk import expand, TARGET_100X, _publish_new
from skeleton.ai.webcrawler.source_navigation import Catalogue, REGISTRY_PATH, rank_sources


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def row(n):
    # Never dispatched; synthetic path under an existing public hostname.
    return {"name": f"Fixture game resource {n}", "url": f"https://github.com/fixture-corpus/project-{n}/",
            "family": "engine-tools", "kind": "documentation",
            "tags": "fixture game engine rendering development"}


class BulkCatalogueTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.base_path = self.root / "base.json"
        self.raw = REGISTRY_PATH.read_bytes()
        self.base_path.write_bytes(self.raw)
        self.export_path = self.root / "fixture.jsonl"

    def expansion(self, rows, **options):
        raw = b"".join(json.dumps(item).encode("utf-8")+b"\n" for item in rows)
        self.export_path.write_bytes(raw)
        args = dict(expected_base_sha256=sha(self.raw), expected_export_sha256=sha(raw),
                    publisher="https://github.com/fixture-corpus/", rights_reference="synthetic test only")
        args.update(options)
        return expand(self.base_path, self.export_path, **args)

    def test_exact_source_and_conflict_custody(self):
        a = row(1)
        b = dict(a, name="conflicting label")
        output, receipt = self.expansion([a, a, b, row(2)])
        base = Catalogue(self.raw)
        result = Catalogue(output)
        self.assertEqual(receipt["added_sources"], 2)
        self.assertEqual(receipt["duplicate_export_rows"], 1)
        self.assertEqual(receipt["conflicting_metadata_held"], 1)
        self.assertEqual(receipt["sources"], len(base.rows)+2)
        self.assertEqual(receipt["output_sha256"], sha(output))
        self.assertFalse(receipt["network_authorized"])
        self.assertFalse(receipt["rights_verified"])
        self.assertEqual(result.match(a["url"]).name, a["name"])

    def test_wrong_digest_and_minimum_fail(self):
        with self.assertRaisesRegex(ValueError, "export digest mismatch"):
            self.expansion([row(1)], expected_export_sha256="0"*64)
        with self.assertRaisesRegex(ValueError, "base catalogue digest mismatch"):
            self.expansion([row(1)], expected_base_sha256="0"*64)
        with self.assertRaisesRegex(ValueError, "minimum populated"):
            self.expansion([row(1)], minimum=65_536)

    def test_no_private_or_fabricated_authority(self):
        for url in ("https://user@github.com/project/",
                    "https://github.com/path?token=secret",
                    "https://127.0.0.1/path",
                    "https://github.com/%2e%2e/path/",
                    "https://private.internal/path",
                    "file:///tmp/data"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    self.expansion([dict(row(1), url=url)])
        with self.assertRaises(ValueError):
            self.expansion([dict(row(1), tags="bad\ntext")])
        with self.assertRaises(ValueError):
            self.expansion([row(1)], rights_reference="")

    def test_non_replace_publication(self):
        path = self.root / "out.json"
        _publish_new(path, b"first")
        with self.assertRaises(FileExistsError):
            _publish_new(path, b"second")
        self.assertEqual(path.read_bytes(), b"first")
        self.assertFalse(list(self.root.glob(".dragon-catalogue-*")))

    def test_hundredfold_fixture_and_rank_pool(self):
        # Test actual admission and ranking at the target count, not an
        # assertion that these fixture URLs are real external sources.
        current = len(json.loads(self.raw)["sources"])
        target = max(TARGET_100X, current * 10)
        count = max(0, target-current)
        output, receipt = self.expansion((row(i) for i in range(count)), minimum=target)
        self.assertEqual(receipt["sources"], target)
        self.assertTrue(receipt["target_100x_reached"])
        registry = Catalogue(output)
        self.assertEqual(len(registry.by_id), target)
        if count:
            last = row(count-1)
            self.assertEqual(registry.match(last["url"]+"docs").name, last["name"])
        plan = rank_sources("World of Warcraft raid combat logs addons", limit=48, registry=registry)
        self.assertGreater(plan["distinct_hosts"], 1)
        self.assertIn("www.warcraftlogs.com", {item["host"] for item in plan["sources"]})
        self.assertFalse(plan["network_authorized"])


if __name__ == "__main__":
    unittest.main()
