# Jeeves local inference efficiency: second-generation adaptive work

This change remains under the canonical runtime inference owner
(VOL-007/VOL-015). It extends existing local execution, not another model,
provider, crawler, state database, or autonomous permission authority.

## Improvements and rationale

| Area | Implemented control | Evidence status |
|---|---|---|
| Coalesced execution | Same model/request, tenant, grants, work class, cancellation lineage, cache epoch, explicit deadline | Existing runtime change |
| Cache expiry | Earliest possible expiry fast path; TTL and byte pressure still checked, explicit trim forces a sweep | Existing runtime change |
| Hardware fit | Resolve actual Linux cgroup mount and intersect nested CPU quota, cpuset and available RAM | Existing GGUF consumer planner change |
| Context packing | Exact excerpt bytes, pinned source/revision, as-of selection, deduplication, source-family quotas, atomic contradictory claims, required claim coverage | Explicit canonical request-preparation API |
| Reasoning allocation | Fixed-shape measured calibration, required dependency closure, stage/aggregate limits and optional value per measured millisecond | Advisory planning API |

Long context is not necessarily better context. The independent study
"Lost in the Middle" demonstrates positional sensitivity in long inputs
(https://aclanthology.org/2024.tacl-1.9/). This implementation therefore
preserves original evidence, tests full rendered input costs, prioritizes
required claims and tries placing stronger evidence toward both ends of
the reference section. This is a heuristic, not proven accuracy improvement.
It does not treat evidence JSON or source text as instructions.

## Evidence preparation procedure

1. Dragon/Wiki/Hoarder or another authorized context owner selects and verifies
   source revision, original exact excerpt bytes, principal and snapshot.
   Supply explicit valid-from and valid-until UTC epoch seconds, verified
   source/revision revocation sets, claim identity, stance and source family.
   The packing module does not fetch or certify external source facts.
2. Construct the original canonical LocalInferenceRequest without a context
   digest. Bind Scope.query_sha256 to that request's exact digest. Bind the
   activated model/tokenizer and source snapshot; do not use inferred
   identities. Call prepare_evidence_request with the active LocalInputBudget
   and its actual rendered-request token counter.
3. Inspect incomplete coverage, conflicts and omissions. Required or
   contradictory evidence cannot silently vanish into a successful result.
   If no candidate is returned, stop or ask the existing knowledge owner
   for a revised evidence set. The internal search has a finite tokenizer
   call ceiling; the final canonical recount uses one additional call.
4. Reconfirm source state and source permissions, then submit the complete
   derived prompt to the existing context pre-delivery seal and native
   admission. Do not use the advisory receipt as an authorization grant.
   Repacking a sealed request is prohibited.

No user data is moved to a cloud service. No retrieval index, trained neural
context extension, persistent memory or prompt-injection immunity is implied.

## Calibrated reasoning procedure

Create bounded stages with exact input/output reservations, dependencies
and explicit required/optional classification. Calibration observations bind
model, runtime, tokenizer, selected profile, device, protocol and thermal band.
A successful calibration must exercise the full requested token shape.
Failed/zero-token attempts continue to count against the requested shape.
Keep queue time distinct from execution time; add both and a conservative
margin to the worst fresh observation. A missing or failed required stage
holds the entire proposal; optional stages rank by estimated value per ms.
A proposal is not an execution lease, time guarantee, or automatic retry.
Each stage still requires its canonical supervisor admission, and actual
elapsed time, tokens and failures must be charged by that supervisor.

## Cache, scheduling and controller details

Existing exact-result cache and identity checks remain authoritative;
no tensor/KV/prefix cache was invented. Coalescing is allowed only within
matching explicit deadline contracts and work classes, and after cache
epoch boundaries new requests cannot inherit old in-flight work. An
existing follower is conservatively held if the cache epoch changed.
An already running leader retains physical custody and may complete its
original request, but stale-epoch cache publication stays forbidden.
Distinct deadlines may deliberately duplicate work to avoid one short
deadline cancelling unrelated longer-lived work. Unspecified deadlines
still coalesce within one class. Cache expiry only skips a full traversal
until the earliest possible expiry or TTL-policy change; byte limits and
per-hit expiry remain enforced. No externally visible telemetry schema change.

The GGUF planner uses the existing process cgroup mount resolver for Linux
v1/v2, counts the tightest reachable RAM/CPU/cpuset ancestor and holds on
malformed present controller data. It does not infer GPU memory or treat
swap as RAM. Target device measurements and physical fit remain independent.

## Qualification and rollback

Run after completion on the exact reviewed tree:

```sh
python -m unittest discover -s skeleton/testing -p 'test_jeeves_measured_tuning.py' -v
python -m unittest discover -s skeleton/testing -p 'test_jeeves_evidence_packing.py' -v
python -m unittest discover -s skeleton/testing -p 'test_jeeves_reasoning_economics.py' -v
python -m unittest discover -s skeleton/testing -p 'test_jeeves_local_flight_isolation.py' -v
python -m unittest discover -s skeleton/testing -p 'test_jeeves_consumer_controller_bounds.py' -v
python -m unittest discover -s skeleton/testing -p 'test_jeeves_cache_expiry_work.py' -v
```

Follow with existing inference and concurrency suites, all canonical
architecture/AI construction/interface/provider/enterprise and AI-tree
validators, exact-head security and CI. Compare local end-to-end quality,
TTFT, full request latency, peak process memory, thermal throttling and
cache overhead on the same approved model and hardware. No baseline benefit
is asserted without executed measurements. Roll back by reverting the
increment and retaining the already approved deployment configuration.
No migration of private state or model bytes is necessary.

Still held: native GUI/Dragon/Wiki end-to-end consumption of the new APIs,
independent real-device performance, hardware-aware physical GPU/KV reuse,
native streaming and any neural-weight training. No automatic model upgrade
or fallback to a hosted provider is introduced.
