# Frontend dependency status — 2026-10-25

Observed 2026-10-25 06:37–06:42 UTC using the public npm registry and GitHub
Advisory API through the configured proxy with TLS verification enabled.
This review did not change packages, the lockfile, security gates or images.

The current static dependency gate remains **failed**. There is no published
patched `node-forge` release. The previously reported `braces` advisory has
officially been withdrawn, so it must not be described as an active advisory.
An additional installed-dependency mitigation check fails for
`http-cache-semantics`; that failure remains separate from package-version
advisory matching and from deployed application exposure.

## Current versions and official advisory status

| Package | Frozen Yarn lock | npm `latest` observed | Official GitHub advisory status |
| --- | --- | --- | --- |
| `braces` | `3.0.3` | `3.0.3` | [GHSA-vfj7-8cjw-p6xm / CVE-2026-93687](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), withdrawn **2026-10-23T12:53:02Z**. GitHub states it is “not a practically exploitable vulnerability.” Historical range `<=3.0.3`; no first patched version. |
| `node-forge` | `1.4.0` | `1.4.0` | [GHSA-86w9-cpqp-85rv / CVE-2026-85393](https://github.com/advisories/GHSA-86w9-cpqp-85rv), **active high**, CVSS 7.5. Affected `<=1.4.0`; `first_patched_version` is null. |
| `sprintf-js` | `1.0.3` | `1.1.3` | [GHSA-hp3w-g68c-fv3c / CVE-2026-97058](https://github.com/advisories/GHSA-hp3w-g68c-fv3c), withdrawn **2026-10-22T19:21:04Z**. GitHub states applications are responsible for handling exceptions appropriately. Historical range `<=1.1.3`; no first patched version. |
| `http-cache-semantics` | `4.3.0` | `4.3.0` | [GHSA-ch52-4w7c-c8xp / CVE-2026-93748](https://github.com/advisories/GHSA-ch52-4w7c-c8xp), **active high**. Published metadata lists `<=4.2.0`, with no first patched version. Locked `4.3.0` is outside that stated range, but fails the repository's existing max-stale behavior check below. |

Registry sources: [braces](https://registry.npmjs.org/braces),
[node-forge](https://registry.npmjs.org/node-forge),
[sprintf-js](https://registry.npmjs.org/sprintf-js), and
[http-cache-semantics](https://registry.npmjs.org/http-cache-semantics/latest).
No later stable `braces` or `node-forge` version was present in the observed
registry version lists. A release bump to `sprintf-js@1.1.3` would not represent
a published security fix for the withdrawn advisory.

Upgrading the framework is not an established remedy for the active forge
advisory: observed latest [`@expo/cli@58.1.15`](https://registry.npmjs.org/%40expo%2Fcli/latest)
still depends on `node-forge@^1.4.0`, as does observed latest
[`@expo/code-signing-certificates@0.0.7`](https://registry.npmjs.org/%40expo%2Fcode-signing-certificates/latest).
Observed latest [`micromatch@4.0.8`](https://registry.npmjs.org/micromatch/latest)
still depends on `braces@^3.0.3`.

## Declared gates and observed mitigation checks

`node frontend/scripts/audit-known-yarn-advisories.cjs` exits **1**, with
`release_accepted: false` and outstanding packages `braces` and `node-forge`.
The offline policy has an **October 16** snapshot and no withdrawal state; it
continues to classify the withdrawn braces advisory as `unpatched_affected`.
Refreshing that stale advisory state requires an explicit evidence-backed
policy review. This review did not dismiss alerts or change the gate.

The same static policy classifies `http-cache-semantics@4.3.0` as patched using
a hard-coded `>=4.2.1` threshold. The current official advisory metadata does
not publish that first-fixed-version claim.

Read-only checks against the existing `/workspace/Skeleton/frontend/node_modules`
installation produced these results:

| Existing check | Observed result |
| --- | --- |
| `verifyBracesDepthGuard()` | Passed: the existing local depth mitigation remains applied. |
| `verifyNodeForgeNestedDigestAlgorithmGuard()` | Passed: the malformed nested DigestAlgorithm fixture was rejected and the source guard was present. |
| `verifyHttpCacheMaxStaleGuard()` | **Failed**: `http-cache-semantics@4.3.0` reused the security-zeroed response through `max-stale`. |
| Complete `verify-no-release-npm-security.js` | **Exit 1**, stopping at the cache check before its forge check. The guards were then executed individually without modifying their definitions. |

The source inconsistency is specific:
`frontend/scripts/patch-node-modules.js` returns early for cache version
`4.3.0` as supposedly already patched, while its following exact-version
allowlist and existing `this.maxAge() > 0` mitigation still support that same
version and source shape. Installed `4.3.0` retains the unguarded
`if (allowsStaleWithoutRevalidation)` branch. Consequently the existing
compensating-control verifier cannot currently be reported as successful.
This observation does not extend GitHub's published affected-version range
or establish exposure in the installed application.

The existing postinstall patches do not change package versions and do not
clear the version gate. Future unreviewed versions are deliberately rejected
by the patch hook. A successful frontend export also does not prove these
security checks passed: the Docker dependency stage applies the patch hook,
but does not execute this complete verifier.

## Dependency paths and runtime exposure limits

Representative frozen-lock paths are:

- `@expo/cli@54.0.27 -> node-forge@1.4.0`.
- `@expo/cli@54.0.27 -> @expo/code-signing-certificates@0.0.6 -> node-forge@1.4.0`.
- `@expo/cli@54.0.27 -> @expo/metro@54.2.0 -> metro-file-map@0.83.8 -> micromatch@4.0.8 -> braces@3.0.3`.
- `react-native@0.81.5 -> babel-jest@29.7.0 -> @jest/transform@29.7.0 -> micromatch@4.0.8 -> braces@3.0.3`.
- `@expo/cli@54.0.27 -> @expo/xcpretty@4.4.7 -> js-yaml@3.15.2 -> argparse@1.0.10 -> sprintf-js@1.0.3`.

`@expo/cli` is declared in regular dependencies, so calling every affected
package a manifest-level development-only dependency would be inaccurate.
The inspected actual forge imports are in Expo CLI iOS signing and Expo
code-signing-certificate code. No direct imports of `node-forge`, `braces` or
`sprintf-js` were found in `frontend/app`, `frontend/src` or `frontend/index.js`.

The production frontend Docker stage runs Nginx and copies only the exported
`dist` assets and Nginx configuration; it does not copy the build stage's
`node_modules`. That separates Node build/development-tool exposure from the
Nginx serving process. It does **not** prove that no package-derived JavaScript
was bundled, or certify the installed image. This review did not inspect an
exact newly built browser bundle, runtime SBOM, installed image, or adversarial
application request path. No remote production exploitability claim follows
from dependency presence alone.

## GitHub alert visibility

The push notice reports three Dependabot alerts, two high and one moderate.
`GET /repos/Apeloff1/Skeleton/dependabot/alerts?state=open&per_page=100` returned
**403: Resource not accessible by integration**. Repository metadata access
does not grant security-alert access, and the available connector supplies no
Dependabot alert endpoint.

The exact three active alert identities, dependency scopes and affected refs
therefore remain **unobserved**. The push counts must not be assigned to the
packages above by inference, especially because two historical advisories have
now been withdrawn. No alert was dismissed or suppressed.

## Minimal remediation and release assessment

1. No package or lock bump currently closes the active `node-forge` advisory.
   Retain and verify the reviewed local mitigation, and leave published-version
   qualification unresolved until an independently reviewed published fix or
   a verified removal of every forge dependency path exists. A major Expo
   upgrade alone is not such a removal.
2. Review the official braces withdrawal and update the stale October 16
   policy's advisory state explicitly in a coordinated follow-up. Retain the
   defensive depth guard. This is a withdrawal-state correction, not a claim
   that `braces@3.0.3` received a new security release.
3. Before claiming the compensating-control gate passes, resolve the cache
   verifier inconsistency. The smallest source candidate is to remove the
   `4.3.0` early skip and apply the already present exact-version max-stale
   guard, followed by its behavior regression and full verifier. This review
   made no such change; frontend sources were frozen for the pending build.
4. An account or integration with Dependabot-alert read permission must identify
   the three reported alerts before their closure can be assessed. Public
   advisory metadata cannot substitute for that repository-specific inventory.

Functional build/testing can proceed with the current frozen inputs, but this
evidence does **not** support a clean dependency-security or enterprise
production-readiness claim. The active forge advisory, failed cache mitigation
check, stale withdrawal policy and unavailable repository alert inventory are
specific outstanding qualification items.

## Evidence identity

Reviewed integration checkout: `e82ea07c056e05cc81125667234b28a399870a30`.
The primary and integration copies of package, lock, static gate and Dockerfile
were byte-identical at observation. Frozen `frontend/yarn.lock` SHA-256:
`b9e1a6e64933b417be9d72b621dfb01d567d2370afedf76337de45cc809f5a48`.

Sanitized local evidence is retained under
`/workspace/scratch/consumer-readiness-2026-10-22/dependency-review-20261025/`:
registry metadata, official advisory metadata, dependency paths, current gate
output and isolated mitigation results. The separate
`dependabot-read-access-limit.json` and `.md` record the API permission limit.
These local evidence paths are session artifacts; official URLs above are the
portable external references. No credentials were captured in the evidence.
