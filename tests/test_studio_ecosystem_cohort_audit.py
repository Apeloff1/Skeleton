"""Assurance must walk every registered project and never skip a bad one."""
from pathlib import Path

import pytest

from skeleton.ai.game_builder.studio_ecosystem_cohort_audit import audit_all_studio_sources
from skeleton.ai.game_builder.studio_ecosystem_catalog import StudioEcosystemError


def test_complete_corpus_has_stable_chain_and_retains_release_holds():
    result = audit_all_studio_sources()
    assert result["indexed_projects"] >= 512
    assert result["consistent_projects"] == result["indexed_projects"], result["errors"]
    assert result["document_sections_expected"] == 8 * result["indexed_projects"]
    assert result["source_consistent"]
    assert not result["release_certified"]
    assert len(result["source_chain_sha256"]) == 64
    assert audit_all_studio_sources()["source_chain_sha256"] == result["source_chain_sha256"]


def test_denies_fake_corpus_completion_and_bad_arguments():
    baseline = audit_all_studio_sources(minimum_projects=10000)
    assert not baseline["source_consistent"]
    assert baseline["status"] == "source_rejected"
    with pytest.raises(StudioEcosystemError):
        audit_all_studio_sources(max_error_details=0)
    with pytest.raises(StudioEcosystemError):
        audit_all_studio_sources(minimum_projects=True)
