"""Operator-facing review of a journal claim and independently retained result.

This module prepares evidence only. It never signs recovery, reissues work,
or silently settles a claim. The operator must verify process quiescence and
retain an independent custody checkpoint before authorizing reconciliation.
"""
from dataclasses import dataclass
from hashlib import sha256
import json

from skeleton.frontier.durable_work import DurableWorkJournal, RecoveryChallenge, WorkConflict
from skeleton.frontier.worker_results import WorkerResultStore
from skeleton.prood.local_executor import verified_predecessors, worker_input_digest


@dataclass(frozen=True, slots=True)
class ResultRecoveryReview:
    challenge: RecoveryChallenge
    proposed_state: str
    receipt_digest: str
    result_present: bool
    input_digest: str | None
    review_digest: str
    independent_quiescence_verified: bool = False


def review_worker_result(journal: DurableWorkJournal, results: WorkerResultStore,
                         work_id: str) -> ResultRecoveryReview:
    if type(journal) is not DurableWorkJournal or type(results) is not WorkerResultStore:
        raise TypeError("canonical custody owners required")
    if journal.scope != results.scope:
        raise WorkConflict("recovery scope mismatch")
    status = journal.status(work_id)
    if status.kind != "prood.worker":
        raise WorkConflict("only local worker results are supported")
    challenge = journal.recovery_challenge(work_id)
    result = results.load(work_id)
    if result is None:
        # Missing result is not proof that computation did not happen.
        state = "uncertain"
        receipt = sha256(("missing-worker-result:" + challenge.record_mac).encode("ascii")).hexdigest()
        digest = None
    else:
        body = journal.recovery_input(challenge, kind="prood.worker")
        predecessors = verified_predecessors(journal, results, status.dependencies)
        if result.input_digest != worker_input_digest(body, predecessors):
            raise WorkConflict("durable result does not bind the original claimed input")
        state = "succeeded" if result.succeeded else "failed"
        receipt = result.receipt_digest
        digest = result.input_digest
    # Detect a concurrent journal change across the independent DB reads.
    if journal.recovery_challenge(work_id) != challenge:
        raise WorkConflict("worker claim changed during recovery inspection")
    identity = [challenge.scope, challenge.work_id, challenge.owner, challenge.record_mac,
                state, receipt, digest]
    review = sha256(json.dumps(identity, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    return ResultRecoveryReview(challenge, state, receipt, result is not None, digest, review)
