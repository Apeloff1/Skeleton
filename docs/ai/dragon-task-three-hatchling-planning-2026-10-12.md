# Dragon task-aware three-hatchling research milestone
Authored: 2026-10-12 UTC | PR #3605

## Milestone 1: Task-focused mother-Dragon planning
DragonTaskResearchPlanner composes the canonical owner-scoped DragonResearchWorkboard with the editorial technical source atlas. It matches a bounded set of explicit user task terms and documented adjacent topics against registered source metadata. Exact lexical matches contribute a navigation signal of 12 points, adjacent topics 3, and review-ready candidates a small 2-point boost. Unchanged re-observations do not earn invented novelty. These are navigation scores, NOT model confidence or source-truth probabilities.

Every plan includes Article, Video and Updates when their sources exist, reserves one suggestion from each role, then balances later suggestions across registered hosts. Article and Updates can share a source but that source is not counted twice as independent verification. Video references without reviewed topic metadata receive no invented topical relevance.

## Milestone 2: Bounded source census and explicit gap analysis
The default budget inspects up to 300 registered source rows, covering the current 248 curated technical sources and added specialist references. It uses the original verified canonical workboard in pages of no more than 60 rows. Raw registered rows count against the scan budget even if policies exclude their source, stopping large blocked inventories from causing unlimited scanning. Results explicitly declare whether the scan exhausted the source inventory, give observed scope, matched and unmatched task terms, exact source identities, observed host diversity and remaining prerequisites.

No source is crawled, no transcript downloaded, no worker started, no source rights issued, no XP minted, no AI model trained and no knowledge automatically approved. The plans are deterministic and include a canonical digest. Priority never implies verified quality or fact agreement.

## Milestone 3: Authenticated GameForge Studio integration
A new authenticated GET /api/dragon-research/task-plan returns these bounded recommendations, using the existing tenant principal and request-scoped read-only SQLite research sessions. The task input is one to eight unique lowercase topics, including AI/QA/VR, and the source census budget is 1–300. The route sets Cache-Control private/no-store and rejects malformed terms with 422 and corrupted custody with 409.

The new mother-Dragon cockpit section lets players enter game research topics and see grouped recommendations for all three hatchlings, exact and adjacent matches, missing-topic gaps and the separate review or authorization requirements. A changed task cancels stale requests. The screen rejects responses claiming implicit worker execution, permission, XP or model-weight changes.

## Verification and adversarial constraints
Added specialist tests for deterministic complete scans, three hatchlings, partial scans, two-letter topics, tenant isolation, malformed/duplicated inputs and changed source-integrity digests. Backend route tests cover registered API shape and rights-safe behavior. The exact feature-branch CI will determine actual pass/fail status; no green result is assumed before execution.

2026-10-12 UTC improvements: (real game-task-based source navigation); (balanced three-lane suggestions); (explicit gaps and partial scan boundaries); (no bypass around idle-only execution and independent Wiki/HOAG approval).