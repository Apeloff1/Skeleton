"""Security regressions for no-query credentials and safe public enum errors."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


ROUTES = Path(__file__).resolve().parents[1] / "routes"


def _source(name: str) -> str:
    return (ROUTES / name).read_text(encoding="utf-8")


def _credential_contract(source: str) -> bool:
    """Inspect the actual route function without executing dynamically compiled code.

    Keep the admission boundary intentionally narrow: a single legacy-token
    rejection followed by the unchanged header value, with bounded FastAPI
    parameters. Any additional statement or user-controlled error detail fails.
    """
    tree = ast.parse(source)
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_ops_credential"
    ]
    if len(functions) != 1:
        return False
    function = functions[0]
    args = function.args
    if (
        function.decorator_list or args.posonlyargs or args.kwonlyargs
        or args.vararg or args.kwarg or args.kw_defaults
        or [arg.arg for arg in args.args] != ["x_ops_token", "legacy_token"]
        or len(args.defaults) != 2
    ):
        return False

    def _parameter(call: ast.expr, name: str, alias: str, deprecated: bool) -> bool:
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            return False
        if call.func.id != name or call.args or any(k.arg is None for k in call.keywords):
            return False
        values = {k.arg: k.value for k in call.keywords}
        expected = {"default": "", "alias": alias, "max_length": 512}
        if deprecated:
            expected["deprecated"] = True
        return (
            len(values) == len(expected)
            and all(
                key in values
                and isinstance(values[key], ast.Constant)
                and type(values[key].value) is type(value)
                and values[key].value == value
                for key, value in expected.items()
            )
        )

    if not _parameter(args.defaults[0], "Header", "X-Ops-Token", False):
        return False
    if not _parameter(args.defaults[1], "Query", "token", True):
        return False
    statements = function.body
    if (
        statements and isinstance(statements[0], ast.Expr)
        and isinstance(statements[0].value, ast.Constant)
        and isinstance(statements[0].value.value, str)
    ):
        statements = statements[1:]
    if len(statements) != 2:
        return False
    rejection, accepted = statements
    if not (
        isinstance(rejection, ast.If)
        and isinstance(rejection.test, ast.Name)
        and rejection.test.id == "legacy_token"
        and not rejection.orelse
        and len(rejection.body) == 1
        and isinstance(rejection.body[0], ast.Raise)
        and isinstance(accepted, ast.Return)
        and isinstance(accepted.value, ast.Name)
        and accepted.value.id == "x_ops_token"
    ):
        return False
    error = rejection.body[0].exc
    if not isinstance(error, ast.Call) or not isinstance(error.func, ast.Name):
        return False
    if error.func.id != "HTTPException" or error.args or len(error.keywords) != 2:
        return False
    values = {kw.arg: kw.value for kw in error.keywords}
    return (
        set(values) == {"status_code", "detail"}
        and isinstance(values["status_code"], ast.Constant)
        and type(values["status_code"].value) is int
        and values["status_code"].value == 400
        and isinstance(values["detail"], ast.Constant)
        and type(values["detail"].value) is str
        and values["detail"].value
        == "operator credentials must use the X-Ops-Token header"
    )


def test_legacy_query_token_is_rejected_even_if_matching_header():
    assert _credential_contract(_source("ops.py"))


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        ("if legacy_token:", "if False:"),
        ("return x_ops_token", "return legacy_token"),
        ("status_code=400", "status_code=200"),
        (
            'detail="operator credentials must use the X-Ops-Token header"',
            'detail=f"bad credential: {legacy_token}"',
        ),
        ('alias="X-Ops-Token"', 'alias="X-Legacy-Token"'),
        ('alias="token"', 'alias="other_token"'),
        ('max_length=512, deprecated=True', 'max_length=2048, deprecated=True'),
    ],
)
def test_credential_contract_rejects_unsafe_route_mutations(original, replacement):
    source = _source("ops.py")
    assert original in source
    assert not _credential_contract(source.replace(original, replacement, 1))


def test_operator_header_only_credential_is_retained():
    assert _credential_contract(_source("ops.py"))


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
