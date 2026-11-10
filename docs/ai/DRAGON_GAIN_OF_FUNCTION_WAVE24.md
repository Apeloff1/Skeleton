# Wave 24 — Canonical frontier circuit breaker for URL traps

The canonical CrawlRun enqueue step now applies a finite deterministic
family guard after original URL policy admission and before adding any
new queued work. It vetoes URL credential parameters, excessive faceted
query keys, extreme numeric page indices, repeated path segments, and
overly repeated URL families. The guard is a restriction only.

URL family fingerprints normalize numeric and long hexadecimal path
identities plus sorted query key names. A family is capped at 24 distinct
canonical URLs per run (including seen and pending queue); this avoids
unbounded calendar and faceted pagination loops but retains independent
paths and ordinary pagination. The algorithm is pure, bounded by the
existing 512-row state envelopes, deterministic across snapshot replay,
and adds no mutable state, IO, network permissions or worker leases.

All original robots, consent, owner/tenant restrictions, host pacing,
public-IP/DNS pinning, redirects, request/byte reservation, rights and
Mongo CAS remain authoritative. No source HTML or model instructions
can override the circuit. Tests exercise direct trap conditions and
real scripted canonical HTML capture with 40 paginated URLs, proving
24 remain admitted, secrets are excluded, and no extra request happens.

The family guard is deliberately conservative: legitimate very large
pagination families require an explicit future scoped design decision
rather than implicitly escalating crawler breadth.
