"""Dragon year-scale production worker binding.

A legitimate Dragon work unit is captured and approved using the existing
Dragon evidence/almanac/lease owners supplied by the host. This adapter
only admits their independently verified output digests to the shared ledger.
It neither scrapes unauthorized sources nor promotes unreviewed weights.
"""
from skeleton.automation.annual_worker import AnnualWorkRunner, ExternalWorker, ExternalVerifier
from skeleton.automation.annual_production import AnnualProductionStore


def make_dragon_annual_runner(
    store: AnnualProductionStore,
    *,
    run_reviewed_research_quantum: ExternalWorker,
    verify_reviewed_knowledge: ExternalVerifier,
    clock=None,
) -> AnnualWorkRunner:
    from time import time
    return AnnualWorkRunner(
        store, system="dragon", worker=run_reviewed_research_quantum,
        verify=verify_reviewed_knowledge, clock=clock or time,
    )
