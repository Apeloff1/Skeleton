# Dragon Wave 23 — Public federation and historical-source navigation

Two real acquisition paths are implemented in the canonical Dragon worker.

## ActivityStreams 2 collections

The crawler now recognizes typed ActivityStreams JSON collection pages and
nominates bounded next/prev links, collection-root first pages and explicitly
public Article/Note/Document item links. Each link must remain same-origin,
even if the owner originally allowed multiple hosts. JSON-LD contexts are
syntactically validated without remote dereferencing. Actor, inbox, outbox,
followers, private DMs, replies, WebFinger, arbitrary activity scripts and
subscription endpoints are not promoted into the frontier.

The acquired collection is discovery-only rather than trusted evidence.
Its admitted links still pass the unchanged canonical consent, robots,
DNS/socket, host pacing, request/byte budget and worker lease controls.

## Explicit Memento opt-in

A new CrawlRequest.discover_mementos boolean defaults to false. When enabled,
the canonical worker may nominate only same-origin, past-dated Link
rel=memento references from already acquired source responses. Timegate,
timemap, original, remote archive host and future timestamps do not grant
traversal authority. Date headers cannot renew consent or establish
historical authenticity. All references still require a fresh canonical
worker dispatch reservation before network IO.

The original run ID binds the opt-in value and implementation source digest,
so snapshot recovery fails closed on altered policy or code. No parallel
network client, new credentials, persistent database or model authority
is introduced.

Dedicated parser and actual scripted run_slice regression suites verify
private social feed suppression, same-origin enforcement, opt-in behavior,
byte/request accounting, event isolation and snapshot replay.

Live Internet, real public federation policies, temporal archive provenance,
distributed worker/DB tests, complete repository CI, merge and launch
qualification remain independent holds.
