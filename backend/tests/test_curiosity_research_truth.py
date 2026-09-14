import asyncio

from core.curiosity_engine import Inquiry
from core.curiosity_research_pipeline import EnsembleCuriosityResearcher


INQUIRY = Inquiry(
    id="inq-1", subject="battery cycle life", questions=("What affects measured cycle life?",),
    context_record_ids=(), keywords=("battery", "cycle"), score=0.8, reason="test",
)


async def agreeing_model(task, prompt, system):
    return {
        "summary": "Panel hypothesis.",
        "claims": ["Battery chemistry X increases measured cycle life by 20 percent."],
        "questions": ["Under which temperature?"],
        "contradictions": [],
        "tags": ["battery"],
    }


def test_three_models_agreeing_produce_no_empirical_claim_evidence():
    researcher = EnsembleCuriosityResearcher(agreeing_model, models=("a", "b", "c"))
    result = asyncio.run(researcher(INQUIRY, {}))
    claim = result["claims"][0]
    assert result["claim_evidence"][claim] == []
    assert result["claim_bound_evidence_count"] == 0
    assert len(result["panel"]) == 3


def test_unverified_locator_cannot_bind_source_to_claim():
    claim = "Battery chemistry X increases measured cycle life by 20 percent."
    async def search(inquiry, questions):
        return [{
            "source": "paper-a", "locator": "doi:example", "kind": "primary_empirical",
            "independence_group": "lab-a", "quality": 0.95, "supports_claims": [claim],
            "verified_locator": False, "reproducible": True,
        }]
    researcher = EnsembleCuriosityResearcher(agreeing_model, source_search=search, models=("a", "b"))
    result = asyncio.run(researcher(INQUIRY, {}))
    assert result["claim_evidence"][claim] == []


def test_verified_locator_binds_only_exact_named_claim():
    claim = "Battery chemistry X increases measured cycle life by 20 percent."
    async def search(inquiry, questions):
        return [{
            "source": "paper-a", "locator": "doi:example", "kind": "primary_empirical",
            "independence_group": "lab-a", "quality": 0.9, "supports_claims": [claim, "Different claim"],
            "verified_locator": True, "reproducible": True, "peer_reviewed": True,
        }]
    researcher = EnsembleCuriosityResearcher(agreeing_model, source_search=search, models=("a", "b"))
    result = asyncio.run(researcher(INQUIRY, {}))
    assert len(result["claim_evidence"][claim]) == 1
    row = result["claim_evidence"][claim][0]
    assert row["source_id"] == "paper-a"
    assert row["independence_group"] == "lab-a"
    assert "Different claim" not in result["claim_evidence"]
