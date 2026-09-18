from scripts import check_merge_readiness_contract as contract


def test_job_block_retains_exact_readiness_guard() -> None:
    workflow = f"""jobs:
  readiness:
    name: Merge Readiness
    {contract.READINESS_GUARD}
    needs:
      - unit
"""

    readiness = contract.job_block(workflow, "readiness")

    assert "name: Merge Readiness" in readiness
    assert contract.READINESS_GUARD in readiness


def test_later_job_cannot_satisfy_readiness_guard_contract() -> None:
    workflow = f"""jobs:
  readiness:
    name: Merge Readiness
    needs:
      - unit
  later_job:
    name: Later job
    {contract.READINESS_GUARD}
"""

    readiness = contract.job_block(workflow, "readiness")

    assert "later_job:" not in readiness
    assert contract.READINESS_GUARD not in readiness


def test_job_block_returns_empty_for_missing_job() -> None:
    assert contract.job_block("jobs:\n  unit:\n    name: Unit\n", "readiness") == ""
