"""Builder year-scale production worker binding.

The host supplies its content-addressed builder graph executor and existing
build receipt verifier. One quantum gets a stable idempotency key and a
fenced worker epoch; this adapter does not run uncontrolled shell commands.
"""
from skeleton.automation.annual_worker import AnnualWorkRunner, ExternalWorker, ExternalVerifier
from skeleton.automation.annual_production import AnnualProductionStore


def make_builder_annual_runner(
    store: AnnualProductionStore,
    *,
    run_build_graph_quantum: ExternalWorker,
    verify_build_artifacts: ExternalVerifier,
    clock=None,
) -> AnnualWorkRunner:
    from time import time
    return AnnualWorkRunner(
        store, system="builder", worker=run_build_graph_quantum,
        verify=verify_build_artifacts, clock=clock or time,
    )
