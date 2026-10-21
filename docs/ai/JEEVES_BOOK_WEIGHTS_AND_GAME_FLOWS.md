# Jeeves standalone game-creation interaction and full-book candidate weights

Jeeves remains the first-party standalone model. Audio, video, images, scene frames, and 3D assets are scoped augmentations and evidence, not substitutes for its model. Neither an API provider nor a second inference/runtime root is introduced.

## Native conversational forges

The existing Jeeves ToolRegistry now exposes three read-only tools: game_creation_catalog, game_creation_questions, game_creation_compose. Its 30 facets each ask three questions and cover story, world, NPC, dialogue, levels, physics, forges, visual art, environment, music, UI, game runtime, target consoles, QA, release, and training. The model returns hash-bound answer receipts and a canonical B014 creator plan, never implicit execution.

Actual execution is delegated to already registered host creator handlers via CreatorRunbookRunner and CreatorRunbookStore. Each step needs a fresh ToolGrant, exact-command host authorization, durable pre-effect persistence, and a verified completed CreatorCommandReceipt. In-doubt work is reconciled rather than automatically replayed. verify_receipts reports a chained command/receipt hash and does not claim shipped-game quality. The UI and host must install relevant engine-specific handlers to make every facet executable; uninstalled forges are not marked ready.

Multimodal assets are references with exact modality, SHA-256 content, source ID and rights-review ID. Existing asset owners retain binary custody, decoding, revocation and permissions.

## Full books for the real Jeeves weights pipeline

Use only approved full chapter text from works the operator may lawfully use for model training. A book document with schema_version skeleton.jeeves.book_weight_intake.v1 includes a books array, each containing book_id, title, rights, review, and chapters. A chapter has chapter_id, family (one of mechanics, narrative, npc, world, economy, tooling, accessibility or review) and full text.

The book rights object follows skeleton.jeeves.game_corpus_rights.v1 and includes training_permitted true, source_kind original_authoring / licensed_training / public_domain, rights_holder, rights_basis and review_id. A real human quality review has reviewer_id, quality_approved true and an actionable note of at least 24 characters.

The book compiler partitions every source chapter into ordered contiguous spans (no source text omitted), emits a hash-pinned JSONL reviewed game-design intake plus a full offset/hash-chain coverage receipt. Nothing is fetched from the internet and no books are packaged with Skeleton. Excerpts are candidate training rows, not proof of learned competence.

Run, after independently hashing and approving all books:

1. python -m skeleton.ai.training.jeeves_book_curriculum --source /private/books.json --expected-sha256 SHA256 --intake /private/book-intake.jsonl --coverage /private/book-receipts.json
2. python -m skeleton.ai.training.jeeves_game_corpus_builder --intake /private/book-intake.jsonl --output-dir /private/datasets --prefix rights-reviewed-books --partition-seed independently-chosen-20261021 --rights-review-id human-review-id
3. python -m skeleton.ai.training.jeeves_production_game_train --checkpoint /private/jeeves-serving-checkpoint.json --expected-sha256 SERVING_CHECKPOINT_SHA256 --candidate /private/jeeves-candidate.json --report /private/candidate-eval.json --dataset-manifest /private/datasets/rights-reviewed-books-manifest.json

The canonical dataset builder and loader enforce SHA pinning, per-source project-disjoint train/eval splits, contamination scans, and independent-family coverage of all eight domains. Training is candidate-only; model serving weights require separate genuine evaluation, quality review, promotion authorization and rollback proof. Large book collections must be split into manageable complete-volume batches. No benchmark contamination or redistribution of restricted books.

## Explicit nonclaims and readiness

Creating records does not train tensors. Training was not run for this code change: authorized books, the actual serving checkpoint, compute, and independent rights approvals are external prerequisites. No complete engine compatibility, full studio automation, book ingestion, or end-to-end game release is claimed absent actual execution receipts.
