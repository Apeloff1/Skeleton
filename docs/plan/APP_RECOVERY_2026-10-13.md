# App recovery checkpoint — 2026-10-13

Implementation checkpoint by Codex; not an application-completion or enterprise-qualification sign-off.
Inspected base: `714358b0e0bf285997a46f081cea5c559b33d1cb`.

## Implemented repair batch

- [x] Recover a lost Jeeves attachment through the existing Send/Retry flow using the original client message ID. Reconcile server history first; recover an already committed reply without generating again.
- [x] Preserve original session, project context and artifact-form preference for newly submitted unresolved turns, including across reloads. Later workspace edits must not change retry semantics.
- [x] Reject stale history refreshes if the local conversation changed while the request was in flight, preventing an older projection from erasing a newer completed reply.
- [x] Bind provider receipt evidence at FINALIZING as well as VERIFYING, including a resumed finalizer that starts from VERIFYING.
- [x] Correct the outage regression's ownership ledger expectation: the successful second HTTP request already owns epoch 2, so a subsequent holder must acquire epoch 3. Check every receipt-chain link.

## Construction obligations

This is a bounded repair of VOL-042 Product Shell and the existing AI chat lifecycle, under the current canonical owners.

| Level | Implementation and limitation |
| --- | --- |
| L00 Ownership | `WorkspaceController` owns device projection; `ChatTurnLifecycle` coordinates the canonical durable journal. |
| L01 Dependencies | Existing frontend and backend boundaries only; no provider, runtime root or dependency added. |
| L02 Contracts | Optional, bounded `retryRequest` metadata in workspace v1. Older caches remain readable. Backend request/response schemas unchanged. |
| L03 Authority | Canonical history is checked before reattachment retries; server request-reference validation still rejects changed content. |
| L04 Control flow | Reattach the original file, retain the original message ID, reconcile, then retry only if still unresolved. |
| L05 State | Retry parameters are device cache, not conversation authority. Attachment bytes remain ephemeral. Completed projections remove retry metadata. |
| L06 Privacy | Serialization explicitly allows only session/context/forms; binary payloads, extra fields and client transcript history are excluded. |
| L07 Recovery | Reload, timeout, prior server commit, context edits, stale refresh and resumed finalization have regression coverage. |
| L08 Observability | Conflict instructions explain original-request requirements. FINALIZING carries the minimized provider-set reference in the existing digest-chained journal. |
| L09 Economics | No additional automatic generation or polling. Recovered replies avoid a second model call. Unresolved metadata is bounded by existing conversation/message/context limits. No latency benchmark claimed. |
| L10 Evaluation | 42 frontend workspace checks and 19 backend lifecycle/route/engine-cutover checks pass locally. Strict TypeScript check passes for the portable controller/workspace modules. |
| L11 Deployment | Ship through existing frontend/backend builds and CI. Revert this commit for rollback; optional cache metadata is ignored by old clients. No database migration. |
| L12 Operator controls | Retry or Check server reconciles an uncertain result. Reattach the same original file; a different file remains a server conflict. Start a new conversation for a changed request. |
| L13 Exit | Repair implementation only. Exact-head CI, installed-client testing and full application acceptance remain outstanding. |

## Validation and remaining work

Local checks passed: application assembly preflight, architecture map, AI construction, capability interfaces, enterprise superiority contract, enterprise implementation notes, portable controller/workspace TypeScript, and the 61 focused checks above.

Provider bootstrap validation was launched; its repository-wide scan was still running when this checkpoint was written. It is not recorded as passed.

Remaining acceptance work:

- [ ] Exact-head CI and independent verification of this repair batch.
- [ ] Full Expo typecheck/export and browser/native interaction smoke.
- [ ] Production-equivalent engine, Mongo, authentication and conversation recovery journeys.
- [ ] Real installed local-model generation and task quality evaluation; mocked route checks cannot establish model capability.
- [ ] Feature-by-feature app inventory and executable acceptance before any whole-app completion percentage.

Existing cached failed turns created before this change have no original request snapshot. Their historical context cannot be reconstructed from local metadata; the server remains responsible for rejecting mismatched retries.

Structural checks are not semantic readiness evidence. The inspected enterprise checker reported 421 dossiers and zero enterprise-qualified profiles; those counts do not establish an app completion percentage.
