"""Structural admission tests for the first-install ops router audit."""
from pathlib import Path

from scripts.check_app_assembly import has_canonical_ops_router


ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "backend/routes/ops.py"


def test_real_multiline_ops_router_and_admin_guard_qualify():
    source = OPS.read_text(encoding="utf-8")
    assert has_canonical_ops_router(source)


def test_wrong_router_function_is_rejected():
    source = OPS.read_text(encoding="utf-8")
    assert "router = project_router(" in source
    assert not has_canonical_ops_router(
        source.replace("router = project_router(", "router = APIRouter(", 1)
    )


def test_drifting_ops_prefix_is_rejected():
    source = OPS.read_text(encoding="utf-8")
    assert 'prefix="/api/admin/ops"' in source
    assert not has_canonical_ops_router(
        source.replace('prefix="/api/admin/ops"', 'prefix="/api/admin"', 1)
    )


def test_downgraded_admin_role_is_rejected():
    source = OPS.read_text(encoding="utf-8")
    assert 'Depends(auth.require_role("admin"))' in source
    assert not has_canonical_ops_router(
        source.replace(
            'Depends(auth.require_role("admin"))',
            'Depends(auth.require_role("viewer"))', 1,
        )
    )


def test_missing_canonical_import_is_rejected():
    source = OPS.read_text(encoding="utf-8")
    assert "from routes.playable_access import project_router, scoped_database" in source
    assert not has_canonical_ops_router(
        source.replace(
            "from routes.playable_access import project_router, scoped_database",
            "from routes.playable_access import scoped_database", 1,
        )
    )


def test_malformed_and_comment_spoofed_router_are_rejected():
    assert not has_canonical_ops_router('router = project_router(\n')
    assert not has_canonical_ops_router(
        '# router = project_router(prefix="/api/admin/ops")\n'
        'router = APIRouter(prefix="/api/admin/ops")\n'
    )
