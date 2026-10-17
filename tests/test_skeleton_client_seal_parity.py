"""Parity: the SDK's stdlib seal minting must match the server's ``mint_seal`` byte for byte.

The client may not import ``skeleton.api`` (architecture boundary), so
``skeleton.client.seal`` mirrors the server helper. Tests may import both, which
is how we keep the wire form from drifting.
"""

from __future__ import annotations

import pytest

from skeleton.api.hmac_seal import mint_seal as server_mint
from skeleton.api.hmac_seal import verify_seal
from skeleton.client import seal as client_seal

_CASES = [
    # (env secret, env keyring, explicit secret, principal)
    ("primary-secret", None, None, None),
    ("primary-secret", None, None, "user42"),
    (None, None, "explicit", None),
    (None, None, "explicit", "user42"),
    ("primary-secret", "k1=ring-one,k2=ring-two", None, None),
    ("primary-secret", "k1=ring-one,k2=ring-two", None, "user42"),
    (None, "k1=ring-one,k2=ring-two", None, None),
    (None, "k1=ring-one,k2=ring-two", None, "user42"),
    (None, "default=ring-default,k2=ring-two", None, "user42"),
    (None, None, None, None),
    (None, None, None, "user42"),
    (None, None, "", None),
]


@pytest.mark.parametrize("env_secret,env_ring,secret,principal", _CASES)
@pytest.mark.parametrize("ttl", [31, 300])
def test_client_mint_matches_server_mint(monkeypatch, env_secret, env_ring, secret, principal, ttl):
    for name, value in (("GF_SEAL_SECRET", env_secret), ("GF_SEAL_KEYRING", env_ring)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    kwargs = {"secret": secret, "principal": principal, "now": 1_700_000_000.75}
    expected = server_mint("sdk", ttl, **kwargs)
    assert client_seal.mint_seal("sdk", ttl, **kwargs) == expected
    if expected is not None:
        assert verify_seal(expected, secret=secret, keyring=env_ring, now=1_700_000_000) == "sdk"


def test_client_mint_rejects_bool_ttl_like_server():
    with pytest.raises(ValueError):
        server_mint("sdk", True, secret="s")
    with pytest.raises(ValueError):
        client_seal.mint_seal("sdk", True, secret="s")


def test_client_seal_module_does_not_import_server_api():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(client_seal))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(a.name.startswith("skeleton.api") for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("skeleton.api")
            assert not (node.level and (node.module or "").startswith("api"))
