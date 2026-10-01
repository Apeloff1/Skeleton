from __future__ import annotations

import sys
import unittest

from skeleton.native.isolation import (
    AcceleratorIsolationError,
    run_json_process,
)


_ECHO = (
    "import json,sys;"
    "p=json.loads(sys.stdin.buffer.read().decode('utf-8'));"
    "sys.stdout.write(json.dumps({'seen':p},sort_keys=True))"
)


class AccelerationIsolationTests(unittest.TestCase):
    def test_bounded_json_subprocess_roundtrip(self) -> None:
        result = run_json_process(
            [sys.executable, "-c", _ECHO],
            {"value": 7},
            timeout_s=5,
        )
        self.assertEqual(result.payload, {"seen": {"value": 7}})

    def test_input_bound_fails_closed(self) -> None:
        with self.assertRaisesRegex(AcceleratorIsolationError, "input bound"):
            run_json_process(
                [sys.executable, "-c", _ECHO],
                {"value": "x" * 1000},
                timeout_s=5,
                max_input_bytes=10,
            )

    def test_environment_allowlist_cannot_expose_arbitrary_host_values(self) -> None:
        with self.assertRaisesRegex(
            AcceleratorIsolationError,
            "exceeds safe allowlist",
        ):
            run_json_process(
                [sys.executable, "-c", _ECHO],
                {},
                timeout_s=5,
                allowed_environment=("PATH", "GITHUB_TOKEN"),
            )

    def test_nonzero_child_is_not_a_fallback_success(self) -> None:
        with self.assertRaisesRegex(AcceleratorIsolationError, "exited"):
            run_json_process(
                [sys.executable, "-c", "raise SystemExit(3)"],
                {},
                timeout_s=5,
            )


    def test_rejects_streaming_output_over_bound(self) -> None:
        command = [
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('x' * 200000); sys.stdout.flush()",
        ]
        with self.assertRaisesRegex(
            MODULE.AcceleratorIsolationError,
            "stdout exceeds output bound",
        ):
            MODULE.run_json_process(
                command,
                {"request": "bounded"},
                timeout_s=5,
                max_output_bytes=1024,
            )


if __name__ == "__main__":
    unittest.main()
