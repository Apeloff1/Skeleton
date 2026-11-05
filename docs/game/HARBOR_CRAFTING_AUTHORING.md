# Lantern Quay — transactional authored-world editor

The original world source can be modified through a deterministic, typed,
allowlisted editor without executing scripts. The editor takes an expected
source SHA-256 digest as an optimistic lease, a bounded JSON operation list,
and emits an independently replay-verifiable revision containing both
the original source and the new source. Changes are transactional: any
invalid operation, collision, blocked resource, unreachable dock or stale
lease rejects the entire edit and prints no success artifact.

Supported operations: stock (id, quantity), merchant_price (price),
max_ticks (value), move_resource (id, at), tile (at, tile), recipe
(id, inputs, output) and delivery (item, quantity). The editor rejects
duplicate targets, unknown fields, invalid quantities, no-op revisions,
closed-perimeter violations and disconnected resources. It is intentionally
not a general-purpose code executor or binary asset importer.

Example edits.json:

    [{"op":"merchant_price","price":1},{"op":"stock","id":"wood","quantity":3}]

Author a new revision, substituting the current source digest:

    python -m scripts.game.harbor_crafting author --edits edits.json --expected-source-digest DIGEST > revision.json

Verify source-to-source edit replay:

    python -m scripts.game.harbor_crafting verify-author --revision revision.json

The verified revision JSON contains the edited source; extract the source
object to a JSON file and use --source to play the edited game. The revision
digest provides deterministic integrity checking, not a publisher signature
or distributed authorization. No graphical editor/device qualification is
claimed.

Focused acceptance:

    pytest -q skeleton/testing/test_harbor_crafting_authoring.py
