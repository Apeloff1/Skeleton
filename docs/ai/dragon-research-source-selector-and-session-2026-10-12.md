# Dragon research milestones — catalog, safer access, and production data sessions
Timestamp: 2026-10-12 UTC. Feature branch: feat/dragon-wisdom-review-20261010. PR #3605.

## Milestone A — Discover real owner-bound sources in the three-hatchling cockpit

Previously, the React Native companion expected operators to manually enter opaque 71-character source identities. DragonResearchSourcePicker now pages across the original owner-scoped canonical Dragon source registry (at most 60 scanned identities per request), verifying technical-article atlas ownership or separately registered video identities through the existing canonical source custodians. Sources blocked by the original policy job are never suggested. It returns only IDs, concise labels/hosts, evidence readiness and custody receipts. It does not fetch web pages, claim source rights, award XP or promote weights.

The backend GET /api/dragon-research/sources uses the same authenticated Dragon Academy tenant/principal mapping as the existing companion routes. It has a validated continuation cursor and bounded page size, never accepts database paths or owner identities from a request. The mobile cockpit exposes Discover / Refresh, filter, per-child source selection and Next page. Article and Updates can intentionally share the same source; Video must be a different identity. This is three specialist roles, not three artificially distinct publishers.

## Milestone B — Separate sensitive source excerpts from normal status

Standard child status reads no longer prefetch the editor-only mother review. A separate explicit tap fetches timecoded/video and article/update excerpts through the editor-authorized endpoint; guest or viewer access cannot obtain the raw review packet. Changing the source selection aborts prior requests and clears stale data. Every research response sets Cache-Control: private, no-store. All three endpoints are GET-only and return 503 if canonical storage was not installed, rather than synthetic demo output.

## Milestone C — Request-scoped production adapter over the existing databases

The new backend/core/dragon_research_session.py module composes canonical DragonAlmanacs, DragonTechnicalSources, DragonSourceCaptures, DragonNestStore, DragonNestSourceFeed, DragonVideoTranscriptLedger, DragonSourceDeltaLedger, DragonArticleHatchling and DragonThreeHatchlingCoordinator from two existing, operator-provisioned SQLite files. It opens fresh connections for each request, avoiding sharing a thread-confined SQLite connection between FastAPI web workers. No crawling, independent rights issuance, training, hidden schedule or model promotion is performed.

Installation is deliberately opt-in via SKL_DRAGON_RESEARCH_DASHBOARD_ENABLED=1, using these server-owned settings:

  SKL_DRAGON_KNOWLEDGE_DB_PATH: existing canonical reviewed-knowledge / research database
  SKL_DRAGON_PRACTICE_DB_PATH: existing signed-nest database
  SKL_DRAGON_NEST_SIGNING_KEY_HEX: separate, nonpublic HMAC nest key (32+ bytes)
  SKL_DRAGON_TRANSCRIPT_REVIEW_PUBLIC_KEY_HEX: externally managed Ed25519 public key (32 bytes)
  SKL_DRAGON_TRANSCRIPT_REVIEW_ISSUER and SKL_DRAGON_TRANSCRIPT_REVIEW_KEY_ID: trusted review identity

The values must be installed by a trusted service/deployment operator and never supplied by browser input. If any mandatory file/key is absent or invalid, installation refuses. No empty database fallback, no fabricated source state, and no automatic authorization to perform new research. The public signing key verifies existing transcript receipts and is not capable of granting rights.

## Integration tests and CI

Existing tests/test_dragon_specialist_evidence.py gains end-to-end read-only catalog cases covering actual article/video records, pagination, blocked-source exclusion, cross-tenant privacy, malformed cursors and tampered custody. New backend/tests/test_dragon_research_routes.py checks route registration, authenticated role dependencies, 503 failure without canonical storage, rejection of arbitrary IDs, tenant separation, no new files created on missing configuration, and construction of the request-scoped factory.

Dragon AI Verification now triggers on the new frontend, backend route, session and test files; its Python safety job compiles the source picker and session factory, its authenticated-backend tests include the new research routes, and its existing frontend typecheck includes the new companion screen.

**Validation limitation:** the PR's currently visible GitHub run previously showed only a passing CodeQL Analyze(actions) check. Source Safety pytest, backend route tests and frontend TypeScript checks must still be confirmed on the exact new head. The PR stays draft/unmerged.

Timestamped improvements:
- (All three hatchlings can be selected from real owner-bound curated sources.)
- (Blocked sources are omitted from the picker; source IDs no longer require manual memorization.)
- (Quote-bearing mother evidence requires an explicit editor-authorized request.)
- (Session-scoped connections use existing Dragon knowledge and signed-nest databases.)
- (Private no-store responses, bounded discovery and tenant-specific failure modes strengthen user safety.)

Next: execute Python/frontend tests, address failures, deploy trusted storage configuration and independently assess game-building benefits through the adversarial sandbox.