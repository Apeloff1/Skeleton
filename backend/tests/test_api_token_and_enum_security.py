"""Security regressions for no-query credentials and safe public enum errors."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import HTTPException


ROUTES = Path(__file__).resolve().parents[1] / "routes"


def _source(name: str) -> str:
    return (ROUTES / name).read_text(encoding="utf-8")


def _isolated_ops_credential():
    """Execute the actual route dependency without importing the entire server."""
    tree = ast.parse(_source("ops.py"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_ops_credential"
    )
    module = ast.Module(body=[
        ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
        function,
    ], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "Header": lambda **kwargs: "",
        "Query": lambda **kwargs: "",
        "HTTPException": HTTPException,
    }
    exec(compile(module, "<ops-security-unit>", "exec"), namespace)
    return namespace["_ops_credential"]


def test_legacy_query_token_is_rejected_even_if_matching_header():
    credential = _isolated_ops_credential()
    with pytest.raises(HTTPException) as rejected:
        credential("some-header-secret", "some-header-secret")
    assert rejected.value.status_code == 400
    assert "some-header-secret" not in str(rejected.value.detail)


def test_operator_header_only_credential_is_retained():
    credential = _isolated_ops_credential()
    assert credential("header-secret", "") == "header-secret"
    assert credential("", "") == ""


def test_nexus_public_enum_errors_are_stable_and_bounded():
    source = _source("nexus.py")
    assert 'kind: str = Field(min_length=1, max_length=64)' in source
    assert 'detail="unsupported truth watch event kind"' in source
    assert 'detail="unsupported evidence kind"' in source
    assert 'detail=f"unsupported truth watch event kind: {body.kind}"' not in source
    assert 'detail=f"unsupported evidence kind: {row.kind}"' not in source


def test_ops_private_project_auth_guard_is_not_dropped():
    source = _source("ops.py")
    assert 'dependencies=[Depends(auth.require_role("admin"))]' in source
    assert 'route_class=_GuardedPrivateProjectRoute' in source
    assert 'return x_ops_token or legacy_token' not in source
