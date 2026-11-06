"""Dragon crawler campaign assurance under the existing canonical owner.

Explicitly import from an authorized application boundary. No import starts
a worker, opens a connection, writes state or grants new permission.
"""
from .contracts import (
    CampaignScope, CampaignLimits, CampaignMandate,
    ResearchCandidate, ResearchDispatch, CampaignPlan,
)
from .budget import BudgetProjection, BudgetReservation, project_budget, reserve_advisory
from .planner import build_campaign_plan
from .evidence import SourceInspection, CampaignPassage, EvidenceInspection, inspect_campaign_evidence
from .lineage import (
    SourceLink, LineageImpact, DuplicateFamily,
    validate_lineage, invalidation_closure, exact_duplicate_families,
)
from .journal import CampaignEntry, CampaignJournal
from .revisions import (
    SourceDelta, PassageDisposition, RevisionImpact, compare_research_revisions,
)
from .diagnostics import CampaignDiagnostics, measure_campaign_diagnostics
from .integration import CampaignInspection, frontier_hints, inspect_crawl_campaign
from .recovery import RecoveryAssessment, assess_campaign_recovery
from .control import CampaignControlProposal, propose_campaign_control
from .references import CitationCheck, CitationReport, verify_current_citations
from .recrawl_advisory import RefreshObservation, RefreshProposal, RefreshPortfolio, propose_adaptive_refresh
from .stopping import ResearchStopGate, decide_campaign_stop

__all__ = [name for name in globals() if not name.startswith("_")]
