"""Jeeves year-scale production worker binding.

Jeeves proposes/executes through the canonical governed runtime supplied by
the host; this wrapper never invents a model or a completed authored scene.
Immutable step receipts must be independently checked against the canonical
Jeeves state before a production checkpoint advances.
"""
from skeleton.automation.annual_worker import AnnualWorkRunner, ExternalWorker, ExternalVerifier
from skeleton.automation.annual_production import AnnualProductionStore


def make_jeeves_annual_runner(
    store: AnnualProductionStore,
    *,
    run_authorized_step: ExternalWorker,
    verify_canonical_receipt: ExternalVerifier,
    clock=None,
) -> AnnualWorkRunner:
    from time import time
    return AnnualWorkRunner(
        store, system="jeeves", worker=run_authorized_step,
        verify=verify_canonical_receipt, clock=clock or time,
    )
