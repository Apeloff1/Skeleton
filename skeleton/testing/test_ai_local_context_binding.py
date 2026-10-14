from __future__ import annotations
import pytest
from skeleton.ai.runtime.inference.local import LocalInferenceRequest

def test_context_digest_changes_local_request_identity() -> None:
    a=LocalInferenceRequest(prompt="same",context_digest="a"*64)
    b=LocalInferenceRequest(prompt="same",context_digest="b"*64)
    assert a.digest!=b.digest

def test_local_request_rejects_malformed_context_digest() -> None:
    with pytest.raises(ValueError,match="context_digest"):
        LocalInferenceRequest(prompt="x",context_digest="not-a-digest")

def test_local_request_without_context_remains_supported() -> None:
    request=LocalInferenceRequest(prompt="x")
    assert request.context_digest is None
    assert len(request.digest)==64
