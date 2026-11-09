# Frontend dependency review — 2026-10-28

This is a dated lockfile and source review, not a consumer-security or release
certification. The earlier [October 25 report](DEPENDENCY_STATUS_2026-10-25.md)
retains the observations available at that time.

Official npm and GitHub advisory endpoints were queried through the configured
proxy with TLS verification. An npm bulk advisory query covered all 931 unique
package identities parsed from the Yarn v1 lock. Before the change it reported
three high and two moderate advisories affecting `undici@6.28.1`. The locked
Expo CLI requires `undici@^6.18.2`; the reviewed resolution is now `6.29.1`,
within that range. Both versions require Node 18.17 or newer, and the frontend
image uses Node 24. The actual npm 6.29.1 tarball was downloaded independently:
its 297,796 bytes, SHA-1 and SHA-512 integrity matched the public registry and
the updated lockfile. No dependency install was performed for this review.

GitHub lists `6.29.1` as the first fixed 6.x version for
[GHSA-xjj6-f33q-929c](https://github.com/advisories/GHSA-xjj6-f33q-929c),
[GHSA-2m5v-pch6-74hx](https://github.com/advisories/GHSA-2m5v-pch6-74hx),
[GHSA-qrxm-fqhp-jwvm](https://github.com/advisories/GHSA-qrxm-fqhp-jwvm),
[GHSA-4qv8-2p9j-2685](https://github.com/advisories/GHSA-4qv8-2p9j-2685) and
[GHSA-9fm3-97px-rjf6](https://github.com/advisories/GHSA-9fm3-97px-rjf6).
The follow-up npm bulk query against the updated lock returned no high or
critical findings and one low finding. This query is one source of evidence;
it does not establish the status of every GitHub repository alert or image.

The remaining low finding is [GHSA-gcqx-w48m-w2h4](https://github.com/advisories/GHSA-gcqx-w48m-w2h4):
`deepmerge@4.3.1`, pulled by `@expo/config@12.0.14`, can poison the prototype of
returned objects. The official range is `>=4.2.0, <=4.3.1`, with no published
first-patched version. A version- and shape-bound postinstall guard rejects an
own enumerable `__proto__` key in both merge inputs for all three published
4.3.1 entrypoints. Rejecting that key is an intentional compatibility change.
Isolated tests reproduce the problem in the real package before the guard and
exercise the guard, normal object/array/symbol behavior, idempotence, version
drift and partial states afterward. The Docker dependency stage runs the guard
and verifies the installed compiled distributions before building the frontend.
The observed Expo config call sites use default merge options; custom merge or
clone options, already-poisoned inputs and downstream copying are not globally
certified. The advisory remains open and the known-advisory gate remains blocked.

The same refresh records that
[GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
for braces was withdrawn on October 23. GitHub lists active affected ranges
`<=1.4.0` for [node-forge GHSA-86w9-cpqp-85rv](https://github.com/advisories/GHSA-86w9-cpqp-85rv)
and `<=4.2.0` for [http-cache-semantics GHSA-ch52-4w7c-c8xp](https://github.com/advisories/GHSA-ch52-4w7c-c8xp),
with `first_patched_version: null` for both. The exact locked `1.4.2` and
`4.3.0` versions are recorded as outside those published ranges, not labeled
as published fixes. Unreviewed versions still require advisory reverification;
mixed affected/unaffected locks remain blocked. Other advisories and live Yarn
audit records are not automatically dismissed by this scoped snapshot.

The existing VM's `frontend/node_modules` still has `undici@6.28.1`,
`node-forge@1.4.0` and an unpatched deepmerge. The new verifier therefore fails
there as intended. A fresh frozen dependency installation and production image
build are required to establish the new installed state. The actual browser
bundle, any native Windows installation, and the repository's separate
Dependabot alert inventory have not been fully qualified by this review.
