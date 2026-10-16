# Frontend dependency security custody — 2026-10-16

This report is for active security issue #2457. It is not an exception,
Dependabot dismissal, or declaration that the installed frontend is safe.

The Yarn v1 lockfile was checked against the following **fixed advisory
identities**, not a complete vulnerability-database feed:

| Package | Lockfile | Advisory | State |
|---|---|---|---|
| `image-size` | Not installed | GHSA-5p2g-fcmc-qvqq, GHSA-w3rx-r6r6-pgpr | No lockfile exposure |
| `brace-expansion` | 1.1.21 / 2.1.7 / 5.0.12 | GHSA-q2hr-2g5m-vwhr | Patched per installed major |
| `decode-uri-component` | 0.5.0 | GHSA-vcc3-ghjq-m6fr | Patched |
| `http-cache-semantics` | 4.3.0 | GHSA-ch52-4w7c-c8xp | Above affected range |
| `braces` | 3.0.3 | GHSA-vfj7-8cjw-p6xm | **Unpatched, open** |
| `node-forge` | 1.4.0 | GHSA-86w9-cpqp-85rv | **Unpatched, open** |

As of October 16, GitHub's reviewed advisories list **no patched versions**
for `braces` or `node-forge`; do not fabricate overrides to unavailable
versions or dismiss their findings. The lockfile records `braces` beneath
`micromatch@4.0.8`, and `node-forge` beneath Expo CLI and
`@expo/code-signing-certificates@0.0.6`. These are dependency graph
relationships, **not** proof that vulnerable code is or is not packaged in a
mobile release. Review actual packaged artifacts, invocation pathways,
build-service exposure and potential untrusted regex/signature inputs before
any scoped risk decision. No risk exception is authorized by this report.

## Repeatable offline report

```bash
cd frontend
yarn test:known-advisories
yarn audit:known-advisories:report    # produces JSON, status 0 for reporting
yarn audit:known-advisories           # status 1 until all tracked alerts clear
```

The script fails closed for malformed, ambiguous or conflicting lockfile
stanzas and keeps each declared dependency parent. It reports only the six
known identities above. The strict command exits unsuccessfully for
unpatched/advisory-unverified versions. It does **not** contact the npm registry
or GitHub's Dependabot API, inspect platform output bundles, or replace a
full `yarn audit` / SBOM / container scan. Report-only status is never a
passed security gate.

## Release-blocking next steps

1. Obtain the complete current Dependabot alert list, including older alerts
   omitted from the historical connector report.
2. Run native-web/mobile dependency reachability and signed release-output
   inventories. Determine whether `node-forge` signature verification or
   `braces` pattern parsing can receive untrusted input; keep findings open.
3. When **actual patched compatible packages** are published, change
   resolutions if needed, regenerate `frontend/yarn.lock` with Yarn classic,
   and rerun CI, dependency review, and the full platform release suite.
4. Keep the advisory identifiers visible throughout; never mark automatic
   patching complete because the lockfile parser ran.

References: https://github.com/advisories/GHSA-vfj7-8cjw-p6xm and
https://github.com/advisories/GHSA-86w9-cpqp-85rv.
