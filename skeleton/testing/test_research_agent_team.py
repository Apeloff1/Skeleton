from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.research_evaluation_assurance import (
    ResearchEvaluationAssuranceError,
    ResearchRoleTemplate,
    build_research_team,
)


def templates():
    return (
        ResearchRoleTemplate(
            "researcher",
            "propose and run bounded experiments",
            "creator",
            ("read-evidence", "run-sandbox-experiment"),
        ),
        ResearchRoleTemplate(
            "verifier",
            "independently challenge evidence",
            "independent-verifier",
            ("read-evidence", "verify-result"),
        ),
    )


def test_research_team_binds_roles_to_verification_standard() -> None:
    team, evidence = build_research_team(
        "team-1",
        templates(),
        verification_standard_ref="VS-003",
    )
    assert len(team.roles) == 2
    assert evidence.verification_standard_ref == "VS-003"
    assert evidence.independent_groups == ("creator", "independent-verifier")
    assert evidence.production_authority is False
    assert len(evidence.digest) == 64


def test_research_role_forbids_production_and_self_verification() -> None:
    with pytest.raises(ResearchEvaluationAssuranceError, match="must forbid"):
        ResearchRoleTemplate(
            "unsafe",
            "unsafe role",
            "creator",
            ("read",),
            ("production_mutation",),
        )


def test_research_team_requires_independent_groups() -> None:
    duplicate_group = (
        ResearchRoleTemplate("a", "one", "same", ("read",)),
        ResearchRoleTemplate("b", "two", "same", ("read",)),
    )
    with pytest.raises(ValueError, match="independent"):
        build_research_team(
            "team",
            duplicate_group,
            verification_standard_ref="VS-003",
        )
