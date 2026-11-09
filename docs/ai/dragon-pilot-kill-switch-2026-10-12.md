# Dragon pilot kill switch — persistent default-deny, cross-process stop
**Authored:** 2026-10-12 UTC
**Depends on:** Signed source capture permits and controlled research pilot.

## Operational milestone

All controlled Dragon pilot workers are **disabled by default**. Issuing an independently scoped source permit does not turn the pilot on. `DragonSourcePermissionAuthority.verify` refuses permits whenever the owner-specific durable `control_state` is disabled, and the controlled HTTP adapter calls `verify` before the first request, each subsequent robots/page request, and source-content storage. Disabling an owner mid-robots response prevents the article request and leaves the worker to finish, acknowledge a real stop, and apply source retry/backoff.

The kill switch is a two-table SQLite, append-only sequence of `skeleton.dragon.pilot_control.v1` events and a checked head. Its initial state is absent/disabled. `set_pilot_enabled` is restricted to the trusted sealed issuer and uses an expected-head compare-and-swap. Enabling additionally requires **independently verified owner consent**; disabling does not require new consent. Every event records owner, sequence, prior digest, UTC epoch, new enabled state, bounded reason and `training_authorized=false`. A duplicate transition, head mismatch, replay, journal corruption, clock rollback or event exhaustion fails closed. A second process opening the same SQLite database sees the same state.

The toggle does not itself grant rights for any source. After re-enabling, the source must still have a valid distinct HMAC-signed `reference_capture` grant, current independently checked policy receipt, recorded robots/terms/reference-use permissions, idle article consent and a global resource grant. A disabled owner cannot continue acquiring merely because a short-lived worker ticket already exists.

## Operator instructions

Use the sealed issuer process with separately managed keys. Example with the actual principal/session verification omitted **on purpose**:

```python
state = permission_authority.control_state(owner, authorized=True)
disabled = permission_authority.set_pilot_enabled(
    owner, enabled=False, now=trusted_utc_epoch,
    expected_head_digest=state["head_digest"],
    reason="operator emergency research pause",
    authorized=True, trusted_issuer=True,
)
```

Reactivation requires **freshly verified owner consent** and a compare-and-swap from the latest disabled head; no user-facing browser or AI-generated assistant message is authority to enable it. No always-on scheduler is launched by this implementation. The physical network stack, OS worker process and global scheduler must still provide actual stop acknowledgements; the kill switch prevents *new* steps but does not reach back in time to cancel an already-started HTTP response.

## Regression tests

The offline source-operations tests include default-off behavior even with a valid signed grant, refusal to enable without verified owner consent, issuer role refusal, shutdown after a robots response without a page request, resource-slot release and durable retry, cross-instance state detection, stale restart/replay rejection, redundant transition rejection, and broken journal detection. Exact-head Python test execution must still be verified.

**No live sources acquired in this milestone.** The 248-source directory is not a source-rights inventory, and source-capture grants do not authorize media downloads, rights-free reuse or neural training.
