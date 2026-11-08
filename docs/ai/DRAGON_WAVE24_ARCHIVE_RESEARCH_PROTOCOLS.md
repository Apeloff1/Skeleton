# Dragon Wave 24 — Scholarly OAI-PMH, OPDS and IIIF archive navigation

The actual canonical Dragon worker now supports three archival discovery
protocols, with finite signed-off MIME admission and regression tests.

Open Archives Initiative OAI-PMH ListIdentifiers supports bounded server
resumption tokens and exact same-origin cursor pagination, without expanding
opaque identifier strings to unapproved URLs. XML DTD/ENTITY payloads and
malformed/oversized records fail closed, and source bytes never drive a new
network method or endpoint beyond the originally authorized HTTP GET.

OPDS 2 JSON catalogs nominate only next/prev typed OPDS pages and
same-origin navigation catalogs. Ebook purchases, DRM, acquisition,
publication downloads, authentication and publisher URLs are not followed.

IIIF Presentation 3 Collections nominate only same-origin Manifest and
Collection identifiers. IIIF Manifests enter the original unreviewed
source-capture pipeline as finite text describing labels, canvases, timed
media and metadata. Image, canvas, rendering, annotation and service URLs
are never fetched, nor are rights fields treated as licence clearance.

Existing owner/tenant consent, robots, DNS/socket admission, host pacing,
byte/request reservation, URL trap policy and snapshot replay remain
authoritative. New parser source identities bind into the canonical runtime
implementation digest. Malformed sources consume their metered attempts
but cannot publish fabricated evidence.

Source-only CI compiles all five modules and runs direct negative tests,
cross-host isolation, current source-rights checks and real canonical
CrawlRun.run_slice capture/replay tests for each protocol.

This is not live remote archive, license, distributed Mongo, device,
release, independent historical authentication or launch qualification.
