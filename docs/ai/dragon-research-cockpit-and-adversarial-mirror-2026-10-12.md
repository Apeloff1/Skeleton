# Dragon milestones — game-studio cockpit and adversarial knowledge review
Timestamp: 2026-10-12 UTC. Branch: feat/dragon-wisdom-review-20261010. PR #3605.

## Milestone 1: All-three-hatchling UI and read-only API

New frontend/app/dragon-research.tsx presents the Article, Video, and Updates hatchlings in that order, with actual signed-nest game level and accepted-evidence count, observed research receipts, and the mother Dragon's review hypotheses. GameForge Studio Overview links to the route. The client sends only three canonical source identity hashes, uses the existing authenticated API client, checks returned identities and discards stale requests. It never displays invented research or grants XP, permission, model weights, or background execution.

New backend/routes/dragon_research.py exposes status for authenticated Dragon Academy principals, with no client-supplied tenant or arbitrary DB path. The mother-review endpoint additionally requires an editor-level account because it returns bounded exact source excerpts. Both routes fail closed with 503 if a server-created canonical Dragon research coordinator is not configured, and 409 on inaccessible records.

The new router is registered in backend/core/routes_registry.py; the existing Dragon runtime lifespan can mount an already configured, correctly typed app.state.dragon_research_coordinator without creating unauthorized storage or replacing prior authorities. Production deployment must provision it; otherwise the screen honestly reports unavailable state.

## Milestone 2: Structured disagreement and uncertainty

New skeleton/ai/game_builder/dragon_evidence_disagreement.py checks source-exact excerpts for opposing polarity markers near shared concepts, differences in mentioned version numbers, conditional constraints, uncertainty and duplicated text. This is a deterministic, bounded reviewer aid, not a semantic truth engine or independent corroboration. The mother three-hatchling coordinator adds an evidence-risk packet to each candidate research question. No automatic review approval, training or growth occurs.

## Milestone 3: Adversarial mirror holdout gate

New skeleton/ai/game_builder/dragon_research_mirror.py compares the new rule-based signals to the preceding keyword-only baseline on labeled positive/negative controls. It reports baseline and candidate accuracy, TP/FP/FN/TN and a reproducible evaluation digest. It rejects unlabeled, duplicate, unbalanced and otherwise inadequate suites. The evaluator only tests the integrity and shape of supplied reviewer receipts, not their real-world signer identity. Production must authenticate the reviewer and proof outside the evaluation module.

Even a passing challenge cannot promote any model weights or serve as proof of improved game-building performance. The output expressly requires manual Wiki/HOAG review.

## Verification and scope

New tests/test_dragon_evidence_mirror.py exercises conflict/version/uncertainty cues, deterministic holdout score changes, and unsafe controls. The existing specialist evidence suite also verifies that the mother attaches reviewer-risk packets. The Dragon workflow now compiles both new modules and the backend route and executes these regression tests.

No real HTTP crawl, video download, OS worker process reconciliation, user-account provisioning or autonomous neural training occurred in this work pass. Python exact-head validation, frontend TypeScript build, and signed-in UI end-to-end tests remain necessary.

2026-10-12 UTC improvements:
- (All three hatchlings have an authenticated game-studio research cockpit.)
- (Read-only status and editor-only quoted evidence are separated.)
- (Mother research reports possible contradictions and version conflicts.)
- (Adversarial challenge scores candidate rules against a lexical baseline.)
- (Independent source rights, knowledge approval and model weights remain separately governed.)
