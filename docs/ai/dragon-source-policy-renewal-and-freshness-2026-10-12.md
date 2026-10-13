# Dragon source policy renewal and freshness ledger
**Authored:** 2026-10-12 UTC  
**Target:** PR #3605, existing 248 technical-source candidates.

## Milestone A — Explicit acquisition-policy renewal

The acquisition workflow originally could archive past policy receipts using `SequentialAlmanacWorker.restart_blocked`, but no source-aware, crash-safe renewal transaction joined that operation to the new Dragon durable source queue. The new `DragonSourcePolicyRenewal` closes the gap for two deliberately narrow entry conditions:

- **Expired policy:** source must remain in canonical stage 1 (fetch pending), have an actually expired stage-0 policy receipt, and be in a durable `scheduled` or `retry_wait` state. It cannot have a live resource grant or unresolved host quarantine/hold.
- **Scheduled revisit:** source must be in stage 5 (`reviewed`), have a completed durable observation, current accepted Wiki lineage, and an actual previous captured revision old enough to meet the editorial per-family review cadence. This is a *revisit proposal*, not proof the remote page changed.

The renewal request takes an explicit 64-hex expected operation-head digest and a supervisor-authorized reason. It performs a single `BEGIN IMMEDIATE` SQLite transaction to validate the owner, canonical source identity, stage history and host fence; append the `policy_recheck` operations event; archive all old acquisition-stage evidence; and put the canonical source job back into **policy stage 0**. Missing, corrupt, replayed, live, not-yet-due, or manually held sources fail closed.

The new `policy_recheck` state is **not dispatchable**. `rearm` requires a freshly completed policy receipt in the existing canonical SequentialAlmanacWorker, checks the old receipt was superseded, requires the new policy receipt timestamp to postdate the reset, verifies that the prior policy and source still match, and preserves any existing host cooldown when scheduling the next fetch. It does **not** assert that site permissions have been verified independently merely because a caller passes `trusted_worker=True`: the deployment must genuinely authenticate external policy reviewers and supply the robots/terms/reference-use permission evidence when completing stage zero.

Manual `policy_hold` from a dangerous or extreme robots delay remains terminal in this milestone. **It is not silently reactivated** by this renewal path, by waiting for a timer, or by creating a new source record.

## Milestone B — Editorial freshness assessments

The new read-only `DragonSourceRefreshPlanner` class reports for an owner-scoped source:

- Current durable operation state and canonical almanac stage
- Expiry time of the *recorded* policy receipt, verified by its digest
- Latest captured content digest and observation timestamp, if any
- Family-defined editorial review cadence and next suggested check
- Reasons such as `policy_expired_requires_recheck`, `reviewed_source_revisit_due`, `reviewed_source_cadence_not_due`, `acquisition_pending_independent_review`, `robots_or_retry_cooldown`, `manual_site_policy_hold`, or `active_or_unreconciled_worker`

The planner sets `observed_remote_change=False` because age and publication metadata do not prove that a URL changed. It makes **zero network calls** and does not grant source rights, background execution, Wiki approval, shadow weights or training permission.

The operator-facing `DragonSourcePolicyRenewal.pending` queue verifies its event heads against the append-only journal and lists pending stage-zero and stage-one renewals without mutating source policy. The existing trusted-local CLI now supports:

```sh
python -m skeleton.ai.game_builder.dragon_technical_source_cli refresh-inspect \
  --database /approved/studio.sqlite --owner studio \
  --source-id source-<64hex> --now "$(date -u +%s)" \
  --trusted-local-operator

python -m skeleton.ai.game_builder.dragon_technical_source_cli policy-renewal-pending \
  --database /approved/studio.sqlite --owner studio \
  --limit 20 --trusted-local-operator
```

Mutating renewal and site rights grants are **not** exposed through that read-only CLI. An authenticated external supervisor must invoke `DragonSourcePolicyRenewal.request`, ensure the existing stage-zero policy review is properly completed, then invoke `rearm`. This does not authorize bypassing site robots/terms, using proprietary game assets, collecting private content or mass downloading pages.

## Validation and custody

Regression tests extend the real source-operations fixture to cover expiry detection, atomic history archive, non-dispatchable pending policy, owner isolation, stale compare-and-swap rejection, inability to rearm without fresh policy, successful fresh stage-zero approval, and forbidden reactivation from manually held robots policy.

The independent Wiki test suite also covers an actual five-stage accepted source being proposed for revisit only after the editorial review window, with all five prior receipts archived and the approved knowledge library preserved for historical custody. No test asserts that content changed merely because a revisit became due.

**Deployment/CI:** This is authored repository code. Python regression success, end-to-end host permission evidence, externally supervised process stop, and real crawling must be separately verified before claiming production activation.

## Next operations work

Protect external reviewer identity (a signed, revocable source-policy grant service rather than boolean worker trust), add observability/metrics for queue age and cooldowns, then run narrow, genuinely permitted live acquisitions with independent source review. Keep video and proprietary platform materials on separately permissioned media and licensing paths.
