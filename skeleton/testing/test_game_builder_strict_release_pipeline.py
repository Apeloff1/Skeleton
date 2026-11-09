"""Full structural game release gate: real bytes, binary layout, pinned reviewers.

Synthetic format fixtures check structural consistency only. They are not
runnable operating-system applications or legal publication certificates.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json

import pytest

from skeleton.ai.game_builder.native_binary_structure import ExecutableFormatError
from skeleton.ai.game_builder.native_release_intake import NativeIntakeError
from skeleton.ai.game_builder.release_assurance import ReleaseReadiness
from skeleton.ai.game_builder.release_pipeline import run_structurally_verified_native_release_gate
from skeleton.testing.test_game_builder_native_binary_structure import pe_image
from skeleton.testing.test_game_builder_native_release_intake import (
    _setup, _review_panel,
)
from skeleton.testing.test_game_builder_release_trust_anchor import signed_root


def _inputs(tmp_path):
    args=_setup(tmp_path)
    code=pe_image()
    args["compiled_binary"].write_bytes(code)
    candidate=replace(args["candidate"],native_binary_sha256=sha256(code).hexdigest())
    build=args["build_evidence"]
    data=json.loads(build.read_text())
    data["binary_sha256"]=sha256(code).hexdigest()
    build.write_text(json.dumps(data))
    candidate=replace(
        candidate,native_build_evidence_sha256=sha256(build.read_bytes()).hexdigest(),
    )
    args["candidate"]=candidate
    reviewers, signatures=_review_panel(candidate)
    root,pin=signed_root(candidate,reviewers)
    args.update({
        "registry":root,"attestations":signatures,
        "expected_root_key_sha256":pin,"minimum_policy_epoch":root.policy_epoch,
        "evaluation_utc":"2026-10-11T12:00:00Z",
    })
    return args


def test_strict_game_release_gate_requires_pe_sections_entry_and_independent_root(tmp_path):
    args=_inputs(tmp_path)
    receipt=run_structurally_verified_native_release_gate(**args)
    assert receipt.independent_reviews_complete
    assert receipt.byte_and_signed_review.pinned_review.review.status is (
        ReleaseReadiness.REVIEW_RECEIPTS_SATISFIED_PUBLICATION_PENDING
    )
    assert receipt.executable_structure.format_name=="PE/COFF"
    assert receipt.executable_structure.architecture=="x86_64"
    assert receipt.executable_structure.image_sha256==args["candidate"].native_binary_sha256
    assert receipt.executable_structure.format_structure_checked
    assert receipt.binary_executed_successfully is False
    assert receipt.legal_noninfringement_certified is False
    assert receipt.release_authorized is False
    report=receipt.public_receipt()
    assert report["file_bytes_verified"] is True
    assert report["binary_format_structurally_checked"] is True
    assert report["publisher_approval_granted"] is False
    assert receipt==run_structurally_verified_native_release_gate(**args)


def test_strict_release_gate_rejects_previous_magic_only_pe_fixture(tmp_path):
    args=_setup(tmp_path)
    reviewers,signatures=_review_panel(args["candidate"])
    root,pin=signed_root(args["candidate"],reviewers)
    args.update({
        "registry":root,"attestations":signatures,
        "expected_root_key_sha256":pin,"minimum_policy_epoch":root.policy_epoch,
        "evaluation_utc":"2026-10-11T12:00:00Z",
    })
    with pytest.raises(ExecutableFormatError):
        run_structurally_verified_native_release_gate(**args)


def test_valid_pe_with_unreviewed_binary_byte_change_fails_before_signatures(tmp_path):
    args=_inputs(tmp_path)
    bin_path=args["compiled_binary"]
    data=bytearray(bin_path.read_bytes())
    data[0x200]^=0xFF
    bin_path.write_bytes(data)
    with pytest.raises(ExecutableFormatError,match="differ"):
        run_structurally_verified_native_release_gate(**args)


@pytest.mark.parametrize("field",[
    "registry","expected_root_key_sha256","minimum_policy_epoch",
])
def test_valid_native_pe_never_bypasses_external_reviewer_policy(tmp_path,field):
    from skeleton.ai.game_builder.release_assurance import ReleaseReviewError
    args=_inputs(tmp_path)
    if field=="registry":
        new_root,_=signed_root(args["candidate"],args["registry"].reviewers)
        args[field]=new_root
    elif field=="expected_root_key_sha256":
        args[field]="0"*64
    else:
        args[field]=999999
    with pytest.raises(ReleaseReviewError):
        run_structurally_verified_native_release_gate(**args)


@pytest.mark.parametrize("field",[
    "release_authorized","binary_executed_successfully","game_mechanics_playtested",
    "legal_noninfringement_certified",
])
def test_structural_release_receipt_cannot_forge_gameplay_or_legal_clearance(
    tmp_path,field,
):
    report=run_structurally_verified_native_release_gate(**_inputs(tmp_path))
    with pytest.raises(ValueError):
        replace(report,**{field:True})


def test_structural_release_receipt_bound_to_exact_review_not_other_game(tmp_path):
    args=_inputs(tmp_path)
    report=run_structurally_verified_native_release_gate(**args)
    with pytest.raises(ValueError):
        replace(report,candidate_sha256="f"*64)
    with pytest.raises(ValueError):
        replace(report,report_sha256="f"*64)
