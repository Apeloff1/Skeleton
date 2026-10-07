# Consolidation provenance

The canonical machine-readable inventory is
`docs/lineage/consolidation-manifest.v1.json`. It is intentionally separate
from narrative promotion notes: CI must be able to decide whether a component
is release-eligible without interpreting prose.

## Status model

Every curated consolidation source is pinned to an exact Git revision. Component
records then move through a small lifecycle:

- `candidate`: inventoried or characterized, but not authoritative in Skeleton;
- `canonical`: promoted into Skeleton and release-eligible;
- `rejected`: explicitly evaluated and not promoted.

A candidate destination is a plan, not proof that the destination already
exists. Changing `canonical_status` to `canonical` is the release boundary and
therefore activates stricter validation.

## Canonical promotion requirements

`python scripts/check_provenance_manifest.py` fails unless every canonical
component has all of the following:

1. a declared source repository pinned to a 40-character Git revision;
2. an exact source path and Git blob SHA;
3. an explicit license/ownership decision;
4. `maturity: promoted` and `test_status: passing`;
5. a unique destination that exists in the current checkout; and
6. at least one evidence/test path that also exists in the checkout.

This makes the manifest a two-way consistency boundary: provenance cannot claim
a canonical destination that is absent, and a promotion PR cannot become
release-eligible by leaving source/license/test metadata unresolved.

## Licensing

Do not invent SPDX identifiers. Sources controlled by the same repository owner
may use:

```json
{"status": "owner-controlled", "spdx": null}
```

Third-party content must use an explicit SPDX identifier before a canonical
promotion is accepted. `unknown` and `unlicensed` may be used while inventorying
or rejecting material, but they are blocked at the canonical/release boundary.

## Promotion workflow

When promoting a candidate:

1. select the exact source commit and source file;
2. record the source file's Git blob SHA;
3. confirm ownership/license status;
4. implement the destination without importing generated caches or secrets;
5. add deterministic tests/evidence;
6. change the component to `maturity: promoted`, `test_status: passing`, and
   `canonical_status: canonical`; and
7. run `python scripts/check_provenance_manifest.py` locally before opening the
   pull request.

The `Provenance Policy` workflow runs the validator and its regression suite on
every pull request and push to `main`, rather than only when the manifest itself
changes. This prevents a code-only change from silently invalidating a recorded
canonical destination or evidence path.

## Inventory scope

Version 1 seeds the curated source set already identified by the frontier
consolidation work: Prood, Tutolage, gameforge-rs, gameforge-middleware,
hyperforge-cockpit-sota, Lorebuffa, and Openworld. Their recorded revisions are
snapshots, not floating branch names. Additional source repositories must be
added explicitly before components from them can become canonical.

The large frontier promotion branch may maintain richer wave-specific lineage
notes and source-blob comparisons. Those notes can be reconciled into this
registry as individual promotions become canonical on `main`; draft-only code is
not mislabeled as already promoted.
