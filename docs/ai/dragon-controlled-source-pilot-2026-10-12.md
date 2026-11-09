# Dragon controlled source-acquisition pilot
**Implementation:** 2026-10-12 UTC
**Depends on:** Source Capture Permission Authority and the existing signed nest, resource scheduler, 248-source atlas, policy/capture ledgers, and Glean Matrix.

## Milestone

The opt-in `DragonResearchPilot` provides a single point of entry for individually approved live-source experiments, **not** an always-on autonomous crawler. It requires a valid, nonrevoked, owner- and source-bound `SourceCaptureGrant`, explicit consent to this exact live pilot, permitted reference retention, trusted OS activity/thermal telemetry and a socket-bound `SafeHttpFetcher` restricted to the registered host.

Before reserving RAM/CPU, the pilot verifies the signed grant. It asks `DragonResearchSupervisor` for **only the permit's source**, which must already be in the durable ready queue with current stage-0 policy evidence. The existing signed nest, five-minute idle check, specialist article consent and global resource scheduler then decide whether a grant can be issued. A returned worker also receives the cross-process durable source/host lease; a mismatch, host race or lease failure releases the not-yet-running resource grant.

The synchronous `acquire_canonical_technical_article` has an optional signed-permission context. When the controlled pilot uses it, grant verification happens (1) before starting robots discovery, (2) at the start of every robots/page HTTP request and (3) immediately before storing extracted source text. Each verification re-reads the durable revocation ledger, policy receipt and source identity, so a withdrawn grant cannot authorize a second request or an evidence write merely because a worker was previously admitted.

The canonical crawler keeps its bounded one-host socket-bound DNS, robots, HTTPS and byte/resource limits, same-URL capture requirement, short-lived worker lease, foreground interruption and proper resource stop acknowledgement. Source passage proposals go to the existing exact-text capture journal, analysis and independent Wiki review. Discovery or observation still grants **zero model XP and zero weight-training authority**.

## Trusted host API

```python
# No network I/O, no resource grant:
pilot = DragonResearchPilot(supervisor, separately_provisioned_source_authority)
preview = pilot.preview(signed_grant, now=verified_utc_epoch, authorized=True)

# Actual network operation, only with real source and rights approval:
result = pilot.execute(
    signed_grant, fetcher=socket_bound_allowlisted_fetcher,
    sample_provider=trusted_hardware_monitor,
    consent_provider=trusted_per_lane_consent_provider,
    idle_since_provider=verified_os_idle_origin,
    at_provider=trusted_utc_timestamp,
    clock=monotonic_resource_clock, sleep=bounded_worker_sleep,
    capture_id=unique_attempt_id, authorized=True, trusted_worker=True,
    live_network_approved=True, reference_storage_permitted=True,
)
```

**Never** replace the trusted callbacks with user-provided strings or an unverified web page, issue grants automatically for all atlas sources, or use this pilot to access sites outside the rights scope. The explicit `live_network_approved` argument must be supplied for every invocation, rather than inferred from the presence of a signed grant.

No live pilot is automatically launched by the merged/source branch. Execution still requires an externally authenticated host controller and actually licensed/permissioned destinations. Existing legacy acquisition callers remain available for compatibility; production must route controlled pilot traffic through `DragonResearchPilot` and separately harden/block nonpilot entrypoints before expanding deployment.

## Regression scenarios

The source-operations suite includes offline-fetched evidence under a valid scoped grant, denial of any network request before opt-in, denial without a queued source, forged source URL and owner scopes, mismatched HMAC key, expired grants, permanent issuer revocation, post-robots revocation blocking the page request, and no leaked global resource reservations. All HTTP responses in tests are locally supplied fixtures; they are not real acquisitions and do not prove site permissions.

**Next production milestone:** make the external reviewer/rights-attestation source cryptographically independent using an identity-provider-backed public-key signature; strengthen the process-global resource reconciler and explicit kill switch; then stage genuinely permissioned limited-scope live acquisitions with observability. None of those external controls can be inferred from the successful creation of these code files.
