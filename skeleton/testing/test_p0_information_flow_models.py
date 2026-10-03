from __future__ import annotations

from skeleton.shells.ai.context_provenance import (
    ContextItem,
    ContextKind,
    ContextSensitivity,
    ContextTrust,
)


def test_confidentiality_and_integrity_are_orthogonal_context_axes() -> None:
    high_integrity_secret = ContextItem(
        "policy-secret",
        ContextKind.POLICY,
        ContextTrust.SYSTEM,
        ContextSensitivity.SECRET,
        "hidden policy",
        "host",
    )
    low_integrity_public = ContextItem(
        "retrieved-public",
        ContextKind.REPOSITORY,
        ContextTrust.UNTRUSTED,
        ContextSensitivity.PUBLIC,
        "retrieved data",
        "retriever",
    )

    assert high_integrity_secret.trust is ContextTrust.SYSTEM
    assert high_integrity_secret.sensitivity is ContextSensitivity.SECRET
    assert low_integrity_public.trust is ContextTrust.UNTRUSTED
    assert low_integrity_public.sensitivity is ContextSensitivity.PUBLIC
    assert high_integrity_secret.trust is not low_integrity_public.trust
    assert high_integrity_secret.sensitivity is not low_integrity_public.sensitivity


def test_untrusted_public_data_does_not_become_confidential_by_label() -> None:
    item = ContextItem(
        "public-untrusted",
        ContextKind.REPOSITORY,
        ContextTrust.UNTRUSTED,
        ContextSensitivity.PUBLIC,
        "public observation",
        "retriever",
    )
    assert item.trust is ContextTrust.UNTRUSTED
    assert item.sensitivity is ContextSensitivity.PUBLIC
