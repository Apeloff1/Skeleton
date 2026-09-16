from skeleton.automation.repair_intake import intake_fingerprint, issue_marker


def test_intake_fingerprint_is_deterministic():
    assert intake_fingerprint("CodeQL", "failure", "ABC123", "42") == intake_fingerprint(
        "codeql", "FAILURE", "abc123", "42"
    )


def test_intake_marker_is_machine_readable():
    fingerprint = intake_fingerprint("CodeQL", "failure", "ABC123", "42")
    assert issue_marker(fingerprint) == f"<!-- repair-intake:fingerprint={fingerprint} -->"
