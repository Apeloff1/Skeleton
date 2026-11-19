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


def test_removing_full_domain_suite_fails_readiness_contract(tmp_path, monkeypatch, capsys) -> None:
    workflow = contract.WORKFLOW.read_text(encoding="utf-8")
    assert contract.main() == 0
    damaged = workflow.replace("skeleton/testing --tb=short", "skeleton/testing/test_engine_v3.py --tb=short")
    assert damaged != workflow
    path = tmp_path / "merge-readiness.yml"
    path.write_text(damaged, encoding="utf-8")
    monkeypatch.setattr(contract, "WORKFLOW", path)
    assert contract.main() == 1
    assert "complete canonical domain suite" in capsys.readouterr().out
