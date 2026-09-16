from skeleton.automation.repair_policy import classify_change, failure_fingerprint


def test_failure_fingerprint_is_stable_and_order_independent():
    left = failure_fingerprint("CodeQL", "failure", "abc123", ["B", "A"])
    right = failure_fingerprint("codeql", "FAILURE", "abc123", ["A", "B"])
    assert left == right


def test_workflow_and_action_changes_require_human_review():
    for path in (".github/workflows/repair.yml", ".github/actions/repair/action.yml"):
        decision = classify_change([path])
        assert decision.risk == "high"
        assert decision.human_review_required
        assert not decision.automated_merge_allowed


def test_security_findings_cannot_be_auto_merged():
    decision = classify_change(["backend/example.py"], security_finding=True)
    assert decision.risk == "high"
    assert decision.human_review_required
    assert not decision.automated_merge_allowed


def test_security_control_paths_cannot_be_auto_merged():
    for path in ("docs/security-policy.md", "docs/attestation.md", "docs/merge-gate.md"):
        decision = classify_change([path])
        assert decision.risk == "high"
        assert decision.human_review_required
        assert not decision.automated_merge_allowed


def test_dependency_manifests_require_human_review():
    for path in ("pyproject.toml", "package-lock.json", "requirements-prod.txt"):
        decision = classify_change([path])
        assert decision.risk == "high"
        assert decision.human_review_required
        assert not decision.automated_merge_allowed


def test_small_documentation_change_can_be_low_risk():
    decision = classify_change(["docs/REPAIR.md"])
    assert decision.risk == "low"
    assert decision.automated_merge_allowed
    assert not decision.human_review_required


def test_code_change_is_not_automatically_mergeable():
    decision = classify_change(["backend/example.py"])
    assert decision.risk == "medium"
    assert decision.human_review_required
    assert not decision.automated_merge_allowed
