# Query-relevant offline evidence continuation

Implementation sign-off: Codex, 2026-10-10. Scope: PR #3597 continuation only.

## Functional change

Opt-in grounded turns now select a 220-character original-text window using
query-term coverage, rarity and surrounding context. A match near the end of a
verified chunk can now reach the model, rather than always being discarded by
prefix truncation. Unicode normalization applies only to term comparison;
character offsets, excerpt text and digests refer to the untouched source.
Full-width letters, casefold expansions and decomposed accents are exercised.

The complete original search hit is validated before narrowing. Invalid source
identities, coordinates, types and document hashes cannot be repaired implicitly
by truncation. Saved source errors retain a typed grounding envelope. Existing
v1 evidence snapshots remain valid; prior receipts are never reselected on retry,
restore, export or import. Citation recognition still proves identifiers only,
not factual support or absence of contradiction.

New session, imported-session and fork IDs have an s_ prefix before their existing
192-bit random identifier. They cannot start with a CLI option marker. Previously
saved session IDs remain accepted without migration. The real CLI regression
forces leading-dash randomness and generates a turn in all three resulting IDs.

The source/AST cache bound already repaired in PR #3605 is also applied here to
the mandatory provider validator. Full checks and compact import summaries are
preserved. The exact same shared change can merge without inventing a second
validator or dropping scan coverage.

## Construction, verification and operation

L00–L03 preserve the existing offline session, source-library and model owners;
there is no provider SDK, network acquisition, extra store or privileged context.
L04–L07 preserve original offsets, typed refusal, atomic turn evidence and replay.
L08–L09 retain bounded source chunks/hits/context and resident parser caches.
L10 uses actual SQLite, HTTP, headless native inference, backups and forks.
L11–L12 require no data migration; disable the excerpt selection to restore
prefix behavior for new turns while keeping historical snapshots immutable.
L13 still requires trained-model quality, claim-level factual verification,
installed Windows acceptance, security review and passing exact-head release CI.

Local offline grounding, search, HTTP, CLI and persistence tests pass: 78 tests
and 21 subtests. Two provider-cache regressions pass. Architecture, construction,
capability interfaces, state topology and enterprise-superiority schema pass.
The implementation-dossier validator retains the prior VOL-000.existing_evidence
staleness on this lane. The bounded provider scan and hosted CI are recorded
separately after completion. None of these checks qualifies the full AI product.
