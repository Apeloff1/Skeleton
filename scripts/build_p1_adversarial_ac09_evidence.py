            "skeleton/testing/test_swarm_exact_lease_atomicity.py",
            (
                "test_exact_lease_uses_one_clock_sample_for_commit",
            ),
        ),
        (
            "skeleton/testing/test_swarm_lease_rollback.py",
            (
                "test_exact_lease_commit_uses_one_clock_sample",
                "test_exact_lease_rollback_commit_uses_one_clock_sample",
                "test_exact_lease_rejects_non_finite_clock_without_mutation",
            ),
        ),
    ),
        and row.get("obligation_id") == obligation.obligation_id
        for row in raw_records
    )
    proofs: dict[str, dict[str, Any]] = {}
    evidence: list[dict[str, str]] = []
    for mode in EXPECTED_MODES:
