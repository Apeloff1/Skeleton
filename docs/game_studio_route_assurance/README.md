# Forge Studio source-route assurance — operation guide

**Status:** functional deterministic source replay, candidate evidence only. This
feature does **not** certify native Godot control, shipped builds, playable
game completion, copyrighted-source provenance, asset licensing, or live device
latency. It is a user-accessible part of the canonical game-learning Studio,
not a competing project editor or persistence service.

## Authoritative service and contract (L00–L03)

- **Owner:** `skeleton/forge/game_frontier_studio_route_assurance.py`
  reads existing `StudioProject` and calls the canonical
  `skeleton/forge/game_frontier_studio_tile_navigation.py` traversability
  predicate. Do not introduce an independent map collision policy.
- **Authorized API:** `POST /api/game-frontier-authoring/projects/{project_id}/routes/audit`.
  The existing auth identity and tenant-scoped game-learning workspace resolve
  project ownership, read its source revision, and return a read-only report.
- **Schema:** `skeleton.forge.route_playthrough_assurance.v1`; exactly one
  source layer plus two in-bounds tile coordinates per scenario. Input is
  restricted to `scenario_id`, `layer`, `start`, `goal`, and
  `require_alternate`.
- **Budget:** 1–100 scenarios per request; each layer at most 256×256; IDs up
  to 64 safe characters; witness coordinates capped at 256 per path, while
  the path digest always binds the *entire* actual route.
- **Authority:** audit is a read operation. Game source revisions remain
  exclusively owned by `workspace.save_editor`, with host version/CAS.

## Runtime and state (L04–L05)

Use an authenticated editor or reader session with access to the existing
project. Example JSON body:

```json
{
  "scenarios": [
    {
      "scenario_id": "VillageToHarbor",
      "layer": "ground",
      "start": [2, 3],
      "goal": [15, 3],
      "require_alternate": true
    },
    {
      "scenario_id": "VillageToCitadel",
      "layer": "ground",
      "start": [2, 3],
      "goal": [12, 10],
      "require_alternate": false
    }
  ]
}
```

Coordinates refer to *authored tile positions*, not GPS or world longitude.
Each scenario is resolved by four-way grid movement on source passable cells.
A primary shortest path is recorded by deterministic BFS, with SHA-256 over the
complete coordinate sequence, step count and bounded beginning/end samples.
If redundancy is required, the replay computes a second path that avoids
every internal tile of the primary route. Thus a one-tile bridge may be
reachable but fail the alternate-route requirement. This conservative witness
may reject a graph where a different primary could have yielded an alternate;
it is not a maximum-flow algorithm.

Report status includes source layer digest, project manifest SHA-256, counted
successful/failed scenarios, specific failure reasons, and an integrity
receipt. The API reruns the report against the current project before returning
a positive `verified_against_authoritative_source` annotation. The raw
`receipt_sha256` hashes the deterministic report: it is **not** a
cryptographic signature or evidence of device execution. The API's
`source_version` is intentionally not included in the portable route receipt.

## Security, failure, and recovery (L06–L07)

Inputs containing unknown keys, duplicate IDs, noninteger/bool coordinates,
out-of-bounds cells, unknown layers, empty requests, oversized request counts
or unmapped source tiles fail closed. No arbitrary expressions, scripts,
filesystem paths, callbacks or provider instructions are accepted. Project
state cannot be mutated by a route audit. An auth denial or workspace read
failure leaves the authoritative project untouched.

When a route is inaccessible, inspect the source palette and map geometry
first. `water`, `lava`, `wall`, `pit` and other blocked surfaces are
not turned into invented teleport edges. When a two-route witness fails,
improve the actual authored road network and rerun the audit on a new revision.
To roll back, restore the previous canonical source revision through existing
workspace controls; no migration or alternative state database is required.

## Evidence and capacity (L08–L10)

Each scenario returns `primary` and optional `alternate` evidence with
actual source coordinate path SHA-256, movement steps, truncation indicator,
and an explicit failure code. Response paths never include more than 256
coordinates per witness, even for a 65,536-cell map. Worst-case reference
traversal is proportional to `100 × cells` on the selected layers, bounded
by existing 256×256 layer admission. No external inference, hosted API bill
or remote tool invocation is involved.

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. python -m pytest -q --noconftest skeleton/testing/test_game_frontier_studio_route_assurance.py
```

Coverage includes split and blocked bridges, route topology changes,
deterministic SHA receipts, source document roundtrips, false approval
claims, duplicate/forged input, 100 scenario admission and objective
before/after regression. `verify_route_playthroughs` reruns the
deterministic source traversal before accepting evidence. A report hash
alone is never treated as authoritative; the comparison helper only checks
report integrity and exact scenario comparability.

## Deployment, controls, and exit (L11–L13)

This is a source-only additive feature. There is no new service, credential,
model provider, store or database schema to deploy. Old game projects remain
unchanged, and the operator can disable the endpoint without touching
game-source files. Baseline comparison is strict: a previously successful
route that disappears is counted as a regression; a new successful route
without regressions is reported as a structural improvement.

**Exit from candidate status requires separate evidence**: Godot actual boot
and full gameplay playthrough, controller traces on target hardware, story
and quest terminal reachability, six-month recovery behavior, operational SLOs,
IP/rights clearance, and independent release authorization. A numerical
increase in addressable editor combinations, source route reports, or
generated manuscripts cannot substitute for any of those.
