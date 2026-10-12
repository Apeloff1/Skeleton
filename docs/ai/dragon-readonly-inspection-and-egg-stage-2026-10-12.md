Dragon research hardening: read-only inspections, stable snapshots, honest egg-stage progress
Authored 2026-10-12 UTC | PR #3605 | feat/dragon-wisdom-review-20261010

Milestone 1: SQLite-enforced read-only knowledge storage

ReviewedKnowledgeStore gains opt-in read_only=True. It requires an existing absolute non-symlink path, opens SQLite with URI mode=ro and PRAGMA query_only=ON, and does not set journal mode. Existing write clients retain the default writable behavior. The browser's three-hatchling projection now uses this mode. Downstream CREATE ... IF NOT EXISTS preflight statements succeed only for already-migrated schema, and fail closed on missing tables or indexes. No GET may create an empty knowledge vault.

Milestone 2: Request-scoped stable observation

DragonResearchSessionFactory opens BOTH the reviewed-knowledge file and signed nest database in mode=ro/query_only. It constructs canonical custody verifiers against pre-existing schemas, then begins and primes a read transaction per file, yielding only after both snapshots exist. Both transactions roll back in the finally path and both handles close. These are two separate SQLite snapshots, NOT a cross-file atomic transaction; evidence digests and review constraints remain necessary.

Backend regression tests assert actual SQLite mutation refusal (CREATE and DELETE against existing tables), absence of schema auto-migration, tenant isolation, missing configuration, and that a concurrent legitimate SQLite writer cannot alter the contents of an in-flight read snapshot. A subsequent new request is allowed to observe the committed information.

Operator migration: create the reviewed-knowledge, almanac, source-catalog, capture, update-delta, video-transcript and independent signed-nest tables/indexes in the trusted migration/worker control plane BEFORE enabling the dashboard. SKL_DRAGON_RESEARCH_DASHBOARD_ENABLED=1 is an explicit operator opt-in. The web app must not install keys, auto-download sources or invent progress.

Milestone 3: First-time mother Dragon and all three hatchlings

DragonThreeHatchlingCoordinator.status no longer mistakes a genuinely absent signed-nest snapshot for damaged custody. A new account sees mother_stage=not_initialized, mother_level=null, and three locked children with level=0 and zero accepted evidence. No event is minted. An EXISTING invalid/MAC-tampered signed nest still fails closed through DragonNestStore.read. The update is covered by tests that keep source research pending and verify no XP or neural weights are approved.

Limitations: Authored tests require exact-head CI evidence before any claim of passing. The previously visible run contained only CodeQL Analyze(actions), not the Python or frontend suites. No live source was crawled, no external rights were issued, and no AI weights were changed.

2026-10-12 UTC improvement record:
(Read-only research GET can no longer write schemas or content.)
(Concurrent worker changes cannot mutate an in-flight request's SQLite snapshot.)
(New players get a truthful locked egg-stage Dragon rather than a spurious error.)
(Existing signed companion progress remains separately authenticated and tenant-scoped.)