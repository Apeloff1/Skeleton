# Jeeves whole-repository inventory and governed actions

The existing `AppwideInventory` and `JeevesAppwideRuntime` owners let a local
operator discover an installed checkout, inspect bounded source and invoke
explicit adapters. Start with the
[capability atlas and workbench guide](JEEVES_APP_CAPABILITY_ATLAS.md) for startup,
confirmation, native-source staging and the difference between local adapters
and actual model inference. The assembled application workflow is documented
in [crawler, builder and training operations](ai/STUDIO_CRAWLER_BUILDER_TRAINING.md).

## Inventory identity and source freshness

A scan enumerates visible regular files under the selected real checkout,
classifies overlapping subsystems and reports exclusions. It does not import
those files. The traversal has hard limits of 200,000 regular files, 400,000
inspected entries and 32 directory levels. Generated/private runtime trees,
symlinks and nonregular files are not followed. Sensitive filenames are
restricted; sensitive subtrees are excluded. Binary resources need a specialized
adapter rather than the UTF-8 source reader.

The inventory's `snapshot_digest` binds its recorded paths, metadata, exclusion
records and local file freshness identities. It is **not a full-content digest**
of every file and is not portable source attestation across machines. A fresh
checkout can have a different metadata snapshot even when its source bytes match.

A source read checks the recorded file identity before opening, uses bounded
no-follow traversal where supported, checks the opened descriptor before and
after reading, then returns the actual source SHA-256. An ordinary same-size
source edit therefore cannot pass merely because its byte count stayed equal.
The recorded operator run observed a 20-byte source revision refused before
rescan and read successfully after rescan. This does not certify arbitrary
filesystem tamper resistance or the entire installed runtime.

UTF-8 source inspection is capped at 256,000 bytes. A source replacement proposal
is capped at 120,000 UTF-8 bytes and must match the exact previous SHA. Shared
JSON request limits can impose a tighter encoded bound. The result is a review
diff with source hashes; `source.propose` does not edit the checked-out app.
Current-game proposals use the separate existing workspace proposal/commit owner.

## Use the two identities correctly

The appwide catalog returns `catalog_digest`, `canonical_catalog_digest`, the
inventory identity and registered adapters with their required/optional fields.
Its catalog digest binds the appwide adapter contract to the canonical catalog.
The canonical cockpit's digest is a different value; do not substitute one for
the other.

| Identity | Use |
| --- | --- |
| Canonical atlas `catalog_digest` | Pin `/api/jeeves-app-action` with `expected_catalog_digest` |
| Appwide catalog `catalog_digest` | Pin `/api/jeeves-appwide-invoke` with `expected_catalog_digest` |
| Inventory `snapshot_digest` | Pin appwide invocation with `expected_inventory_digest`, or an inventory search with `params.expected_snapshot` |
| Source `sha256` | Supply the exact base for a source proposal |
| Invocation `digest` and `request_digest` where supplied | Identify the returned operation and its frozen request |

The catalog source identities cover explicitly listed adapter/domain-source
owners, not arbitrary transitive dependencies, loaded bytecode, the interpreter
or standard library. Catalog identity does not prove that a model is configured,
an optional pack is installed or a game passes release review.

## Loopback HTTP interface

These endpoints belong to the existing local workbench server:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/jeeves-appwide-status` | Read the current inventory report; lazily scan if absent |
| `GET /api/jeeves-appwide-status?refresh=true` | Perform a new bounded scan and publish its completed snapshot |
| `GET /api/jeeves-appwide-catalog` | Read the current appwide adapter/catalog contract |
| `POST /api/jeeves-appwide-invoke` | Invoke one registered appwide action |
| `GET /api/jeeves-app-atlas` | Read the canonical family/action atlas |
| `POST /api/jeeves-app-action` | Invoke one canonical selected-project action |

The existing session-token and exact-origin checks apply. The following examples
are request bodies, not unauthenticated endpoints or permission grants.
Use the identities returned by the running server.

A canonical settings preview uses action fields directly inside `args`:

```json
{
  "project": "original_studio",
  "action": "studio.editor.preview",
  "args": {"editor": "racing", "settings": {}},
  "expected_catalog_digest": "<canonical atlas catalog_digest>"
}
```

An appwide native-source preview keeps the selected project in the `params`
routing envelope:

```json
{
  "action": "game.compile.native",
  "params": {
    "project": "original_studio",
    "intent": {
      "title": "Original Studio Preview",
      "subtitle": "Bounded original source preview.",
      "seed": 17,
      "width": 11,
      "height": 11,
      "levels": 1,
      "collectibles_per_level": 1,
      "hazards_per_level": 1
    }
  },
  "operator_authorized": true,
  "expected_catalog_digest": "<appwide catalog catalog_digest>",
  "expected_inventory_digest": "<inventory snapshot_digest>"
}
```

The appwide owner verifies the active project, then forwards only the canonical
action arguments to its existing strict dispatcher. It removes `project` from
those arguments; this routing field must not become an unexpected field in the
compiler's `intent` contract. Native-source previews remain source generation,
not assembled binaries or emulator execution.

`operator_authorized: true` records deliberate operator intent within the
already authenticated local interface. It does not authenticate the caller,
create privileges, approve a source commit or let model output authorize itself.
Actions that require confirmation are refused without it. The workbench UI sends
the current pins and resets its confirmation after refresh, action selection
changes and successful confirmed work.

## Registered work and remaining boundaries

Inspect the live catalog for the precise supported set. The recorded 18 October
operation observed **36 appwide adapters** and **29 canonical actions**; those
numbers describe that source snapshot, not completion percentages.

The existing appwide adapters support:

- Inventory reports and paginated search; bounded static interface, impact,
  context, duplicate and evidence-gap views.
- Source inspection and exact-base review proposals, without repository writes.
- Typed editor catalogs, templates and deterministic previews.
- Finite original-world/chapter planning, current-project assembly, work orders
  and source-backed chapter context.
- Existing Forge component discovery/graph validation, original-game source
  compilation, bounded replay/mirror review and typed tool planning.
- Research-acquisition planning, installed crawler-worker discovery, Dragon
  visual-state reduction and consent-bound companion rehearsals.
- Evidence-referenced improvement proposals with separate review, evaluation,
  rollback and promotion gates.

Only listed adapters can run. A filename, public function signature, classifier
label, source hash or model suggestion cannot grant arbitrary import, shell,
network, credential, publishing or checkpoint-write authority. Native artwork
staging is exposed by the canonical `game.console.source.stage.artwork` action;
select that action in the canonical cockpit rather than assuming every canonical
action also appears in the appwide selector.

The local `system.triad` adapter performs deterministic role exercises. It does
not independently ask three models to review a game, perform a crawl, train a
transformer or prove subjective quality. Its reference-pack requirement is
separate from model readiness and is absent from default production image
source allowlists. Read the
[triad dependency and qualification notes](JEEVES_APP_CAPABILITY_ATLAS.md#understand-triad-and-model-readiness)
before invoking it from a partial installation.

## Recover from a stale or refused operation

| Observed result | Operator recovery |
| --- | --- |
| Catalog changed | Refresh the relevant cockpit, inspect current required fields and confirm the intended action again |
| Inventory/source changed | Use **Scan all app files and report coverage** for a fresh scan, then reopen/reinspect the source |
| Source SHA conflict | Review the current file and prepare a new proposal against its actual SHA; retain any existing reviewed proposal separately |
| Confirmation required | Confirm the selected bounded operation after checking its effect; a session token alone is insufficient |
| Project is not active/current | Select the intended current project through the existing workspace controls |
| Unsupported or excessive parameters | Use the current catalog's fields and the action's limits; split large source/context requests |
| Optional triad reference pack unavailable/corrupt | Supply the exact expected files and matching manifest through explicit installation configuration, then refresh; do not substitute fabricated evidence |

A rescan replaces the server's inventory only after the new scan completes.
It does not repair missing permissions, grant native toolchain compatibility,
commit a proposal or renew a previous confirmation. Unsupported action-argument
fields and invalid input remain explicit failures.

## Exact recorded evidence

The [operator qualification record](ai/evidence/enterprise-2026-10-18/studio/qualification-summary.json)
was recorded at `2026-10-18T04:46:51.677714+00:00`, using source base
`f511c704ec07816697a9df34c5fc622c02565b21` plus the five exact working-tree
source hashes listed there. Its catalog digest is
`777fa6428b3447c6d1dd8a84bbf618298a378ab9f9bb4206920eb8a3889236a2`.
It retains hashes for the public operation artifacts and distinguishes those
observations from later source revisions.

Actual browser operations exercised canonical compilation, appwide Forge
forwarding, replay/mirror review and triad execution with no page errors.
HTTP observations include a valid pinned read, stale-catalog refusal, missing
confirmation, duplicate/nonfinite JSON refusal, excessive nesting refusal and
actual native artwork source staging with all 14 supported fields. The separate
source-freshness observation retained the proposal uncommitted and recovered by
rescan. The owned loopback server was stopped after recording.

No automated test suite, native compiler/emulator or model inference ran in
this particular workbench qualification. Full-app reliability, long-duration
operation, all-console support, model improvement and enterprise superiority
require their own current-source evidence through the canonical owners.
