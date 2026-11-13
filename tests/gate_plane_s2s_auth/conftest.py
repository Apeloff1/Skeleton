"""Shared fixtures for the s2s auth contract tests (TEST-ONLY key material)."""

from __future__ import annotations

import pytest

from skeleton.gate_plane.s2s.clock import ManualClock
from skeleton.gate_plane.s2s.mint_cli import build_test_keyring
from skeleton.gate_plane.s2s.nonce import LocalNonceStoreDouble
from skeleton.gate_plane.s2s.registry import ServiceIdentity, ServiceRegistry
from skeleton.gate_plane.s2s.tokens import TokenSigner

FP_A = "aa" * 32
FP_B = "bb" * 32


@pytest.fixture
def clock():
    return ManualClock()


@pytest.fixture
def ring(clock):
    return build_test_keyring(["test-k1"], clock=clock)


@pytest.fixture
def registry():
    return ServiceRegistry([
        ServiceIdentity.build("forge-worker", scopes=["forge:read", "forge:write"], audiences=["gate"]),
        ServiceIdentity.build("swarm-agent", scopes=["swarm:read"], audiences=["gate"]),
        ServiceIdentity.build("bound-svc", scopes=["forge:read"], audiences=["gate"], cert_fingerprints=[FP_A]),
    ])


@pytest.fixture
def nonces(clock):
    return LocalNonceStoreDouble(clock=clock.now)


@pytest.fixture
def signer_for(ring, clock):
    def _make(service):
        return TokenSigner(service, ring, clock=clock)
    return _make
