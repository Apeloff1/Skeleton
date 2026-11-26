"""Envelope format + key providers. Test keys only (fixed byte patterns)."""
import pytest

from core.core_v1 import envelope
from core.core_v1.envelope import EnvelopeError
from core.core_v1.keys import (KeyProviderError, StaticKeyProvider, EnvKeyProvider, encode_key,
                               parse_keyring, provider_from_env)

K1, K2 = b"\x01" * 32, b"\x02" * 32
P1 = StaticKeyProvider({"k1": K1}, "k1")
P12 = StaticKeyProvider({"k1": K1, "k2": K2}, "k2")
AAD = envelope.secret_aad("t1", "sec_1")


def test_seal_open_roundtrip_and_header():
    blob = envelope.seal(P1, b"whsec_abc", AAD)
    assert blob.startswith(envelope.MAGIC) and envelope.is_envelope(blob)
    assert envelope.key_id_of(blob) == "k1" and b"whsec_abc" not in blob
    assert envelope.open_(P1, blob, AAD) == b"whsec_abc"
    env = envelope.parse(blob)
    assert env.key_id == "k1"


def test_nonces_are_random():
    assert envelope.seal(P1, b"x", AAD) != envelope.seal(P1, b"x", AAD)


def test_aad_binds_tenant_and_secret_id():
    blob = envelope.seal(P1, b"whsec_abc", AAD)
    for other in (envelope.secret_aad("t2", "sec_1"), envelope.secret_aad("t1", "sec_2")):
        with pytest.raises(EnvelopeError):
            envelope.open_(P1, blob, other)


@pytest.mark.parametrize("pos", [5, 10, 30, -1])
def test_tamper_detected(pos):
    blob = bytearray(envelope.seal(P1, b"whsec_abc", AAD))
    blob[pos] ^= 0x01
    with pytest.raises(EnvelopeError):
        envelope.open_(P1, bytes(blob), AAD)


def test_truncated_and_garbage_rejected():
    blob = envelope.seal(P1, b"whsec_abc", AAD)
    for bad in (blob[:10], blob[:-17], b"CSE\x02" + blob[4:], b"whsec_plain"):
        with pytest.raises(EnvelopeError):
            envelope.open_(P1, bad, AAD)
    assert not envelope.is_envelope(b"whsec_plain") and not envelope.is_envelope(None)


def test_unknown_key_id():
    blob = envelope.seal(P12, b"s", AAD)  # sealed under k2
    with pytest.raises(EnvelopeError):
        envelope.open_(P1, blob, AAD)


def test_rewrap_changes_kid_keeps_plaintext_and_is_noop_when_current():
    old = envelope.seal(P1, b"whsec_abc", AAD)
    new = envelope.rewrap(P12, old, AAD)
    assert envelope.key_id_of(new) == "k2" and envelope.open_(P12, new, AAD) == b"whsec_abc"
    assert envelope.rewrap(P12, new, AAD) == new
    # explicit target
    back = envelope.rewrap(P12, new, AAD, to_key_id="k1")
    assert envelope.key_id_of(back) == "k1" and envelope.open_(P1, back, AAD) == b"whsec_abc"


def test_rewrap_verifies_payload():
    blob = bytearray(envelope.seal(P1, b"whsec_abc", AAD))
    blob[-1] ^= 1
    with pytest.raises(EnvelopeError):
        envelope.rewrap(P12, bytes(blob), AAD)


def test_plaintext_size_limit():
    with pytest.raises(EnvelopeError):
        envelope.seal(P1, b"x" * (envelope.MAX_PLAINTEXT + 1), AAD)


def test_static_provider_validation_and_repr():
    with pytest.raises(KeyProviderError):
        StaticKeyProvider({"k1": b"short"}, "k1")
    with pytest.raises(KeyProviderError):
        StaticKeyProvider({"bad id!": K1}, "bad id!")
    with pytest.raises(KeyProviderError):
        StaticKeyProvider({"k1": K1}, "k9")
    assert "\\x01" not in repr(P12) and encode_key(K1) not in repr(P12)
    assert P12.with_active("k1").active_key_id() == "k1"
    assert set(P12.key_ids()) == {"k1", "k2"}


def test_parse_keyring():
    ring = parse_keyring(f"k1:{encode_key(K1)}, k2:{encode_key(K2)}")
    assert ring == {"k1": K1, "k2": K2}
    for bad in ("k1", f"k1:{encode_key(b'x' * 8)}", f"k1:{encode_key(K1)},k1:{encode_key(K2)}"):
        with pytest.raises(KeyProviderError):
            parse_keyring(bad)


def test_env_provider_rules():
    one = {"SKELETON_BACKEND_CORE_KEKS": f"k1:{encode_key(K1)}"}
    assert EnvKeyProvider(one).active_key_id() == "k1"
    two = {"SKELETON_BACKEND_CORE_KEKS": f"k1:{encode_key(K1)},k2:{encode_key(K2)}"}
    with pytest.raises(KeyProviderError):
        EnvKeyProvider(two)
    assert EnvKeyProvider({**two, "SKELETON_BACKEND_CORE_ACTIVE_KEK": "k2"}).active_key_id() == "k2"


def test_provider_from_env_fail_closed():
    assert provider_from_env({}) is None
    with pytest.raises(KeyProviderError):
        provider_from_env({"SKELETON_BACKEND_CORE_REQUIRE_KEK": "1"})
    p = provider_from_env({"SKELETON_BACKEND_CORE_KEKS": f"k1:{encode_key(K1)}",
                           "SKELETON_BACKEND_CORE_REQUIRE_KEK": "1"})
    assert p.active_key_id() == "k1"
