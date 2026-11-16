"""Qualification harness contract regressions; these are not live model runs."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts.qualify_exact_gguf_bridge import (
    QualificationError, _canonical, _assert_sha, _HEX, _assert_runtime,
    _must_deny, publish,
)


def test_sha_and_runtime_pin_rejection(tmp_path):
    runtime = tmp_path / "bridge"
    runtime.write_bytes(b"not a model runner")
    runtime.chmod(0o700)
    digest = hashlib.sha256(runtime.read_bytes()).hexdigest()
    _assert_runtime(runtime, digest)
    with pytest.raises(QualificationError):
        _assert_runtime(runtime, "0" * 64)
    for value in (None, True, "A" * 64, "a" * 63):
        with pytest.raises(QualificationError):
            _assert_sha(value, _HEX)
    symlink = tmp_path / "alias"
    symlink.symlink_to(runtime)
    with pytest.raises(QualificationError):
        _assert_runtime(symlink, digest)


def test_receipt_create_only_and_canonical(tmp_path):
    output = tmp_path / "receipt.json"
    receipt = {"scope": "fixture-only", "source_head": "a" * 40, "tokens": [1, 2]}
    publish(output, receipt)
    assert output.read_bytes() == _canonical(receipt) + b"\n"
    assert json.loads(output.read_bytes()) == receipt
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(QualificationError):
        publish(output, {"scope": "replacement"})
    assert json.loads(output.read_bytes()) == receipt
    assert list(tmp_path.iterdir()) == [output]


def test_negative_admission_must_actually_deny():
    with pytest.raises(QualificationError):
        _must_deny(lambda: None, (ValueError,))

    def reject():
        raise ValueError("denied")

    _must_deny(reject, (ValueError,))
    with pytest.raises(ValueError):
        _must_deny(reject, (RuntimeError,))
