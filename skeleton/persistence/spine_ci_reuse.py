"""Fail-closed reuse decision for already verified exact-head CI evidence."""

from __future__ import annotations

import re
from typing import Any, Mapping


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")


class SpineCiReuseError(RuntimeError):
    """CI evidence reuse input is malformed or overclaims authority."""


def can_reuse_verified_qualification(
    prior: Mapping[str, Any],
    current: Mapping[str, Any],
) -> bool:
    """Return True only for the same independently verified evidence identity.

    This function is deliberately non-authoritative.  It does not validate a
    qualification, grant merge authority, or allow a required check to be
    skipped.  Callers must independently verify both inputs first.
    """

    for label, card in (("prior", prior), ("current", current)):
        if not isinstance(card, Mapping):
            raise SpineCiReuseError(f"{label} qualification is not an object")
        if card.get("kind") != "spine_ci_qualification_verify":
            raise SpineCiReuseError(f"{label} qualification is not verified")
        if card.get("verified") is not True or card.get("ci_green") is not True:
            raise SpineCiReuseError(f"{label} qualification is not green")
        if card.get("merge_authority") is not False:
            raise SpineCiReuseError(f"{label} qualification overclaims merge authority")
        repository = card.get("repository")
        head_sha = card.get("head_sha")
        policy_digest = card.get("required_check_policy_digest")
        identity = card.get("qualification_identity")
        if not isinstance(repository, str) or _REPOSITORY_RE.fullmatch(repository) is None:
            raise SpineCiReuseError(f"{label} repository is invalid")
        if not isinstance(head_sha, str) or _SHA_RE.fullmatch(head_sha) is None:
            raise SpineCiReuseError(f"{label} head SHA is invalid")
        if not isinstance(policy_digest, str) or _DIGEST_RE.fullmatch(policy_digest) is None:
            raise SpineCiReuseError(f"{label} policy digest is invalid")
        if not isinstance(identity, str) or _DIGEST_RE.fullmatch(identity) is None:
            raise SpineCiReuseError(f"{label} qualification identity is invalid")

    return (
        prior["repository"] == current["repository"]
        and prior["head_sha"] == current["head_sha"]
        and prior["required_check_policy_digest"] == current["required_check_policy_digest"]
        and prior["qualification_identity"] == current["qualification_identity"]
    )


__all__ = ["SpineCiReuseError", "can_reuse_verified_qualification"]
