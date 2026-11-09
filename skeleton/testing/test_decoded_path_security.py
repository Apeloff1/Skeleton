from __future__ import annotations

import pytest

from skeleton.sandbox.errors import PathEscapeError
from skeleton.sandbox.fs import check_relative
from skeleton.security.decoded_path import (
    DecodedPathError,
    reject_decoded_path_ambiguity,
)
from skeleton.shells.workspace_txn.pathing import (
    WorkspacePathError,
    normalize_relative_path,
)


@pytest.mark.parametrize(
    "value",
    (
        "%2e%2e/etc/passwd",
        "%2E%2E%2Fetc/passwd",
        "safe/%2e%2e/secret",
        "safe%2f..%2fsecret",
        "safe%5c..%5csecret",
        "%252e%252e%252fetc/passwd",
        "safe/%2500name",
        "%2fetc/passwd",
        "%5c%5cserver%5cshare",
        "C%3a%5cWindows%5cSystem32",
    ),
)
def test_decoded_path_guard_rejects_structural_ambiguity(value: str) -> None:
    with pytest.raises(DecodedPathError):
        reject_decoded_path_ambiguity(value)


@pytest.mark.parametrize(
    "value",
    (
        "report%20final.txt",
        "100%25-complete.txt",
        "literal%2Ename.txt",
    ),
)
def test_decoded_path_guard_preserves_benign_percent_literals(value: str) -> None:
    assert reject_decoded_path_ambiguity(value) == value


@pytest.mark.parametrize(
    "value",
    (
        "%2e%2e/etc/passwd",
        "safe%2f..%2fsecret",
        "%252e%252e%252fetc/passwd",
        "%2fetc/passwd",
    ),
)
def test_sandbox_path_boundary_rejects_encoded_traversal(value: str) -> None:
    with pytest.raises(PathEscapeError):
        check_relative(value)


@pytest.mark.parametrize(
    "value",
    (
        "%2e%2e/etc/passwd",
        "safe%5c..%5csecret",
        "%252e%252e%252fetc/passwd",
        "C%3a%5cWindows%5cSystem32",
    ),
)
def test_workspace_path_boundary_rejects_encoded_traversal(value: str) -> None:
    with pytest.raises(WorkspacePathError):
        normalize_relative_path(value)


def test_benign_encoded_filename_remains_literal_in_both_path_stacks() -> None:
    value = "reports/report%20final.txt"
    assert str(check_relative(value)) == value
    assert normalize_relative_path(value) == value
