from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR = ROOT / "skeleton" / "automation" / "supervisor.py"
MACHINE_CONFIG = ROOT / ".machine" / "repository.toml"
AGENTS = ROOT / "AGENTS.md"
MERGE_READINESS = ROOT / ".github" / "workflows" / "merge-readiness.yml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_supervisor_consumes_one_cached_machine_session() -> None:
    source = _text(SUPERVISOR)
    assert "from functools import lru_cache" in source
    assert "from skeleton.repo_machine.session import build_machine_session" in source
    assert "@lru_cache(maxsize=1)" in source
    assert "def _machine_repository_context()" in source
    assert "build_machine_session(" in source
    assert '"machine_repository": _machine_repository_context()' in source


def test_machine_plane_is_critical_first_class_zone() -> None:
    source = _text(MACHINE_CONFIG)
    block = source.split('name = "repo-machine"', 1)[1].split("[[zone]]", 1)[0]
    assert '".machine/"' in block
    assert '"skeleton/repo_machine/"' in block
    assert 'owner = "machine-architecture"' in block
    assert 'criticality = "critical"' in block


def test_agent_contract_preserves_authority_and_exact_head_validation() -> None:
    source = _text(AGENTS)
    assert "Supervisor -> Secretary -> registered Worker" in source
    assert "Exact-head" in source or "exact head" in source.lower()
    assert "untrusted data" in source
    assert "must not grant permissions" in source


def test_agent_contract_requires_machine_map_for_broad_work() -> None:
    source = _text(AGENTS)
    assert ".machine/repository.toml" in source
    assert "skeleton.repo_machine" in source
    assert "do not invent" in source.lower()


def test_merge_readiness_runs_machine_contract_and_regressions() -> None:
    source = _text(MERGE_READINESS)
    assert "python scripts/check_repo_machine.py" in source
    assert "skeleton/repo_machine" in source
    assert "tests/test_repo_machine.py" in source
    assert "tests/test_repo_machine_sota.py" in source


def test_machine_agent_surface_has_no_dynamic_eval_contract() -> None:
    supervisor = _text(SUPERVISOR)
    agent_contract = _text(AGENTS)
    assert "eval(" not in supervisor
    assert "exec(" not in supervisor
    assert "MODEL_API_KEY" not in agent_contract
