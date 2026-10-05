from __future__ import annotations
import pytest
from skeleton.ai.research.research_agent_team import ResearchAssignment,ResearchRoleTemplate,ResearchTeamError,ResearchTeamPlan

def role(role_id,role_type,independent=False):
    return ResearchRoleTemplate(role_id,role_type,("read:evidence",),independent)

def test_research_team_requires_independent_verifier():
    plan=ResearchTeamPlan(
        "plan-1","Does method X improve quality?",
        (
            ResearchAssignment("a1","agent-investigator",role("r1","investigator"),("collect",)),
            ResearchAssignment("a2","agent-verifier",role("r2","verifier",True),("verify",)),
        ),
        "VS-003",
    )
    assert plan.production_authority is False
    assert len(plan.digest)==64

def test_verifier_role_requires_independence():
    with pytest.raises(ResearchTeamError,match="independent review"):
        role("r","verifier",False)

def test_agent_cannot_hold_multiple_roles():
    with pytest.raises(ResearchTeamError,match="distinct agents"):
        ResearchTeamPlan(
            "p","q",
            (
                ResearchAssignment("a1","same",role("i","investigator"),("x",)),
                ResearchAssignment("a2","same",role("v","verifier",True),("y",)),
            ),
            "VS-003",
        )

def test_team_cannot_claim_production_authority():
    with pytest.raises(ResearchTeamError,match="non-authoritative"):
        ResearchTeamPlan(
            "p","q",
            (
                ResearchAssignment("a1","one",role("i","investigator"),("x",)),
                ResearchAssignment("a2","two",role("v","verifier",True),("y",)),
            ),
            "VS-003",production_authority=True,
        )
