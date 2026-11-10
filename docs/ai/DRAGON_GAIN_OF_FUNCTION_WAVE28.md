# Wave 28 — Source-bounded HTTP freshness and provenance

The existing canonical CrawlRun now projects finite ETag hashes,
Last-Modified/Date/Expires, Cache-Control directives, Age,
Content-Language and Vary dimensions into typed source provenance.
ETags are SHA256-hashed instead of retained because validators can
contain opaque identifiers. Unsupported or malformed headers cannot
issue requests, renew consent or relax any source-use policy.

A site response with Cache-Control no-store now explicitly forbids
retaining its source text in canonical Mongo custody, while ordinary
scoped link-follow decisions still require all original robots, host,
DNS/socket, request budget and consent checks. Cache-Control no-cache
blocks optimistic freshness advice. A bounded due-time is *advisory*
only: no conditional GET, silent recrawl or background scheduler
is introduced. There are no new HTTP methods or credentials.

Snapshot reopen validates the typed optional freshness receipt,
and its code is included in the runtime implementation hash.
The source-only suite tests duplicate/malformed header refusal,
privacy-safe ETag hashing, no-store precedence, bounded dates,
validator tampering, real metered source capture and exact replay.

Live HTTP, distributed leases, actual cache revalidation, device
qualification and merge/release signoff remain separately held.
