"""POSIX subprocess custody fixtures; no real weight quality claims."""
import hashlib
import os
from pathlib import Path
import struct
import sys

import pytest

from scripts.quantize_consumer_gguf import build_candidate, recipe


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_tensor_overrides_are_explicit_sorted_and_escaped():
    assert recipe("Q4_K_M", ["output.weight=q8_0", "blk.0.attn_q.weight=f16"],
                  threads=4, has_imatrix=True) == (
        "--tensor-type", r"^blk\.0\.attn_q\.weight$=f16",
        "--tensor-type", r"^output\.weight$=q8_0")


@pytest.mark.parametrize("overrides", [
    [".*=q8_0"], ["--model=f16"], ["output.weight=Q4_K_M"],
    ["output.weight=q8_0", "output.weight=f16"],
])
def test_invalid_tensor_override_denied(overrides):
    with pytest.raises(ValueError):
        recipe("Q4_K_M", overrides, threads=4, has_imatrix=False)


@pytest.fixture
def invocation(tmp_path):
    if os.name != "posix":
        pytest.skip("descriptor custody POSIX only")
    source = tmp_path / "base.gguf"
    source.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 1, 0) + bytes(1024))
    quantizer = tmp_path / "fixture-quantize"
    # This executable only copies a synthetic fixture. It is not llama.cpp.
    quantizer.write_text(f"#!{sys.executable}\nimport shutil,sys\nshutil.copyfile(sys.argv[-4],sys.argv[-3])\n")
    quantizer.chmod(0o700)
    return dict(quantizer=quantizer, quantizer_sha256=digest(quantizer), source=source,
                source_sha256=digest(source), output=tmp_path/"candidate.gguf",
                scheme="Q4_K_M", max_output_bytes=4096, timeout_seconds=10)


def test_create_only_candidate_with_pinned_fixture(invocation):
    report = build_candidate(**invocation)
    assert report["activation_authorized"] is False
    assert report["candidate_sha256"] == digest(invocation["output"])
    assert report["status"] == "candidate_created_not_qualified"
    with pytest.raises(FileExistsError):
        build_candidate(**invocation)


def test_bad_digest_never_publishes(invocation):
    invocation["quantizer_sha256"] = "0"*64
    with pytest.raises(ValueError, match="SHA-256"):
        build_candidate(**invocation)
    assert not invocation["output"].exists()


def test_failed_child_does_not_publish(invocation):
    q = invocation["quantizer"]
    q.write_text(f"#!{sys.executable}\nraise SystemExit(7)\n")
    invocation["quantizer_sha256"] = digest(q)
    with pytest.raises(RuntimeError, match="successful candidate"):
        build_candidate(**invocation)
    assert not invocation["output"].exists()
