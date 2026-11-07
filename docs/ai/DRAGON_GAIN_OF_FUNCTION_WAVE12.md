# Dragon Wave 12 — Archival and technical artifact acquisition

Real canonical CrawlRun ingestion gains a finite WARC archive catalog,
privacy-reduced HAR performance traces, syntactically bounded inert unified
Git patches, and CSL JSON scientific references. These are new retained
source formats, not standalone advisory dashboards or network services.

The WARC catalog checks record framing and declared lengths, stores only
type, date, byte count, payload SHA-256 and a boolean target-presence label.
Nested request and response bytes are never executed, replayed or retained
as raw evidence. HAR traces omit URLs, cookies, headers, request bodies,
response bodies, IPs, query strings and authentication data. Patches omit
known credential indicators, deny binary patch execution and prevent
filesystem path traversal. CSL citations retain only curated literal fields.

All format MIME values are explicitly enumerated in the canonical worker
policy. Source snapshots retain the original raw response digest, extracted
text hash, truncation and unreviewed provenance. Existing fixed owner/tenant
consent, robots checks, public DNS/socket pinning, redirect approval, worker
lease, request and byte budget, cancellation and Mongo snapshot CAS remain
authoritative. No new fetch destinations are inferred from URLs in these
formats, and no provider calls, code execution or automated publication occur.

The source-only suite includes parser bounds, credential suppression and
actual scripted canonical run_slice/replay tests. Device, live-network,
proxy/DNS races, persistent Mongo, distributed lease validation, all
repository CI, merge and release remain unqualified.
