# Replay-authoritative Lantern Quay journals

The Studio B journal is a portable, bounded, immutable history of gameplay
continuations. It starts from a canonical source-bound save bundle, appends
only legal actions with a compare-and-swap journal digest, and reconstructs
the playable head by replaying every transition. Each revision has a digest
chain, resulting save digest and terminal digest. Neither the journal's outer
digest nor a revision digest is a signature, authentication credential or
proof that an untrusted author has permission to publish content.

From a valid existing save bundle, run:

    python -m scripts.game.harbor_crafting journal-init --bundle save.json > journal.json
    python -m scripts.game.harbor_crafting journal-verify --journal journal.json
    python -m scripts.game.harbor_crafting journal-append --journal journal.json --actions actions.json --expected-journal-digest DIGEST > next.json
    python -m scripts.game.harbor_crafting journal-export --journal next.json > replay-save.json
    python -m scripts.game.harbor_crafting journal-audit --journal next.json
    python -m scripts.game.harbor_crafting journal-rewind --journal next.json --revision-index 0 --expected-journal-digest DIGEST > root-journal.json

The caller must atomically persist the returned bytes. CLI commands write
only to stdout, never overwrite input files and never claim crash-safe disk
publication. For concurrent writers, the storage layer must also enforce an
atomic expected-digest compare-and-swap; a digest comparison in a standalone
CLI process is not a distributed lock.

Limits: 32 revisions, 128 actions per revision, 1024 world ticks and a
512 KiB journal. A revision is validated in full before it is returned.
Rewind returns a new verified history prefix and does not mutate the old
journal. Completed campaigns reject further actions. The replayed save can
be passed to existing mission, NPC, economy and portable package tools.

The journal verifier rejects duplicate/unknown fields, invalid action
shapes, stale leases, changed source, altered historical events, mismatched
revision order, forged terminal states and oversized input. Hashes provide
integrity against accidental or untrusted changes only when the expected
digest comes from an independently trusted source; they do not provide
authenticity against an adversary who can replace all bytes and expectations.
