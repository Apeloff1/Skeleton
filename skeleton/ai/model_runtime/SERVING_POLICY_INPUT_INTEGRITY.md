# Native serving policy — input-bound decision contracts

Operator and contract supplement to [RUNTIME_CORE.md](RUNTIME_CORE.md).


## Governed serving-policy decision identity

`PolicyAwareServingPlanner` validates a bounded native serving request before
policy evaluation. Request IDs must be canonical non-control UTF-8 text,
service class must be typed, token counts must honor the model-runtime token
budget, and prefix/draft availability flags must be explicit booleans. No
network/provider/model execution authority is introduced.

Serving plan v2 receipts bind every policy input: request identity, full token
counts, prefix/cache/draft facts, service class, KV/queue pressure and the
compiled runtime-policy digest. Two plans that happen to make the same
routing decision under different inputs have different receipts, so stale
pressure evidence cannot silently masquerade as a current plan. Operators
should require a fresh plan at execution admission, not treat the digest as a
signature or independent verification of reported pressure.

Focused tests:

```bash
python -m unittest tests.flgb.test_serving_policy_input_integrity -v
python -m unittest tests.flgb.test_serving_policy_era tests.flgb.test_serving_policy_pressure -v
```

### Explicit serving plan verification

`PolicyAwareServingPlanner.verify(plan, trusted_request, kv_pressure_pct=...,
queue_pressure_pct=...)` recreates the current plan under the compiled policy,
compares its digest without timing-dependent short-circuiting and requires
all typed receipt fields to match. A stale pressure record, changed policy,
different request or altered receipt is refused. The caller must provide
trusted fresh inputs; merely comparing to the plan's own claimed inputs would
not be a meaningful authority boundary. The verifier does **not** contact
providers, mutate scheduling state or independently authenticate telemetry.

## Malformed receipt digest handling

`PolicyAwareServingPlanner.verify()` rejects ill-typed, non-ASCII,
nonhexadecimal, wrong-length and uppercase hash identifiers with a stable
`ValueError`, rather than leaking a lower-level comparison error. A valid
lowercase SHA-256 digest is still only deterministic integrity evidence, not
proof of a trusted pressure sensor or execution authority.
