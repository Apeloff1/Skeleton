from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.local_development import LocalEnvironmentQualifier
from skeleton.ai.runtime.deferred.operations_experience import LocalEnvironment


D = "1" * 64
S = "2" * 64


def env(**changes: object) -> LocalEnvironment:
    values = dict(environment_id="dev", python_version="3.12", dependency_digest=D, secret_mode="isolated")
    values.update(changes)
    return LocalEnvironment(**values)


def test_local_qualification_is_deterministic_and_hermetic() -> None:
    q = LocalEnvironmentQualifier(env(), service_digests={"db": S})
    a = q.qualify(env(), observed_services={"db": S})
    b = q.qualify(env(), observed_services={"db": S})
    assert a.digest == b.digest
    assert a.service_digests == (("db", S),)


def test_environment_drift_fails_closed() -> None:
    q = LocalEnvironmentQualifier(env(), service_digests={"db": S})
    with pytest.raises(ValueError):
        q.qualify(env(python_version="3.13"), observed_services={"db": S})
    with pytest.raises(ValueError):
        q.qualify(env(), observed_services={"db": "3" * 64})


def test_real_secret_presence_is_rejected() -> None:
    q = LocalEnvironmentQualifier(env(), service_digests={"db": S})
    with pytest.raises(PermissionError):
        q.qualify(env(), observed_services={"db": S}, real_secret_present=True)


def test_service_contract_requires_canonical_digest() -> None:
    with pytest.raises(ValueError):
        LocalEnvironmentQualifier(env(), service_digests={"db": "not-a-digest"})
