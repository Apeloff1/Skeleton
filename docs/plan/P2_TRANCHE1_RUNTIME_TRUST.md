# P2 Tranche 1 — Runtime Trust, Recovery and Functional Acceptance

Machine plan: `machine/ai_p2_tranche1_plan.json`
Validator: `scripts/check_p2_tranche1_plan.py`
Activation compiler: `scripts/prepare_p2_tranche1_activation.py`

## Status

**Prepared, non-owning.**

This plan does not schedule or transfer ownership of any additional P2 volume. Every selected volume must remain in the 272-volume T0 queued set, and no existing P2 task may own it. Activation is a separate reviewed change after **all seven T0 tasks** are `landed_unpromoted`, including `P2-NATIVE-01`.

That fence allows selection and dependency design to proceed without pretending the first tranche is finished.

## Deterministic activation proposal

The activation compiler is deliberately **non-mutating**. On the current branch it must refuse to activate because `P2-NATIVE-01` is not yet `landed_unpromoted`.

A T0 task counts as landed for activation only when its backlog record also carries a GitHub PR reference, a full lowercase merge SHA, and successful workflow evidence while completion and implementation/verification signatures remain false. A status-only edit fails closed.

Once every T0 task is landed with that evidence, the same compiler must derive an exact proposal with **57 scheduled / 257 queued** volumes while preserving the complete 314-volume P2 source partition. It generates five new task owners—DATA, SEC, INFER, RECOVERY and FUNCTIONAL—with DATA/SEC fenced on the landed native task and the remaining dependency DAG derived from this plan.

The compiler cannot edit the canonical execution map or backlog. A separate reviewed activation change must apply the proposal, rerun the full P2 map validator, and keep all completion/sign-off fields false.

## Why these 15 volumes

T1 prioritizes runtime trust over speculative breadth:

- **State/event foundation:** VOL-005, VOL-039, VOL-132, VOL-134.
- **Security/privacy foundation:** VOL-026, VOL-027, VOL-167, VOL-169, VOL-172, VOL-175.
- **Inference reliability:** VOL-007.
- **Recovery evidence:** VOL-091, VOL-096.
- **Functional-AI acceptance:** VOL-097, VOL-104.

VOL-005, VOL-007, VOL-026, VOL-027 and VOL-039 already have multiple live implementation and focused-test anchors. Their existing tests are starting evidence only; they do not close the masterplan gaps.

The other ten volumes deliberately represent **missing semantic or end-to-end harness work over existing runtime roots**. Their lack of live canonical test anchors is recorded rather than hidden.

## Workstream order

| Workstream | Scope | Depends on |
| --- | --- | --- |
| P2-T1-DATA | state ownership, consistency, events, outbox/inbox | — |
| P2-T1-SEC | threat/boundary/egress/privacy/tenant controls | — |
| P2-T1-INFER | inference reliability | P2-T1-SEC |
| P2-T1-RECOVERY | versioned runbooks + VS-000 recovery | DATA, SEC |
| P2-T1-FUNCTIONAL | VS-001 + functional acceptance | DATA, SEC, INFER, RECOVERY |

## Deliberately deferred

Training infrastructure (VOL-006), world/simulation expansion (VOL-019/VOL-073), multimodal convergence (VOL-020), and domain-specialist expansion (VOL-071/VOL-072/VOL-074) remain queued. They should not outrun state, security, recovery and functional acceptance authority.

## Authority boundary

Selection does not imply implementation, maturity, completion or sign-off. Activation must preserve the exact 314-volume P2 source partition, unique task ownership, the master build sequence, vertical-slice evidence requirements, and signed accountability.
