# Frontend dependency review — 2026-10-28

## 2026-11-09 refresh

A current Yarn v1 lock query covered 1,015 entries and 931 package names. It
found two high-severity advisories with compatible patched releases:
`decode-uri-component@0.5.0` (GHSA-qr28-fpjm-wq7f) and
`follow-redirects@1.16.1` (GHSA-mrwp-f3q8-3g9p). The lock and resolutions now
select `0.5.1` and `1.16.2` respectively, using registry-published integrity
values. The redirect package remains inside Axios's declared range. The decoder
is on the application navigation path through `expo-router -> query-string`.

`query-string@7.1.3` loads the decoder with CommonJS `require`, while both the
old and patched decoder releases expose an ESM default function. The unpatched
interop caused ordinary route parsing to throw. The postinstall hook now binds
the exact reviewed query-string and decoder versions and source hashes, selects
the default export, verifies ordinary and malformed route decoding, and refuses
unknown package shapes. A fresh frozen install exercises this hook; reusing an
old `node_modules` tree does not establish the corrected state.

Three findings remain explicit. `glob@13.0.6` requires the incompatible 14.x
line for its published fix, locked `minimatch` 3.x/9.x/10.x copies require 11.x,
and `deepmerge@4.3.1` has no published patched release. Glob and minimatch were
observed principally in build/lint tooling and are not copied as Node packages
into the exported Nginx image, but the browser bundle has not been proven free
of every affected path. The existing version- and shape-bound deepmerge guard
remains in place. These findings are retained by the offline advisory gate;
there is no blanket resolution override or alert dismissal.

The repository's exact Windows installer and Linux local-inference workflows
must run again after this lock change. This review does not qualify the tester's
Windows/WSL2/Docker environment or operating-system image packages.

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
