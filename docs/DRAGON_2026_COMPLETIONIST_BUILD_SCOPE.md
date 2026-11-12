# Dragon Research Pilot — 2026 Completionist Buildscope and Acceptance Ledger

> **Status:** This is an **expanded implementation plan**, NOT a claim that the planned tasks are already built, passing or releasable. It is bound to PR #5281 (`feat/dragon-research-pilot-qualification-20261112`), scoped from its reviewed source at `3d128e427bdd3c0c9a995423f7571804705ba099`. Source commits after this spec require new exact-head validation. Review-ready is not merge-ready.

## Program context and non-negotiable product contract

Dragon is the owner-scoped research/crawler companion to Jeeves. The user journey is: signed-in account → explicit source/rights scope → bounded capture → durable session and source library → Atlas verification → independent human review → rights-aware, revision-bound metadata receipt. The existing pilot implements a substantial first vertical slice, and its [current 2026 pilot specification](../docs/DRAGON_CRAWLER_USER_PILOT_SPEC.md) and [release readiness ledger](../docs/DRAGON_CAMPAIGN_PILOT_RELEASE_READINESS.md) remain authoritative on what was actually verified. This is a larger successor **work inventory**, not a rewrite of already-proven code.

**Hard invariants:** no cloud text-model fallback; no source-capture without separate consent; no automatic training/publication/knowledge promotion; SSRF/DNS/robots/rights enforced on the backend, not delegated to UI; tenant and owner scoped CAS; immutable source provenance; bounded crawler/sitemap/search/output resources; attacker-controlled source text cannot become privileged instructions; read-only receipts are not release grants. The Jeeves text model remains locally executed; Dragon analysis is advisory evidence and explicit tools, never an unreviewed second language-model authority.

**Existing relevant surfaces:** `frontend/app/dragon-crawler-pilot.tsx`, `CrawlerReleasePrototype.tsx`, `crawlerPilotFlow.ts`, `crawlerPilotContinuity.ts`, `DragonResearchDecisionCockpit.tsx`, `dragonResearchDecisionEngine.ts`, `crawlerClient.ts`, `crawlerPilotReceipt.ts`, `crawlerExport.ts`, `backend/core/dragon_crawler.py`, `backend/core/dragon_campaign_pilot_qualification.py`, `backend/tests/test_dragon_atlas_bridge.py`, `tests/e2e/app-foundation/dragon-crawler-pilot.spec.mjs`. Existing source tests and observed CI results must be rechecked on each resulting head.

## Inter-PR dependency and scope ownership

| Plane | PR / owner | Integration promise | Must remain independent |
|---|---|---|---|
| Dragon research/capture, source rights, Atlas | #5281 (this PR) | Produce bounded, consented, provenance-verified advisory observations | No model switching or direct application-level approval |
| Primary local Jeeves chat | #5282 | Ingest separately reviewed Dragon evidence as untrusted context | No remote provider fallback and no raw crawler source as system policy |
| Single-host inference custody | #5283 (stacked on #5282) | Keep overlapping native inference from corrupting the shared workspace | Does not grant Dragon rights or qualify crawler network |
| Installer / Builder / canonical application | upstream gates | Establish authentic install, permissions, device evidence and rollback | Source-only tests cannot substitute for physical-device proof |

## Definition of done for EACH ledger item

A package is **planned** until it has (1) a named implementation owner and module, (2) code, (3) a positive and an adversarial test, (4) memory/network/disk/time limits where applicable, (5) privacy/security review, (6) exact-head CI and evidence link, (7) rollback compatibility where persistent state changes, and (8) reviewer acknowledgement. All package IDs are stable planning identifiers, not tickets automatically created or work already completed.

## SOTA 2026 build architecture and execution order

- **R0 — owner/auth + rights + SSRF gates:** finish D01–D02 before expanding network capture or exports. Public URL syntax checks are insufficient without server DNS/redirect revalidation.
- **R1 — durable scheduling and source custody:** D03–D04 plus D10. Keep work order state deterministic, bounded and crash/replay safe before increasing worker count.
- **R2 — Atlas, decision and human review:** D05–D06; every claim traces to a revision-bound source and all release decisions remain human controlled.
- **R3 — Jeeves connection and accessible product:** D07–D08, with independent local-only constraints and offline/unavailable honesty.
- **R4 — hardening/performance/production admission:** D09–D12, device qualification, rollback, rights/security, and release attestations.

## Work breakdown — 142 separately testable build packages


### D01 — Identity, tenant custody and session admission

**Primary implementation seams:** `backend/core/dragon_crawler.py; frontend/src/product/crawlerClient.ts`. **Initial test location:** `backend/tests/test_dragon_campaign_pilot_qualification.py`. These paths are starting points, not evidence that future implementation already exists. Each item requires an exact-head negative test and bounded resource contract.

- **DR-01-01 — Bind the signed-in actor, tenant, deployment and authorization epoch to every campaign command.** *Acceptance/abuse case:* Foreign actor, expired principal, changed tenant or stale session must deny before any write. **State: PLANNED / not certified.**
- **DR-01-02 — Separate read, run, pause, export, rights-review and admin capabilities into server-authorized policies.** *Acceptance/abuse case:* UI role toggles, crafted client roles and legacy tokens cannot elevate privileges. **State: PLANNED / not certified.**
- **DR-01-03 — Enforce CSRF/origin protections on credential-bearing browser mutation paths.** *Acceptance/abuse case:* Cross-origin form and crafted referer requests fail without session mutation. **State: PLANNED / not certified.**
- **DR-01-04 — Use canonical tenant-scoped idempotency keys for all create/resume/slice operations.** *Acceptance/abuse case:* Reusing a key with modified sources, policy or budget returns deterministic conflict. **State: PLANNED / not certified.**
- **DR-01-05 — Expose a bounded account/readiness preflight with explicit unavailable dependency codes.** *Acceptance/abuse case:* Partial offline Atlas or queue outage cannot display the campaign as runnable. **State: PLANNED / not certified.**
- **DR-01-06 — Require separate approval for research capture, export and knowledge promotion.** *Acceptance/abuse case:* Capture approval cannot act as downstream publish or training consent. **State: PLANNED / not certified.**
- **DR-01-07 — Guard concurrent browser tabs with versioned server revisions and refresh prompts.** *Acceptance/abuse case:* Two tabs editing same campaign cannot silently overwrite rights or stop state. **State: PLANNED / not certified.**
- **DR-01-08 — Recover user intent following unauthorized and expired actions without replaying mutation.** *Acceptance/abuse case:* Reconnect first performs authenticated read-only reconciliation. **State: PLANNED / not certified.**
- **DR-01-09 — Track auth revocation as a hard fence on running source reads and exports.** *Acceptance/abuse case:* Deleted or suspended user cannot continue an already queued export. **State: PLANNED / not certified.**
- **DR-01-10 — Verify user-facing error text is bounded, localized and free of internal identifiers.** *Acceptance/abuse case:* Secret canaries, Atlas connection strings and raw source URLs never leak into error toast. **State: PLANNED / not certified.**

### D02 — Source eligibility, SSRF, robots and rights admission

**Primary implementation seams:** `backend/core/dragon_crawler.py; frontend/src/features/Jeeves/crawlerPilotFlow.ts`. **Initial test location:** `backend/tests/test_dragon_campaign_pilot_qualification.py`. These paths are starting points, not evidence that future implementation already exists. Each item requires an exact-head negative test and bounded resource contract.

- **DR-02-01 — Canonicalize HTTPS sources with IDNA, redirects, Unicode and port normalization.** *Acceptance/abuse case:* Embedded credentials, IP literals, ambiguous hostnames and parser differentials fail. **State: PLANNED / not certified.**
- **DR-02-02 — Resolve DNS and independently revalidate public addresses on each redirect/hop.** *Acceptance/abuse case:* Public-to-private DNS rebinding and alternate address families cannot bypass policy. **State: PLANNED / not certified.**
- **DR-02-03 — Bound redirect counts and same-origin policy with explicit host-scoped consent.** *Acceptance/abuse case:* Redirects to unapproved domains are rejected instead of auto-expanding rights. **State: PLANNED / not certified.**
- **DR-02-04 — Honor robots, applicable access rights, crawl delay and hard disallow decisions.** *Acceptance/abuse case:* Missing robots proof or ambiguous permissions never becomes authorization. **State: PLANNED / not certified.**
- **DR-02-05 — Freeze allowed source-host set as a SHA-bound create receipt.** *Acceptance/abuse case:* Edited client sources after admission cannot alter the running frontier. **State: PLANNED / not certified.**
- **DR-02-06 — Apply per-host token buckets, deterministic pacing and bounded retries.** *Acceptance/abuse case:* 429/503 cannot cause retry storms, timeouts cannot create unbounded tasks. **State: PLANNED / not certified.**
- **DR-02-07 — Support sitemap-only discovery with finite fanout and source budget.** *Acceptance/abuse case:* Recursive sitemap cycles and decompression bombs fail closed. **State: PLANNED / not certified.**
- **DR-02-08 — Reject unbounded MIME, archive, binary, compressed and streaming content.** *Acceptance/abuse case:* Gigantic/chunked/gzip bomb responses abort within memory/disk cap. **State: PLANNED / not certified.**
- **DR-02-09 — Treat crawl output as untrusted text, never as control-plane instructions.** *Acceptance/abuse case:* Injected system prompts, URL templates and shell fragments stay inert. **State: PLANNED / not certified.**
- **DR-02-10 — Record source-rights basis and reviewable expiration without licensing inference.** *Acceptance/abuse case:* Source rights remain UNKNOWN until explicit owner-reviewed evidence. **State: PLANNED / not certified.**
- **DR-02-11 — Handle takedown requests as an immediate stop, quarantine and export-deny.** *Acceptance/abuse case:* Revocation during capture invalidates pending share and downstream approval. **State: PLANNED / not certified.**
- **DR-02-12 — Record explicit denial reasons with private operational evidence separately.** *Acceptance/abuse case:* Public UI sees codes, not sensitive policy text or source-body fragments. **State: PLANNED / not certified.**

### D03 — Frontier, distributed workers and bounded retries

**Primary implementation seams:** `backend/core/dragon_crawler.py; frontend/src/product/crawlerClient.ts`. **Initial test location:** `backend/tests/test_dragon_campaign_pilot_qualification.py`. These paths are starting points, not evidence that future implementation already exists. Each item requires an exact-head negative test and bounded resource contract.

- **DR-03-01 — Formalize campaign states with transitions for queued, admitted, running, pausing, paused, cancelling, stopped and failed.** *Acceptance/abuse case:* Illegal state transition does not advance version or consume budget. **State: PLANNED / not certified.**
- **DR-03-02 — Use durable per-slice work orders with attempt, lease owner, expiry and monotonic sequence.** *Acceptance/abuse case:* Stale workers cannot commit after a new owner takes over. **State: PLANNED / not certified.**
- **DR-03-03 — Enforce exactly-once committed source receipts, not exactly-once network fetch claims.** *Acceptance/abuse case:* Replayed jobs deduplicate by canonical source/content epoch. **State: PLANNED / not certified.**
- **DR-03-04 — Cap per-campaign concurrent fetches and global host connections independently.** *Acceptance/abuse case:* A large campaign cannot monopolize the backend or starve peers. **State: PLANNED / not certified.**
- **DR-03-05 — Implement fair host scheduling, depth frontier and deterministic run-order hashes.** *Acceptance/abuse case:* Equivalent inputs yield stable admission ordering irrespective of worker timing. **State: PLANNED / not certified.**
- **DR-03-06 — Fence backpressure across CPU, RAM, disk, network and queue capacity.** *Acceptance/abuse case:* Under pressure, refuse new leases before corrupting active work. **State: PLANNED / not certified.**
- **DR-03-07 — Persist progress monotonicity, reset intent and interrupted-slice metadata.** *Acceptance/abuse case:* Percent progress never decreases silently or implies completed documents. **State: PLANNED / not certified.**
- **DR-03-08 — Handle token expiration while workers are active with explicit custody states.** *Acceptance/abuse case:* Revoked rights stop new work and quarantine uncommitted output. **State: PLANNED / not certified.**
- **DR-03-09 — Bound retry classes separately for HTTP policy, transient network and storage conflicts.** *Acceptance/abuse case:* SSRF/rights denial never retries as an availability failure. **State: PLANNED / not certified.**
- **DR-03-10 — Support operator pause/drain and crash recovery without duplicate source publication.** *Acceptance/abuse case:* Restart reproduces canonical receipt sequence and budget accounting. **State: PLANNED / not certified.**
- **DR-03-11 — Make long campaigns observable via coarse rate and bounded failure categories.** *Acceptance/abuse case:* Metrics never carry full request URLs, cookies, source bodies or bearer tokens. **State: PLANNED / not certified.**
- **DR-03-12 — Provide force-stop with worker draining and post-stop read-only evidence.** *Acceptance/abuse case:* Timeout cannot be mislabeled as clean shutdown. **State: PLANNED / not certified.**

### D04 — Source library, provenance, citations and export

**Primary implementation seams:** `frontend/src/product/crawlerExport.ts; frontend/src/product/crawlerClient.ts`. **Initial test location:** `frontend/scripts/test-crawler-pilot-journey.mjs`. These paths are starting points, not evidence that future implementation already exists. Each item requires an exact-head negative test and bounded resource contract.

- **DR-04-01 — Persist original source identity, fetch timestamp, rights version and content digest per item.** *Acceptance/abuse case:* A source pointer alone is never promoted as verified provenance. **State: PLANNED / not certified.**
- **DR-04-02 — Index deduplicated chunks with source offsets, canonical document id and epoch.** *Acceptance/abuse case:* Same text from unrelated sources does not collapse identity. **State: PLANNED / not certified.**
- **DR-04-03 — Provide bounded search, deterministic pagination, cursors and stable sorting.** *Acceptance/abuse case:* Forged/outdated cursor cannot skip permission checks. **State: PLANNED / not certified.**
- **DR-04-04 — Allow passage preview with redacted markup and safe text-only rendering.** *Acceptance/abuse case:* Script tags, SVG, CSS and bidirectional controls cannot execute or distort review. **State: PLANNED / not certified.**
- **DR-04-05 — Support exact passage-to-citation binding with digest and offset verification.** *Acceptance/abuse case:* Edited source text invalidates old citation rather than silently shifting anchors. **State: PLANNED / not certified.**
- **DR-04-06 — Track evidence freshness and expired/unreachable source disposition.** *Acceptance/abuse case:* Stale snapshots cannot be presented as current evidence. **State: PLANNED / not certified.**
- **DR-04-07 — Separate metadata-only portable export from rights-approved body export.** *Acceptance/abuse case:* Default share contains no captured body, credentials or private search query. **State: PLANNED / not certified.**
- **DR-04-08 — Enforce source-level export revocation and per-record omission receipts.** *Acceptance/abuse case:* One denied source never leaks through aggregate archive. **State: PLANNED / not certified.**
- **DR-04-09 — Make CSV/JSON/Markdown exports injection-resistant and canonical.** *Acceptance/abuse case:* Spreadsheet formula and hyperlink payloads remain literal inert data. **State: PLANNED / not certified.**
- **DR-04-10 — Verify import/export checksums and schema migrations before user download.** *Acceptance/abuse case:* Manipulated nested receipts and truncated archives are rejected. **State: PLANNED / not certified.**
- **DR-04-11 — Implement user deletion and bounded retention for snapshots, caches and derived chunks.** *Acceptance/abuse case:* Deletion proof covers all serving copies and indexes. **State: PLANNED / not certified.**
- **DR-04-12 — Provide canonical missing-source and broken-link repair without inventing citations.** *Acceptance/abuse case:* Unknown provenance shows pending evidence, never an inferred URL. **State: PLANNED / not certified.**

### D05 — Atlas analysis and evidence-to-claim trust

**Primary implementation seams:** `frontend/src/features/Jeeves/CrawlerResearchAtlasPanel.tsx; backend/core/dragon_campaign_pilot_qualification.py`. **Initial test location:** `backend/tests/test_dragon_atlas_bridge.py`. These paths are starting points, not evidence that future implementation already exists. Each item requires an exact-head negative test and bounded resource contract.

- **DR-05-01 — Pin Atlas reads to exact campaign, source-policy, snapshot and actor revisions.** *Acceptance/abuse case:* A revised campaign cannot reuse an older favorable Atlas result. **State: PLANNED / not certified.**
- **DR-05-02 — Treat Mongo result data as untrusted typed observations, never release authority.** *Acceptance/abuse case:* Forged ready=true in backend payload cannot override owner policy. **State: PLANNED / not certified.**
- **DR-05-03 — Make claim-to-source trace graph explicit with confidence and uncertainty labels.** *Acceptance/abuse case:* Claims without cited passages are visibly unsubstantiated. **State: PLANNED / not certified.**
- **DR-05-04 — Display contradiction clusters and provenance gaps rather than averaging conflicts.** *Acceptance/abuse case:* Two inconsistent sources cannot become falsely unanimous. **State: PLANNED / not certified.**
- **DR-05-05 — Compute objective coverage with deterministic denominator and known-missing classes.** *Acceptance/abuse case:* Zero-sample and missing-objective cases never score as complete. **State: PLANNED / not certified.**
- **DR-05-06 — Separate host independence, publisher independence and corroboration.** *Acceptance/abuse case:* Many pages from one host must not count as independent authorities. **State: PLANNED / not certified.**
- **DR-05-07 — Support host ablation, time-slice ablation and alternate-policy simulation.** *Acceptance/abuse case:* Counterfactual results are marked simulated and do not trigger capture. **State: PLANNED / not certified.**
- **DR-05-08 — Expose per-objective weakness, single-host dependence and reviewer urgency.** *Acceptance/abuse case:* Degraded evidence never improves a robustness grade. **State: PLANNED / not certified.**
- **DR-05-09 — Verify Atlas result digests before share or human signoff.** *Acceptance/abuse case:* Tampered response text/digest refuses export. **State: PLANNED / not certified.**
- **DR-05-10 — Handle Atlas unavailable/reconnect as a distinct state preserving canonical reads.** *Acceptance/abuse case:* Automatic refresh cannot overwrite a user-selected historical snapshot. **State: PLANNED / not certified.**
- **DR-05-11 — Record source-rights conflicts directly in the research decision context.** *Acceptance/abuse case:* Strong semantic relevance never overrides rights denial. **State: PLANNED / not certified.**
- **DR-05-12 — Provide a reproducible deterministic research brief from frozen metadata-only inputs.** *Acceptance/abuse case:* Same frozen input gives byte-identical brief and digest. **State: PLANNED / not certified.**

### D06 — Human review, decision cockpit and consent transitions

**Primary implementation seams:** `frontend/src/features/Jeeves/DragonResearchDecisionCockpit.tsx; frontend/src/features/Jeeves/dragonResearchDecisionEngine.ts`. **Initial test location:** `frontend/scripts/test-dragon-advanced-decision.mjs`. These paths are starting points, not evidence that future implementation already exists. Each item requires an exact-head negative test and bounded resource contract.

- **DR-06-01 — Implement an explicit review queue for factual, legal, safety and release questions.** *Acceptance/abuse case:* Review task creation grants no autonomous approval. **State: PLANNED / not certified.**
- **DR-06-02 — Make reviewer identity, quorum, decision reason and timestamp mandatory.** *Acceptance/abuse case:* Anonymous and self-reviewed protected actions cannot be finalized. **State: PLANNED / not certified.**
- **DR-06-03 — Bound review-task estimates and finite budget by objective and severity.** *Acceptance/abuse case:* Tasks beyond budget remain listed and explicitly unapproved. **State: PLANNED / not certified.**
- **DR-06-04 — Separate blocker/urgent/next/deferred statuses with deterministic precedence.** *Acceptance/abuse case:* Low-priority UX work cannot displace a critical SSRF blocker. **State: PLANNED / not certified.**
- **DR-06-05 — Bind decision share to snapshot, owner, role, source rights, scenario and revision.** *Acceptance/abuse case:* Any change invalidates stale share authorization. **State: PLANNED / not certified.**
- **DR-06-06 — Add reversible scenario exploration with clear counterfactual labeling.** *Acceptance/abuse case:* A hypothetical alternate choice cannot mutate actual policy state. **State: PLANNED / not certified.**
- **DR-06-07 — Support reviewer disagreement and escalation without rewriting evidence history.** *Acceptance/abuse case:* Disagreement remains auditable and cannot be silently deleted. **State: PLANNED / not certified.**
- **DR-06-08 — Require second review for training, publication, external export and policy override.** *Acceptance/abuse case:* Single reviewer cannot grant irreversible broad rights. **State: PLANNED / not certified.**
- **DR-06-09 — Provide source-specific takedown and revocation controls within review.** *Acceptance/abuse case:* Revoked source disappears from future share plans immediately. **State: PLANNED / not certified.**
- **DR-06-10 — Make keyboard/mobile-accessible evidence triage and citation opening reliable.** *Acceptance/abuse case:* Focus escape, truncated content and touch controls cannot skip confirmation. **State: PLANNED / not certified.**
- **DR-06-11 — Include decision rationale and versioned consent receipt in pilot exit packet.** *Acceptance/abuse case:* Copied brief cannot act as independent live authorization. **State: PLANNED / not certified.**
- **DR-06-12 — Offer explicit return-to-review after network interruption or session rotation.** *Acceptance/abuse case:* Unsaved intent never becomes approved action. **State: PLANNED / not certified.**

### D07 — User UX, accessibility and onboarding

**Primary implementation seams:** `frontend/src/features/Jeeves/CrawlerReleasePrototype.tsx; frontend/app/dragon-crawler-pilot.tsx`. **Initial test location:** `tests/e2e/app-foundation/dragon-crawler-pilot.spec.mjs`. These paths are starting points, not evidence that future implementation already exists. Each item requires an exact-head negative test and bounded resource contract.

- **DR-07-01 — Show one primary guided path from auth to capture, sources, Atlas, review and exit.** *Acceptance/abuse case:* No hidden prerequisite requires a terminal or expert knowledge. **State: PLANNED / not certified.**
- **DR-07-02 — Implement anonymous, expired-session and insufficient-role recovery screens.** *Acceptance/abuse case:* Auth failure cannot expose private historical campaign text. **State: PLANNED / not certified.**
- **DR-07-03 — Default all capture, rights, share and publish toggles to off.** *Acceptance/abuse case:* Back/forward navigation never silently enables consent. **State: PLANNED / not certified.**
- **DR-07-04 — Display resource forecast and risk before create confirmation.** *Acceptance/abuse case:* Unbounded budget defaults are not executable. **State: PLANNED / not certified.**
- **DR-07-05 — Preserve draft inputs per user/session with explicit reset and retention window.** *Acceptance/abuse case:* Account switch destroys old draft without leaking it. **State: PLANNED / not certified.**
- **DR-07-06 — Show accurate live stage, heartbeat age, busy state and last durable checkpoint.** *Acceptance/abuse case:* Stale data is identified and never shown as current completion. **State: PLANNED / not certified.**
- **DR-07-07 — Support keyboard, screen reader, contrast, reduced motion and touch targets.** *Acceptance/abuse case:* All 6 stages usable without pointer and without animation. **State: PLANNED / not certified.**
- **DR-07-08 — Add reconnect/offline banners with separate local-cache and server-authority states.** *Acceptance/abuse case:* Offline cached status cannot issue a server-side commit. **State: PLANNED / not certified.**
- **DR-07-09 — Implement empty-library, partial-ingest and revoked-source states.** *Acceptance/abuse case:* No-results is not indistinguishable from failed search. **State: PLANNED / not certified.**
- **DR-07-10 — Show safe share preview with exact fields and rights redaction before download.** *Acceptance/abuse case:* Sensitive source snippets cannot escape through preview. **State: PLANNED / not certified.**
- **DR-07-11 — Offer first-user task walkthrough with realistic failure/retry paths.** *Acceptance/abuse case:* Tour copy never promises unsupported live crawl or cloud safety. **State: PLANNED / not certified.**
- **DR-07-12 — Preserve meaningful errors for user while avoiding internal operational data.** *Acceptance/abuse case:* Error copy maps typed denial to actionable remediation. **State: PLANNED / not certified.**

### D08 — Cross-plane Jeeves integration without authority confusion

**Primary implementation seams:** `frontend/src/product/crawlerClient.ts; skeleton/app/jeeves_advisory.py`. **Initial test location:** `backend/tests/test_dragon_campaign_pilot_qualification.py`. These paths are starting points, not evidence that future implementation already exists. Each item requires an exact-head negative test and bounded resource contract.

- **DR-08-01 — Expose approved Dragon passages as advisory context only under explicit reviewer grant.** *Acceptance/abuse case:* Crawler text cannot become Jeeves system instructions. **State: PLANNED / not certified.**
- **DR-08-02 — Bind advisory observations to source digest, rights version and exact reviewer scope.** *Acceptance/abuse case:* Changed or revoked evidence cannot remain trusted in new chat. **State: PLANNED / not certified.**
- **DR-08-03 — Require explicit user selection of source passages before grounding a Jeeves question.** *Acceptance/abuse case:* Crawler cannot inject context into all future conversation turns. **State: PLANNED / not certified.**
- **DR-08-04 — Define a common source-citation schema across Dragon, Atlas and Jeeves SQLite.** *Acceptance/abuse case:* A citation without verified owner/source link cannot be accepted. **State: PLANNED / not certified.**
- **DR-08-05 — Preserve model-local execution rule even when Atlas analysis is unavailable.** *Acceptance/abuse case:* No hosted LLM fallback from crawler, chat or review panels. **State: PLANNED / not certified.**
- **DR-08-06 — Handle no-reference case as an honest grounded-answer refusal or ungrounded prompt choice.** *Acceptance/abuse case:* Model must not fabricate citations to meet a UI expectation. **State: PLANNED / not certified.**
- **DR-08-07 — Record advisory consent and TTL as versioned scoped evidence.** *Acceptance/abuse case:* Expired consent excludes subsequent retrieval. **State: PLANNED / not certified.**
- **DR-08-08 — Use bounded context windows and source budget when constructing evidence manifests.** *Acceptance/abuse case:* Massive crawl cannot overflow local model context. **State: PLANNED / not certified.**
- **DR-08-09 — Provide safe source-view back-links from chat to original Dragon review.** *Acceptance/abuse case:* Citation link cannot grant extra retrieval permissions. **State: PLANNED / not certified.**
- **DR-08-10 — Protect tenant isolation across chat, review, crawl and export identities.** *Acceptance/abuse case:* User A's source digest cannot authorize user B's passage. **State: PLANNED / not certified.**
- **DR-08-11 — Check model/advisory output for unsafe direct actions before automation handoff.** *Acceptance/abuse case:* Generated commands require separate privileged approval. **State: PLANNED / not certified.**
- **DR-08-12 — Use provenance-hardened replay across app restart and concurrent tabs.** *Acceptance/abuse case:* Imported chat must retain advisory-source authenticity or label uncertainty. **State: PLANNED / not certified.**

### D09 — Security hardening and abuse resistance

**Primary implementation seams:** `backend/core/dragon_crawler.py; frontend/src/product/crawlerClient.ts`. **Initial test location:** `backend/tests/test_dragon_campaign_pilot_qualification.py`. These paths are starting points, not evidence that future implementation already exists. Each item requires an exact-head negative test and bounded resource contract.

- **DR-09-01 — Threat-model SSRF, DNS rebinding, redirect loops and alternate network interfaces.** *Acceptance/abuse case:* Include denial fuzzing with private IP, metadata service and onion-like aliases. **State: PLANNED / not certified.**
- **DR-09-02 — Limit aggregate response bytes, decompressed bytes, tokens, CPU time and disk writes.** *Acceptance/abuse case:* Compression and parser bombs do not exhaust the host. **State: PLANNED / not certified.**
- **DR-09-03 — Enforce per-user and per-tenant admission, throttling and resource fair share.** *Acceptance/abuse case:* Bursty actor cannot cause unbounded worker creation. **State: PLANNED / not certified.**
- **DR-09-04 — Reject path traversal, symlink/hardlink and workspace replacement in export paths.** *Acceptance/abuse case:* No file outside selected private root can be read or overwritten. **State: PLANNED / not certified.**
- **DR-09-05 — Mask source credentials, signed URLs, cookies and raw HTTP trace from telemetry.** *Acceptance/abuse case:* Canary secrets absent in logs, APIs and support bundles. **State: PLANNED / not certified.**
- **DR-09-06 — Guard generated Markdown/HTML and clipboard paths against XSS/injection.** *Acceptance/abuse case:* Pasted source scripts never execute as trusted UI. **State: PLANNED / not certified.**
- **DR-09-07 — Enforce strict allowlist of backend commands and schema discrimination.** *Acceptance/abuse case:* Extra fields and type confusion reject rather than ignore. **State: PLANNED / not certified.**
- **DR-09-08 — Separate public crawl permission from rights to store, train or republish.** *Acceptance/abuse case:* Robots allowance cannot equal copyright license. **State: PLANNED / not certified.**
- **DR-09-09 — Detect egress violations and unauthorized remote hosts in integration tests.** *Acceptance/abuse case:* CI replay fails on unexpected outbound network. **State: PLANNED / not certified.**
- **DR-09-10 — Model poison and prompt-injection attacks as evidence corruption.** *Acceptance/abuse case:* Instructions embedded in sources stay inert and reviewer-visible. **State: PLANNED / not certified.**
- **DR-09-11 — Implement access revocation barriers on long-lived Atlas/search connections.** *Acceptance/abuse case:* Revoked actor cannot continue reading prior streams. **State: PLANNED / not certified.**
- **DR-09-12 — Produce bounded security audit receipts without content disclosure.** *Acceptance/abuse case:* Audit has event ids, version and class but not fetched body. **State: PLANNED / not certified.**

### D10 — Persistence, migration and data lifecycle

**Primary implementation seams:** `backend/core/dragon_campaign_pilot_qualification.py; backend/core/dragon_crawler.py`. **Initial test location:** `backend/tests/test_dragon_campaign_pilot_qualification.py`. These paths are starting points, not evidence that future implementation already exists. Each item requires an exact-head negative test and bounded resource contract.

- **DR-10-01 — Version every campaign and source record schema with forward-only migration.** *Acceptance/abuse case:* Older DB snapshots either migrate atomically or fail closed. **State: PLANNED / not certified.**
- **DR-10-02 — Define backup/restore with durable revision and content digest verification.** *Acceptance/abuse case:* Partial restore never appears as completed campaign. **State: PLANNED / not certified.**
- **DR-10-03 — Test snapshot consistency across Mongo/SQL/queue boundaries.** *Acceptance/abuse case:* Cross-service disagreement produces an explicit unverified state. **State: PLANNED / not certified.**
- **DR-10-04 — Enforce immutable event and source provenance streams with append-only revisions.** *Acceptance/abuse case:* Mutable display metadata cannot rewrite historical evidence. **State: PLANNED / not certified.**
- **DR-10-05 — Introduce bounded retention by source rights and active legal hold.** *Acceptance/abuse case:* Expired rights remove exportability even before content purge. **State: PLANNED / not certified.**
- **DR-10-06 — Provide GDPR-style owner export/delete workflows where applicable.** *Acceptance/abuse case:* Deletion reaches indexes, caches, transcript links and artifact jobs. **State: PLANNED / not certified.**
- **DR-10-07 — Implement CAS guards on review decision, versioned share and paused campaign commands.** *Acceptance/abuse case:* Concurrent mutation cannot bypass current revision. **State: PLANNED / not certified.**
- **DR-10-08 — Handle disk full, file rotation, backup interruption and corrupt DB indexes.** *Acceptance/abuse case:* No partial success receipt or unreadable unchecked history. **State: PLANNED / not certified.**
- **DR-10-09 — Validate idempotency across process restart and distributed worker scheduling.** *Acceptance/abuse case:* Old command returns prior receipt, not duplicate work. **State: PLANNED / not certified.**
- **DR-10-10 — Record migration provenance and rollback blockers separately.** *Acceptance/abuse case:* Rollback forbidden if new schema cannot be read safely. **State: PLANNED / not certified.**
- **DR-10-11 — Support interrupted source reindex with checkpoint and deterministic restart.** *Acceptance/abuse case:* No duplicated citation IDs or orphaned source references. **State: PLANNED / not certified.**
- **DR-10-12 — Expose consistency audit for operator triage without private body export.** *Acceptance/abuse case:* Audit summarizes discrepancies without raw source text. **State: PLANNED / not certified.**

### D11 — Performance and capacity engineering

**Primary implementation seams:** `backend/core/dragon_crawler.py; frontend/src/features/Jeeves/CrawlerReleasePrototype.tsx`. **Initial test location:** `tests/e2e/app-foundation/dragon-crawler-pilot.spec.mjs`. These paths are starting points, not evidence that future implementation already exists. Each item requires an exact-head negative test and bounded resource contract.

- **DR-11-01 — Set measured p50/p95/p99 stage-transition latency objectives by environment.** *Acceptance/abuse case:* Claims require representative hardware and CI baselines. **State: PLANNED / not certified.**
- **DR-11-02 — Define bounded memory, request and disk budgets for 1–128 requests/campaign.** *Acceptance/abuse case:* Upper limits do not become implicit recommended defaults. **State: PLANNED / not certified.**
- **DR-11-03 — Add multi-tenant load test with 1/10/100 simultaneous scoped users.** *Acceptance/abuse case:* No rights leak and fairness remains measurable. **State: PLANNED / not certified.**
- **DR-11-04 — Benchmark source indexing and result pagination at 1/100/10000 documents.** *Acceptance/abuse case:* Query latency and process memory stay below stated limits. **State: PLANNED / not certified.**
- **DR-11-05 — Profile Atlas generation and bounded snapshot verification.** *Acceptance/abuse case:* Large evidence graphs cannot cause exponential UI recompute. **State: PLANNED / not certified.**
- **DR-11-06 — Use incremental UI render and virtualization for long source lists.** *Acceptance/abuse case:* Mobile scroll remains responsive under realistic payload size. **State: PLANNED / not certified.**
- **DR-11-07 — Control reconnect/backoff jitter and polling budget across background tabs.** *Acceptance/abuse case:* Unfocused tab cannot swamp service or drain battery. **State: PLANNED / not certified.**
- **DR-11-08 — Measure crawler head-of-line blocking from slow domains.** *Acceptance/abuse case:* One hanging host cannot starve all others. **State: PLANNED / not certified.**
- **DR-11-09 — Tune storage space admission and failure warning before capture.** *Acceptance/abuse case:* Low disk prevents new work and keeps old evidence recoverable. **State: PLANNED / not certified.**
- **DR-11-10 — Track redacted worker health, failure classes and time to recover.** *Acceptance/abuse case:* Observability does not reveal private hostnames or query text. **State: PLANNED / not certified.**
- **DR-11-11 — Benchmark export generation and cancel under maximum bounded metadata.** *Acceptance/abuse case:* Cancellation releases temp files and reserved storage. **State: PLANNED / not certified.**
- **DR-11-12 — Provide adaptive feature downgrade with explicit user-visible indication.** *Acceptance/abuse case:* Degraded mode never quietly drops source verification. **State: PLANNED / not certified.**

### D12 — Validation, CI, release control and operations

**Primary implementation seams:** `docs/DRAGON_CRAWLER_USER_PILOT_SPEC.md; .github/workflows/dragon-pilot-source-qualification.yml`. **Initial test location:** `tests/e2e/app-foundation/dragon-crawler-pilot.spec.mjs`. These paths are starting points, not evidence that future implementation already exists. Each item requires an exact-head negative test and bounded resource contract.

- **DR-12-01 — Make exact-head workflow inventory include every changed source and contract seam.** *Acceptance/abuse case:* Older ancestor CI does not qualify current head. **State: PLANNED / not certified.**
- **DR-12-02 — Run source unit, Atlas integration, rights, malicious source and auth negative suites.** *Acceptance/abuse case:* Skipped or cancelled jobs never count as passed. **State: PLANNED / not certified.**
- **DR-12-03 — Execute real Docker-backed Chromium signed-in pilot from login to exit.** *Acceptance/abuse case:* Browser success includes actual backend and durable data custody. **State: PLANNED / not certified.**
- **DR-12-04 — Add independent Windows 11/WSL2, Docker, iOS, Android and ARM host acceptance.** *Acceptance/abuse case:* Emulator or Linux-only source checks cannot certify device. **State: PLANNED / not certified.**
- **DR-12-05 — Exercise offline/slow network, browser crash, app restart and server reboot.** *Acceptance/abuse case:* Recovered revisions and consents are consistent. **State: PLANNED / not certified.**
- **DR-12-06 — Perform migration, backup/restore, rollback and failed-upgrade dry runs.** *Acceptance/abuse case:* Artifacts and user data remain intact on refusal. **State: PLANNED / not certified.**
- **DR-12-07 — Record SBOM, dependency, CodeQL, secret, malware and license evidence.** *Acceptance/abuse case:* High/critical findings require explicit remediation and revalidation. **State: PLANNED / not certified.**
- **DR-12-08 — Verify build provenance, signed release artifacts and deterministic version inventory.** *Acceptance/abuse case:* Artifacts tied to source SHA and toolchain hashes. **State: PLANNED / not certified.**
- **DR-12-09 — Require independent rights/provenance signoff before external share or publication.** *Acceptance/abuse case:* No automatic source-rights promotion from crawler metadata. **State: PLANNED / not certified.**
- **DR-12-10 — Review repository rulesets and branch protections as real enforced settings.** *Acceptance/abuse case:* PR labels alone cannot be treated as security enforcement. **State: PLANNED / not certified.**
- **DR-12-11 — Use canary pilot cohort with kill switch, health budget and rollback playbook.** *Acceptance/abuse case:* Pilot regressions stop rollout before wider exposure. **State: PLANNED / not certified.**
- **DR-12-12 — Produce release evidence packet with reviewer, run links, exact SHA, dates and open holds.** *Acceptance/abuse case:* Ship state defaults to NO GO until every mandatory gate is evidenced. **State: PLANNED / not certified.**

## Cross-cutting authority and data contracts

| Contract | Required fields and behavior | Rejection behavior |
|---|---|---|
| `ResearchSourceGrant.v2` (planned) | actor/tenant; canonical HTTPS origin; verified IP and redirect chain; robots policy; capture, index, export, training and publish rights **separately**; expiration; source digest; approval epoch | Missing grant, stale revision, ambiguous rights, private IP or changed host => deny before fetch |
| `CrawlWorkOrder.v2` (planned) | immutable campaign id; tenant; frontier revision; source grant SHA; bounded budgets; work class; lease owner/expiry; idempotency digest; monotonic attempt | Stale lease, duplicate spend, cross-tenant receipt => deterministic conflict |
| `ResearchSnapshot.v2` (planned) | exact campaign/run sequence; normalized source and chunk digests; approved query scope; provenance chain; timestamp; tool version; integrity envelope | Missing chunk, content mismatch or out-of-policy source => evidence cannot be approved |
| `AtlasClaim.v2` (planned) | objective; source-offset citations; confidence and uncertainty; corroboration; contradiction; model/tool provenance; privacy state | No evidence or contradictory provenance => clearly unverified claim, not publish-ready |
| `ReviewerDecision.v2` (planned) | actor, role, independent reviewer, decision, revision, rationale, rights state and exact snapshot digest | Missing quorum or stale version => denied and persisted as proposed, not approved |
| `PilotShareReceipt.v2` (planned) | metadata-only share inventory; exact owner/source/snapshot/consent/account digest; expiry; revocation/version; export class | Source body, secret fields or stale rights => no payload returned |

The `v2` labels describe proposed future contract revisions; do not emit them as supported server schemas until they are implemented, migrated and tested. Retain the existing canonical API until an explicitly versioned compatibility layer has been proven.

## Adversarial acceptance campaigns (minimum, not a substitute for unit tests)

1. DNS: localhost, RFC1918/ULA, metadata endpoints, mixed-encoding address, rebinding after redirect, IPv4-mapped IPv6 and public/private multi-A answers; all fail without fetching forbidden hosts.
2. Rights: consent revoked during live capture, report share, export queue and second tab; old token/receipt never gains downstream rights.
3. Budget: 128-request campaign with decompression bomb, slow trickle, sitemap cycle, HTTP 429 storm, duplicate worker restart, disk exhaustion and Atlas outage; finite bounded recovery.
4. Integrity: alter nested output hashes, source offsets, Atlas digests, review version and account identity; no stale share or approval survives.
5. UI: sign-in, six-stage flow, zero implicit capture, keyboard-only/phone viewport, live backend session, lost connectivity, browser restart, deleted source and safe go-back.
6. Security: source prompt injection, XSS in excerpts, formula injection in CSV, path traversal in export, hostile Markdown preview and token-in-error canaries.
7. Governance: skipped job, cancelled shard, SHA mismatch, outdated E2E, missing rights/quorum or missing SBOM must remain a hard NO GO.

## Release qualification and evidence matrix

| Evidence | Expected qualification | Status when this scope is authored |
|---|---|---|
| Exact-head focused Dragon source and Node contracts | Runner logs, captured SHA and full test counts | Prior head had passing results; new commits require rerun |
| Real authenticated Docker + Chromium E2E | Actual backend/store, 6-stage pilot, negative auth/rights | Prior head passed; requalify after scope/code changes |
| API/backend/architecture/TypeScript/lint | All shards successful on one exact SHA | Reconfirm; never infer from ancestor |
| CodeQL, secret, malware, dependency, workflow-input, artifact, hygiene | Independent policy checks with no unresolved critical issues | Must verify individually |
| Windows 11/WSL2/Docker & mobile physical devices | Independent install, network/recovery and source-rights UX | **NOT QUALIFIED by source test** |
| User rights, public-source policy, data deletion and release provenance | Signed operator/legal review and exact artifact hashes | **HOLD** |
| Rollout, rollback, failover, observability, performance | Representative load, canary, kill switch and recovery evidence | **HOLD until measured** |
| Apple M1/GPU/offline device claims | Target-device hardware and recovery acceptance | **HOLD; skipped is not passed** |

## Parallel team handoff (12 review/build agents, bounded by owner gates)

The twelve agent roles are: identity/tenant, source-rights, SSRF/network, crawler scheduler, storage/provenance, Atlas verification, decision cockpit, accessibility, Jeeves advisory integration, security/fuzzing, platform/e2e, release/provenance. These are **responsibility lanes** for independently reviewable drafts, not running agents, deployments or permission grants. They should coordinate through immutable contract documents and CI artifacts; no direct push to protected main based on an agent assertion.

**Task splitting:** a file-changing batch must nominate the exact `DR-XX-YY` IDs, expected changed paths, invariants, tests, migration impact, security/privacy assessment, baseline SHA, reviewer, stop condition, and explicit unresolved holds. Avoid a single gigantic unsafe PR merge; group orthogonal, measurable changes by authority boundary.

## Explicit exclusions and no-go rules

No new remote inference model, automatic training, source publication, unbounded internet crawl, bypass of robots/rights, unsandboxed plugins, implicit consent, unreviewed agent action, forced merge, security-gate waiver or unverified on-device claim. These omissions are deliberate safety/integrity constraints; they are not scope shortfalls to bypass. Source-only success never proves real user acceptance. **Promotion to Ready for Review is review visibility only.**
