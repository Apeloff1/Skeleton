"""Protect exact-head npm archive qualification against workflow drift.

This test lives in the repository root, not the frontend Docker context:
the frontend container must not require .github as an input.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_node_forge_archive_is_attested_at_exact_pr_head():
    workflow = (ROOT / ".github/workflows/merge-readiness.yml").read_text("utf-8")
    assert "name: Verify exact-head frozen node-forge npm archive" in workflow
    assert 'CANDIDATE_SHA: ${{ github.event.pull_request.head.sha || github.sha }}' in workflow
    assert 'test "$(git rev-parse HEAD)" = "$CANDIDATE_SHA"' in workflow
    assert "yarn --cwd frontend install --frozen-lockfile --ignore-scripts --non-interactive" in workflow
    assert "node --test frontend/scripts/test-node-forge-rsa-custody.cjs" in workflow
    assert "node frontend/scripts/verify-node-forge-frozen-archive.cjs" in workflow


def test_frozen_archive_verifier_does_not_rewrite_any_package():
    script = (ROOT / "frontend/scripts/verify-node-forge-frozen-archive.cjs").read_text("utf-8")
    assert "REVIEWED_UPSTREAM_SHA256" in script
    assert "crypto.createHash('sha256').update(raw)" in script
    assert "raw.equals(installed)" in script
    assert "npm" in script and "pack" in script and "--ignore-scripts" in script
    assert "fs.writeFileSync" not in script
