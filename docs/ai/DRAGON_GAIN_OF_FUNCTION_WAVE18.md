# Dragon Wave 18 — Source-bound software supply-chain intelligence

This branch extends the actual canonical Dragon crawler to ingest three
new machine-readable external source categories: CycloneDX JSON SBOMs,
SPDX 2.2/2.3 JSON inventories and OpenVEX vulnerability claims. They are
not a credential-bearing package manager, vulnerability scanner, source
license grant, artifact installer or automated security certification.

- CycloneDX: finite package components, version, ecosystem, declared
  license, checksum-presence and a normalized directed dependency graph.
- SPDX: package inventory, normalized DEPENDS_ON / DEPENDENCY_OF links,
  declared license and source-side checksum-presence. Supplier download URLs
  and package locators are not exposed, resolved or traversed.
- OpenVEX: bounded vulnerability-label, subject count, declared status
  and justification summaries explicitly retaining unverified supplier
  claims, never treating a "not_affected" claim as clearance.
- Shared dependency graph: exact node/edge identity validation, finite
  fanout, duplicate rejection, unresolved identity reporting, graph
  fingerprints and iterative cycle-affected accounting. Graph results
  never change capture permission, worker grants or actual installations.

No references in source files grant additional network requests. Metadata
and package URLs with potential secrets remain out of the retained
projection; only curated unreviewed labels and structural measurements
reach the canonical source hash/evidence system. Current owner, robots,
consent, host/port, DNS, rights, budget, provenance and Mongo CAS controls
stay authoritative.

The source workflow compiles all parser/graph modules and checks direct
graph/format regressions, source privacy, rejected malformed documents,
actual scripted CrawlRun acquisition, metered requests and snapshot replay.

This remains a draft candidate. A passing source-only suite does not
establish external supplier trust, license clearance, live network,
physical platform, distributed-worker or launch readiness.
