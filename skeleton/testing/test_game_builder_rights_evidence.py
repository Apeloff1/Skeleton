"""Original homebrew rights-document custody, without third-party assets."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import os
from unittest.mock import patch

import pytest

from skeleton.ai.game_builder.rights_evidence import (
    MAX_RIGHTS_EVIDENCE_BYTES, RightsEvidenceError,
    RightsEvidenceReceipt, read_rights_evidence,
)


def test_local_authorship_file_is_hashed_without_claiming_legal_clearance(tmp_path):
    path = tmp_path / "own-artwork-receipt.txt"
    data = b"Original code and artwork by my studio; dated source notes."
    path.write_bytes(data)
    receipt = read_rights_evidence(path)
    assert receipt.document_sha256 == sha256(data).hexdigest()
    assert receipt.content_bytes == len(data)
    assert receipt.bytes_read_from_local_regular_file
    assert not receipt.independent_ownership_verified
    assert not receipt.legal_clearance_issued
    assert read_rights_evidence(path) == receipt


@pytest.mark.parametrize("contents", [b"", b"z" * (MAX_RIGHTS_EVIDENCE_BYTES + 1)])
def test_empty_or_unbounded_rights_evidence_is_not_admitted(tmp_path, contents):
    path = tmp_path / "owner.txt"
    path.write_bytes(contents)
    with pytest.raises(RightsEvidenceError, match="bounded"):
        read_rights_evidence(path)


def test_authorship_custody_rejects_symlink_even_to_legal_document(tmp_path):
    target = tmp_path / "original.txt"
    target.write_text("Original self-authored game", encoding="utf-8")
    shortcut = tmp_path / "alias.txt"
    try:
        shortcut.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(RightsEvidenceError, match="bounded"):
        read_rights_evidence(shortcut)


def test_authorship_custody_rejects_path_swap_before_descriptor_open(tmp_path):
    source = tmp_path / "review.txt"
    replacement = tmp_path / "replacement.txt"
    source.write_bytes(b"Current authorship evidence.")
    replacement.write_bytes(b"Other data, replacing the original.")
    original_open = os.open
    changed = []

    def replace_then_open(path, flags, *args, **kwargs):
        if os.fspath(path) == os.fspath(source) and not changed:
            changed.append(True)
            os.replace(replacement, source)
        return original_open(path, flags, *args, **kwargs)

    with patch("skeleton.ai.game_builder.rights_evidence.os.open",
               side_effect=replace_then_open):
        with pytest.raises(RightsEvidenceError, match="changed during admission"):
            read_rights_evidence(source)
    assert changed


@pytest.mark.parametrize("changes", [
    {"independent_ownership_verified": True},
    {"legal_clearance_issued": True},
    {"content_bytes": 0},
    {"document_sha256": "invalid"},
    {"bytes_read_from_local_regular_file": False},
])
def test_authorship_receipt_cannot_forge_rights_verification(changes):
    receipt = RightsEvidenceReceipt("f" * 64, 18)
    with pytest.raises(RightsEvidenceError):
        replace(receipt, **changes)
