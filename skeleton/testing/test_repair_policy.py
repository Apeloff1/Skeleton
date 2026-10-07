from skeleton.automation.repair_policy import classify_change, failure_fingerprint


def test_failure_fingerprint_is_stable_order_independent_and_deduplicated() -> None:
    left = failure_fingerprint("CodeQL", "failure", "ABC123", ["B", "A", "A"])
    right = failure_fingerprint("codeql", "FAILURE", "abc123", ["A", "B"])

    assert left == right


def test_workflow_and_action_changes_require_human_review() -> None:
    for path in (
        ".github/workflows/repair.yml",
        ".github/actions/repair/action.yml",
        ".github\\workflows\\repair.md",
        "./.github/workflows/notes.md",
    ):
        decision = classify_change([path])
        assert decision.risk == "high"
        assert decision.human_review_required
        assert not decision.automated_merge_allowed


def test_leading_dot_on_github_directory_cannot_be_stripped_into_low_risk_docs() -> None:
    decision = classify_change([".github/workflows/example.md"])

    assert decision.risk == "high"
    assert "workflow control plane" in decision.reasons
    assert not decision.automated_merge_allowed


def test_invalid_or_traversing_paths_fail_closed() -> None:
    for path in (
        "../docs/readme.md",
        "/tmp/readme.md",
        "docs//readme.md",
        "docs/../readme.md",
    ):
        decision = classify_change([path])
        assert decision.risk == "high"
        assert "invalid or non-canonical repository path" in decision.reasons
        assert decision.human_review_required


def test_security_findings_cannot_be_auto_merged_and_change_decision_identity() -> None:
    ordinary = classify_change(["docs/guide.md"])
    security = classify_change(["docs/guide.md"], security_finding=True)

    assert ordinary.risk == "low"
    assert ordinary.automated_merge_allowed
    assert security.risk == "high"
    assert security.human_review_required
    assert not security.automated_merge_allowed
    assert ordinary.fingerprint != security.fingerprint


def test_security_control_paths_cannot_be_auto_merged() -> None:
    for path in (
        "docs/security-policy.md",
        "docs/attestation.md",
        "docs/merge-gate.md",
        "sandbox/policy.md",
    ):
        decision = classify_change([path])
        assert decision.risk == "high"
        assert decision.human_review_required
        assert not decision.automated_merge_allowed


def test_dependency_manifests_require_human_review() -> None:
    for path in (
        "pyproject.toml",
        "package-lock.json",
        "requirements-prod.txt",
        "service/requirements.txt",
    ):
        decision = classify_change([path])
        assert decision.risk == "high"
        assert decision.human_review_required
        assert not decision.automated_merge_allowed


def test_small_ordinary_documentation_change_can_be_low_risk() -> None:
    decision = classify_change(["docs/guide.md", "README.md"])

    assert decision.risk == "low"
    assert decision.automated_merge_allowed
    assert not decision.human_review_required
    assert decision.reasons == ()


def test_code_or_large_documentation_change_is_not_auto_mergeable() -> None:
    code = classify_change(["backend/app.py"])
    many_docs = classify_change(["a.md", "b.md", "c.md", "d.md"])

    for decision in (code, many_docs):
        assert decision.risk == "medium"
        assert decision.human_review_required
        assert not decision.automated_merge_allowed


def test_high_risk_repairs_have_explicit_quarantine_disposition() -> None:
    workflow = classify_change([".github/workflows/repair.yml"])
    security = classify_change(["docs/guide.md"], security_finding=True)
    ordinary_code = classify_change(["backend/app.py"])
    safe_docs = classify_change(["docs/guide.md"])

    for decision in (workflow, security):
        assert decision.quarantined is True
        assert decision.disposition == "quarantine"
        assert decision.human_review_required is True
        assert decision.automated_merge_allowed is False

    assert ordinary_code.quarantined is False
    assert ordinary_code.disposition == "human_review"
    assert safe_docs.quarantined is False
    assert safe_docs.disposition == "auto_merge"
