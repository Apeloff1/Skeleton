# Authoritative-work reconciliation

A work-order record is an idempotency and resource fence, not permission to
generate from a fabricated receipt. A real success is only accepted after an
independent read of canonical `ExecutionSpine.replay()` with exact actor,
session, request, seed, sampling parameter and prompt SHA.

A request whose durable dispatch marker exists but whose native result is
absent remains `dispatch-unknown`. Operator may mark it held. Neither outcome
is permission to regenerate the native model. An undispatched lease may be
cancelled with the original lease token; no other reservation is refunded.

The work order stores only prompt digests, not prompt bytes; jobs and outbox
are scoped to tenant, subject and model identity. The same SQLite transaction
updates budget, revision, event payload/chain and outbox. Every audit checks
stored event bodies and current job state hashes, plus total reserved and
consumed tokens across tenant budgets.

These are source-level guarantees, not external authentication. Only trusted
owner code may invoke the queue and supply operator approval; model output and
retrieved text must never be connected as trusted callers.
