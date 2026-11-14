"""Recovery regressions: bounded authenticated requests and private custody."""
from dataclasses import replace
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
import tempfile

import pytest

from skeleton.ai.runtime.operational_ai.guarded_request.contracts import canonical_bytes
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied
from skeleton.ai.runtime.operational_ai.guarded_request.identities import Scope
from skeleton.ai.runtime.operational_ai.guarded_request.nonce_fence import NonceFence
from skeleton.ai.runtime.operational_ai.guarded_request.signed_envelope import SignedEnvelope, MAX_TTL_MS
from skeleton.ai.runtime.operational_ai.model.gguf.file_guard import open_private_artifact_root

KEY = bytes(range(32))
PAYLOAD = "a" * 64


def test_scope_key_roundtrip_and_principal_isolation():
    user = Scope("tenant", "alice", "session", "b" * 64)
    other = Scope("tenant", "bob", "session", "b" * 64)
    with sqlite3.connect(":memory:", isolation_level=None) as db:
        fence = NonceFence(db)
        assert fence.reserve(user, "nonce", 1, PAYLOAD) == "admitted"
        assert fence.reserve(user.key, "nonce", 1, PAYLOAD) == "replayed"
        assert fence.reserve(other, "nonce", 1, PAYLOAD) == "admitted"
        assert fence.head(user.key) == 1
        assert fence.head(other) == 1
        with pytest.raises(GateDenied):
            fence.reserve(user.key + "/extra", "nonce", 2, PAYLOAD)


@pytest.mark.parametrize("changes", [
    {"expires_ms": 100 + MAX_TTL_MS + 1},
    {"sequence": True},
    {"nonce": "invalid/nonce"},
    {"issued_ms": True},
])
def test_verifier_rejects_invalid_even_authenticated_envelopes(changes):
    scope = Scope("tenant", "alice", "session", "b" * 64)
    envelope = SignedEnvelope.sign(
        KEY, scope=scope, nonce="nonce", sequence=1,
        payload_sha256=PAYLOAD, issued_ms=100, expires_ms=200,
    )
    malformed = replace(envelope, **changes)
    # Hold the key legitimately: verification must enforce the shape even
    # when authenticity succeeds. A test-only key and payload are used.
    mac = hmac.new(KEY, canonical_bytes(malformed._payload()), hashlib.sha256).hexdigest()
    malformed = replace(malformed, mac_sha256=mac)
    with pytest.raises(GateDenied):
        malformed.verify(KEY, scope=scope, payload_sha256=PAYLOAD, now_ms=150)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_private_artifact_root_accepts_concrete_path_and_rejects_symlink():
    with tempfile.TemporaryDirectory(dir=Path.home()) as temp:
        parent = Path(temp)
        destination = parent / "artifact"
        fd = open_private_artifact_root(destination, create=True)
        try:
            assert os.fstat(fd).st_mode & 0o077 == 0
        finally:
            os.close(fd)
        alias = parent / "alias"
        alias.symlink_to(destination, target_is_directory=True)
        with pytest.raises((OSError, ValueError)):
            open_private_artifact_root(alias / "unexpected", create=True)
        assert not (destination / "unexpected").exists()
        fd = open_private_artifact_root(destination)
        os.close(fd)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_artifact_creation_does_not_cross_writable_ancestor():
    with tempfile.TemporaryDirectory(dir=Path.home()) as temp:
        unsafe = Path(temp) / "unsafe"
        unsafe.mkdir()
        unsafe.chmod(0o777)
        with pytest.raises((OSError, ValueError)):
            open_private_artifact_root(unsafe / "child", create=True)
        assert not (unsafe / "child").exists()
