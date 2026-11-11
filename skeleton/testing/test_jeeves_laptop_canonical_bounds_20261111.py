"""Bounded Jeeves source-evidence canonicalization and mirror regressions.

All cases are source-only: no native GGUF, device, deployment, or release proof.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import unittest
from unittest import mock

from skeleton.jeeves.native_fabric.laptop_ops import contracts


class TestBoundedJeevesCanonicalEvidence(unittest.TestCase):
    def test_valid_evidence_keeps_exact_json_and_fingerprint(self):
        value = {
            "domain": "bootstrap",
            "stages": [{"name": "source", "verified": True}],
            "unicode": "😀\u007f",
            "limits": (0, 1.25, None, False),
        }
        expected = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
        self.assertEqual(contracts.canonical(value), expected)
        self.assertEqual(contracts.fingerprint(value), sha256(expected).hexdigest())

    def test_oversized_single_and_aggregate_text_denied_before_encoding(self):
        candidates = (
            {"payload": "x" * 65_537},
            ["x" * 4096] * 17,
            {("k" * 65_537): 1},
        )
        for value in candidates:
            with self.subTest(case=type(value).__name__):
                with mock.patch.object(
                    contracts.json, "dumps",
                    side_effect=AssertionError("JSON allocation was reached"),
                ):
                    with self.assertRaises(contracts.LaptopGateHold):
                        contracts.canonical(value)

    def test_deep_cycle_large_integer_and_large_container_denied_preencoder(self):
        nested: object = None
        for _ in range(65):
            nested = [nested]
        cyclic: list[object] = []
        cyclic.append(cyclic)
        cases = (
            (nested, 65536),
            (cyclic, 65536),
            (1 << 300_000, 65536),
            (list(range(33)), 32),
        )
        for value, ceiling in cases:
            with self.subTest(kind=type(value).__name__, ceiling=ceiling):
                with mock.patch.object(
                    contracts.json, "dumps",
                    side_effect=AssertionError("JSON allocation was reached"),
                ):
                    with self.assertRaises(contracts.LaptopGateHold):
                        contracts.canonical(value, maximum=ceiling)

    def test_foreign_values_and_nonstring_keys_denied_preencoder(self):
        for value in ({"unsafe": object()}, {7: "number key"}, {"unsafe": bytearray(4)}):
            with self.subTest(kind=repr(type(next(iter(value.values()))))):
                with mock.patch.object(
                    contracts.json, "dumps",
                    side_effect=AssertionError("JSON allocation was reached"),
                ):
                    with self.assertRaises(contracts.LaptopGateHold):
                        contracts.canonical(value)

    def test_invalid_ceiling_is_denied_before_encoding(self):
        for ceiling in (0, -1, True, 1.5, None, "65536"):
            with self.subTest(ceiling=ceiling):
                with mock.patch.object(
                    contracts.json, "dumps",
                    side_effect=AssertionError("JSON allocation was reached"),
                ):
                    with self.assertRaises(contracts.LaptopGateHold):
                        contracts.canonical({"ok": True}, maximum=ceiling)

    def test_json_escape_overhead_and_nonfinite_values_still_fail_closed(self):
        with self.assertRaises(contracts.LaptopGateHold):
            contracts.canonical({"del": "\u007f"}, maximum=8)
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(contracts.LaptopGateHold):
                    contracts.canonical({"float": value})

    def test_complete_twenty_domain_bundle_denies_large_direct_evidence(self):
        # Exercise the real source-bundle admission boundary, not only the
        # canonical helper; no native model or device is activated.
        from skeleton.jeeves.native_fabric.laptop_ops.batch.fixtures import successful_bundle
        from skeleton.jeeves.native_fabric.laptop_ops.batch.runner import evaluate_bundle

        evidence = successful_bundle()
        domain = next(iter(evidence))
        stage = next(iter(evidence[domain]))
        evidence[domain][stage]["untrusted_extra"] = "x" * 65_537
        with mock.patch.object(
            contracts.json, "dumps",
            side_effect=AssertionError("JSON allocation was reached"),
        ):
            with self.assertRaises(contracts.LaptopGateHold):
                evaluate_bundle(evidence)

    def test_aggregate_scalars_and_container_overhead_denied_preencoder(self):
        # Each payload previously fit the traversal and string-only budget,
        # yet could allocate oversized JSON before the final byte check.
        cases = (
            ([(1 << 500)] * 20, 1024),
            ([1e-300] * 200, 512),
            ([""] * 100, 128),
        )
        for value, ceiling in cases:
            with self.subTest(kind=type(value[0]).__name__, ceiling=ceiling):
                with mock.patch.object(
                    contracts.json, "dumps",
                    side_effect=AssertionError("JSON allocation was reached"),
                ):
                    with self.assertRaises(contracts.LaptopGateHold):
                        contracts.canonical(value, maximum=ceiling)

    def test_exact_small_valid_json_budget_preserved(self):
        for value in ({"": 0}, {"x": 1.25}, [True, None, ""]):
            expected = json.dumps(
                value, sort_keys=True, separators=(",", ":"),
                ensure_ascii=True, allow_nan=False,
            ).encode("ascii")
            with self.subTest(value=value):
                self.assertEqual(
                    contracts.canonical(value, maximum=len(expected)),
                    expected,
                )

    def test_byte_identical_canonical_mirror(self):
        root = Path(__file__).resolve().parents[1]
        canonical = root / "jeeves/native_fabric/laptop_ops/contracts.py"
        mirror = root / "ai/agents/jeeves/native_fabric/laptop_ops/contracts.py"
        self.assertEqual(canonical.read_bytes(), mirror.read_bytes())


    def test_qualification_workflow_executes_exact_immutable_head(self):
        workflow = (
            Path(__file__).resolve().parents[2]
            / ".github/workflows/jeeves-bounded-canonical-evidence.yml"
        ).read_text(encoding="utf-8")
        expected_ref = 'ref: ${{ github.event.pull_request.head.sha }}'
        expected_guard = 'run: test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"'
        self.assertEqual(workflow.count(expected_ref), 1)
        self.assertEqual(workflow.count(expected_guard), 1)
        self.assertIn('EXPECTED_SHA: ${{ github.event.pull_request.head.sha }}', workflow)
        self.assertLess(workflow.index(expected_ref), workflow.index(expected_guard))
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("fetch-depth: 1", workflow)


if __name__ == "__main__":
    unittest.main()
