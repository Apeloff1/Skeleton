from scripts import check_merge_readiness_contract as contract


def test_leading_always_guard_accepts_canonical_forms() -> None:
    accepted = (
        "    if: always()\n",
        "    if: ${{ always() }}\n",
        "    if: always() && !cancelled()\n",
        "    if: ${{ always() && (github.event_name != 'pull_request') }}\n",
    )

    for job in accepted:
        assert contract.has_leading_always_guard(job), job


def test_leading_always_guard_rejects_nonleading_and_lookalike_forms() -> None:
    rejected = (
        "    if: success() && always()\n",
        "    if: ${{ success() || always() }}\n",
        "    if: almost_always()\n",
        "    if: always()oops\n",
        "    name: Merge Readiness\n",
    )

    for job in rejected:
        assert not contract.has_leading_always_guard(job), job


def test_job_block_does_not_leak_into_later_jobs() -> None:
    workflow = """jobs:
  readiness:
    name: Merge Readiness
    needs:
      - unit
  later_job:
    name: Later job
    if: always()
"""

    readiness = contract.job_block(workflow, "readiness")

    assert "name: Merge Readiness" in readiness
    assert "later_job:" not in readiness
    assert not contract.has_leading_always_guard(readiness)


def test_job_block_returns_empty_for_missing_job() -> None:
    assert contract.job_block("jobs:\n  unit:\n    name: Unit\n", "readiness") == ""
