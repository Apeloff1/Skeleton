from __future__ import annotations

from pathlib import Path

from scripts.check_legacy_duplicate_inventory import (
    CLASSIFICATION_SET,
    SCAN_ROOTS,
    ContractFamily,
    ContractMember,
    collect_violations,
    extract_fingerprint,
    file_matches_family,
    inventory_table,
)


REPO_ROOT = Path(__file__).resolve().parents[1]

CANONICAL_GATE = '''\
"""canonical dependency boundaries"""

FORBIDDEN = {"backend"}

def _matches_module(module, forbidden):
    return module == forbidden

RULES = (
    {
        "root": "skeleton",
        "excluded_prefixes": ("skeleton/testing/",),
        "forbidden_modules": ("backend",),
    },
)
'''

DUPLICATE_GATE = '''\
"""second implementation of the same gate contract"""

def _matches_module(module, forbidden):
    return module.startswith(forbidden)

TABLE = (
    {
        "excluded_prefixes": (),
        "forbidden_modules": ("frontend",),
    },
)
'''

UNRELATED_SAME_BASENAME = '''\
"""shares a filename with a gate scanner but not the contract."""

def parse_report(path):
    return path

NAME = "check_architecture_boundaries.py"
'''

ERROR_ENVELOPE = '''\
from fastapi.responses import JSONResponse

class ApiErrorResponse:
    def to_dict(self):
        return {"error": {"type": "X", "code": "C", "message": "m", "context": {}}}

def map_error(exc):
    return ApiErrorResponse()

def install_error_handlers(app):
    app.add_exception_handler(Exception, lambda *_: None)
'''


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _scan_roots(tmp_path: Path) -> Path:
    for relative in SCAN_ROOTS:
        (tmp_path / relative).mkdir(parents=True, exist_ok=True)
    return tmp_path


def _family(
    *,
    family_id: str = "architecture.boundary.gate",
    function_names: tuple[str, ...] = ("_matches_module",),
    ast_markers: tuple[str, ...] = ("forbidden_modules", "excluded_prefixes"),
    aliases: tuple[str, ...] = ("architecture_boundaries",),
    members: tuple[ContractMember, ...],
) -> ContractFamily:
    return ContractFamily(
        family_id=family_id,
        function_names=function_names,
        ast_markers=ast_markers,
        aliases=aliases,
        members=members,
    )


def test_repository_legacy_duplicate_inventory_is_closed() -> None:
    assert collect_violations(REPO_ROOT, require_roots=True) == []


def test_inventory_table_uses_exclusive_closed_classes() -> None:
    rows = inventory_table(REPO_ROOT)
    assert rows
    classifications = {row["classification"] for row in rows}
    assert classifications <= CLASSIFICATION_SET
    assert "unknown" not in classifications
    families: dict[str, list[str]] = {}
    for row in rows:
        families.setdefault(str(row["family_id"]), []).append(str(row["classification"]))
        assert row["path"]
        assert row["function_names"] or row["ast_markers"]
        assert row["exists"] is True
        assert any(str(row["path"]).startswith(prefix + "/") for prefix in SCAN_ROOTS)
    for family_id, classes in families.items():
        assert classes.count("canonical") == 1, family_id


def test_exclusive_classes_are_accepted_when_declared(tmp_path: Path) -> None:
    root = _scan_roots(tmp_path)
    _write(root, "scripts/canonical_gate.py", CANONICAL_GATE)
    _write(root, "backend/scripts/twin_gate.py", DUPLICATE_GATE)
    _write(
        root,
        "skeleton/api/narrow_gate.py",
        '''\
def _matches_module(module, forbidden):
    return False

PARTIAL = {"excluded_prefixes": (), "forbidden_modules": ("tests",)}
''',
    )
    inventory = (
        _family(
            members=(
                ContractMember("scripts/canonical_gate.py", "canonical"),
                ContractMember("backend/scripts/twin_gate.py", "duplicate"),
                ContractMember("skeleton/api/narrow_gate.py", "overlapping"),
            )
        ),
    )

    assert collect_violations(root, inventory=inventory) == []


def test_two_canonicals_in_one_family_fail_closed(tmp_path: Path) -> None:
    root = _scan_roots(tmp_path)
    _write(root, "scripts/canonical_gate.py", CANONICAL_GATE)
    _write(root, "backend/scripts/twin_gate.py", DUPLICATE_GATE)
    inventory = (
        _family(
            members=(
                ContractMember("scripts/canonical_gate.py", "canonical"),
                ContractMember("backend/scripts/twin_gate.py", "canonical"),
            )
        ),
    )

    errors = collect_violations(root, inventory=inventory)

    assert any("exactly one canonical member required" in item for item in errors)


def test_unknown_classification_fails_closed(tmp_path: Path) -> None:
    root = _scan_roots(tmp_path)
    _write(root, "scripts/canonical_gate.py", CANONICAL_GATE)
    inventory = (
        _family(members=(ContractMember("scripts/canonical_gate.py", "unknown"),)),
    )

    errors = collect_violations(root, inventory=inventory)

    assert any("unknown status fails closed" in item for item in errors)
    assert any("exactly one canonical member required" in item for item in errors)


def test_unlisted_fingerprint_match_is_unknown(tmp_path: Path) -> None:
    root = _scan_roots(tmp_path)
    _write(root, "scripts/canonical_gate.py", CANONICAL_GATE)
    _write(root, "scripts/extra_gate.py", DUPLICATE_GATE)
    inventory = (
        _family(members=(ContractMember("scripts/canonical_gate.py", "canonical"),)),
    )

    errors = collect_violations(root, inventory=inventory)

    assert any("unknown contract implementation: scripts/extra_gate.py" in item for item in errors)
    assert any("architecture.boundary.gate" in item for item in errors)


def test_fingerprint_match_ignores_basename(tmp_path: Path) -> None:
    root = _scan_roots(tmp_path)
    canonical = _write(root, "scripts/owner.py", CANONICAL_GATE)
    twin = _write(root, "backend/scripts/also_owner.py", DUPLICATE_GATE)
    decoy = _write(
        root,
        "scripts/check_architecture_boundaries.py",
        UNRELATED_SAME_BASENAME,
    )
    family = _family(
        members=(
            ContractMember("scripts/owner.py", "canonical"),
            ContractMember("backend/scripts/also_owner.py", "duplicate"),
        )
    )

    canonical_fp = extract_fingerprint(canonical, repo_root=root)
    twin_fp = extract_fingerprint(twin, repo_root=root)
    decoy_fp = extract_fingerprint(decoy, repo_root=root)

    assert canonical.name != twin.name
    assert decoy.name == "check_architecture_boundaries.py"
    assert file_matches_family(canonical_fp, family)
    assert file_matches_family(twin_fp, family)
    assert not file_matches_family(decoy_fp, family)
    assert collect_violations(root, inventory=(family,)) == []


def test_same_basename_without_markers_is_not_a_duplicate(tmp_path: Path) -> None:
    root = _scan_roots(tmp_path)
    _write(root, "scripts/check_architecture_boundaries.py", CANONICAL_GATE)
    _write(
        root,
        "backend/scripts/check_architecture_boundaries.py",
        UNRELATED_SAME_BASENAME,
    )
    inventory = (
        _family(
            members=(
                ContractMember("scripts/check_architecture_boundaries.py", "canonical"),
            )
        ),
    )

    assert collect_violations(root, inventory=inventory) == []


def test_scan_does_not_leave_allowlisted_roots(tmp_path: Path) -> None:
    root = _scan_roots(tmp_path)
    _write(root, "scripts/canonical_gate.py", CANONICAL_GATE)
    _write(root, "skeleton/kernel/hidden_gate.py", CANONICAL_GATE)
    _write(root, "backend/hidden_gate.py", CANONICAL_GATE)
    inventory = (
        _family(members=(ContractMember("scripts/canonical_gate.py", "canonical"),)),
    )

    assert collect_violations(root, inventory=inventory) == []


def test_parse_failure_fails_closed(tmp_path: Path) -> None:
    root = _scan_roots(tmp_path)
    _write(root, "scripts/canonical_gate.py", "def broken(:\n")
    inventory = (
        _family(members=(ContractMember("scripts/canonical_gate.py", "canonical"),)),
    )

    errors = collect_violations(root, inventory=inventory)

    assert any("cannot validate Python module: SyntaxError" in item for item in errors)


def test_missing_listed_path_fails_closed(tmp_path: Path) -> None:
    root = _scan_roots(tmp_path)
    inventory = (
        _family(members=(ContractMember("scripts/canonical_gate.py", "canonical"),)),
    )

    errors = collect_violations(root, inventory=inventory)

    assert any("missing listed path scripts/canonical_gate.py" in item for item in errors)


def test_listed_path_fingerprint_drift_fails_closed(tmp_path: Path) -> None:
    root = _scan_roots(tmp_path)
    _write(root, "scripts/canonical_gate.py", UNRELATED_SAME_BASENAME)
    inventory = (
        _family(members=(ContractMember("scripts/canonical_gate.py", "canonical"),)),
    )

    errors = collect_violations(root, inventory=inventory)

    assert any("does not match declared function/AST fingerprint" in item for item in errors)


def test_missing_scan_root_fails_closed_when_required(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    _write(tmp_path, "scripts/canonical_gate.py", CANONICAL_GATE)
    inventory = (
        _family(members=(ContractMember("scripts/canonical_gate.py", "canonical"),)),
    )

    errors = collect_violations(tmp_path, inventory=inventory, require_roots=True)

    assert any("missing required scan root: backend/scripts" in item for item in errors)


def test_http_error_envelope_matches_behavior_markers_not_filename(tmp_path: Path) -> None:
    root = _scan_roots(tmp_path)
    _write(root, "skeleton/api/lattice.py", ERROR_ENVELOPE)
    _write(
        root,
        "skeleton/api/helpers.py",
        '''\
from fastapi.responses import JSONResponse

def error_response(*, code, message, status=400, context=None):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "context": context or {}}})
''',
    )
    family = _family(
        family_id="http.error.envelope",
        function_names=("error_response", "map_error", "ApiErrorResponse"),
        ast_markers=("JSONResponse",),
        aliases=("error envelope",),
        members=(
            ContractMember("skeleton/api/lattice.py", "canonical"),
            ContractMember("skeleton/api/helpers.py", "overlapping"),
        ),
    )

    lattice = extract_fingerprint(root / "skeleton/api/lattice.py", repo_root=root)
    helper = extract_fingerprint(root / "skeleton/api/helpers.py", repo_root=root)
    assert lattice.path.endswith("lattice.py")
    assert helper.path.endswith("helpers.py")
    assert file_matches_family(lattice, family)
    assert file_matches_family(helper, family)
    assert collect_violations(root, inventory=(family,)) == []


def test_checker_does_not_delete_or_heuristic_close() -> None:
    source = (REPO_ROOT / "scripts" / "check_legacy_duplicate_inventory.py").read_text(
        encoding="utf-8"
    )
    assert "unlink(" not in source
    assert "os.remove" not in source
    assert "Path.unlink" not in source
    assert "heuristic" in source
    assert "never deletes" in source.lower() or "never delete" in source.lower()
