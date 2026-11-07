# Wave 27 — OpenAPI dependency topology and operation risk boundaries

The canonical JSON OpenAPI 3 extractor now computes a real bounded
operation and local schema dependency graph in addition to its previous
path/method/status summary.

The parser walks finite local schema property/combinator and response
descriptors, counts local/unresolved/remote references, and uses exact
SCC-aware dependency graph algorithms to flag cycle membership, longest
condensed schema chains and reverse impact. It observes declared security
requirements without interpreting them as an authorization grant.

Request bodies, API servers, auth secrets, arbitrary examples, remote
schema references, dynamic code and source scripts are never executed,
fetched or projected. API traversal remains subject to the existing
separately admitted GET-only pagination contract and policy/robots
checks. This structural graph cannot authorize any API operation.

Direct adversarial tests cover cycles, missing/external references,
schema depth, source privacy, finite response/media maps and
determinism. An actual scripted canonical CrawlRun captures the
graph as unreviewed evidence and proves no extra network requests,
immutable request/byte accounting and exact snapshot replay.

No device, live network, external API call, compiler, persistent
distributed Mongo or release qualification is asserted.
