# Dragon Research Pilot — User-Usable Vertical Release Specification

**Status:** Implemented prototype path. **Production deployment and general-availability release remain unqualified.**

**Source baseline:** `Apeloff1/Skeleton`, `main` at `df96a92eafbb4730ff8207dca19c3e7596bec67f`, additive review-only PR #5281, mining the historical closed/unmerged PR #4876. The #4876 campaign stack already exists under the canonical repository owner; none of its historical branches are treated as release evidence.

**Canonical user entry:** Expo Router `/dragon-crawler-pilot` (authenticated); linked from the existing `/crawler` workspace.

**Runbook owner:** existing backend and skeleton crawler teams; no second runtime authority is created.

---

## Executive definition of complete

The Dragon pilot is a real user-facing workflow for bounded, permissioned capture of public-source content, exact-source analysis, evidence-review handoff, and personal evidence export. It is **not** a system that declares a captured page true, searches arbitrary private endpoints, gains autonomous network authority, trains a language model from unreviewed content, publishes crawled material or treats a passing local test as release certification.

The scope of this prototype is a **complete guided vertical** over the existing canonical services. The physical crawler, Mongo source store, registration of sources, full-text retrieval, metadata-only Atlas and human-review store already exist. The new screen coordinates them using their existing typed SDK and provides a coherent six-step first-user journey, meaningful failure and recovery states, and an exact source-only pilot exit receipt. It never requires users to configure an independent crawler service.

A feature is user-usable only when a signed-in user can see its real preconditions, perform it with explicit authority and finite budget, inspect its verified receipt, and recover from a missing result without fabricating success.

## Product promise and hard exclusions

1. The user selects specific public HTTPS sources and previews the **syntactic** host scope. This preview is never an SSRF/robots/rights clearance.
2. The user explicitly acknowledges capture consent and source rights. Both must be true at the create boundary. The server independently enforces consent, scope, DNS pinning, URL policy, host admission, request budgets, media limits, timeouts, robots and source-use policy.
3. The user creates an owned mission using one idempotency key. The action creates durable state but performs **zero implicit crawling**.
4. The user triggers an explicit, short canonical crawl slice. No path in the guided screen launches a new physical worker or a blind retried request with a new key.
5. The user inspects current captured sources and their use-policy/freshness records. Unreviewed external text is not an instruction or evidence of correctness.
6. The user performs bounded Atlas research and receives exact snapshot/policy/forensic/operations metadata, a human-review agenda, and a release-prototype advisory receipt.
7. The user may select text for human review through the existing knowledge subsystem. Only that subsystem records approved design references according to its own rights, review and role contracts.
8. The user may explicitly export a currently authorized source in JSON or Markdown; exported material is outside the app's revocation control, and that limitation must be communicated.
9. The user may export the pilot's **metadata-only** readiness receipt; it contains no page bodies, principal email, credentials or internal source text.
10. Publication, external training, autonomous privileged tool execution, mass crawling, private network access, factual certification, app rollout and hardware certification are **not** supplied by the new screen.

## User journey contract

### Stage 0 — account, deployment and readiness
The route is guarded by `StudioLoginGate requireAuthenticated`. The viewer sees a truthful read-only state. The editor/admin role may create and run only when the canonical service reports readiness. The first screen includes a Setup route and the existing full-operations route. If runtime services are not configured, the screen must remain accessible and show the returned action rather than crash or create a silent fake session.

A source-only user should never need to install an extra database, copy an API token into chat or start a second process from this screen.

### Stage 1 — bounded capture setup
- Inputs: mission title (1–160 chars); 1–16 unique HTTPS URLs; up to 16 short topical terms; 1–128 requests; 1–64 documents; 1–32 MiB; depth 0–3; host balancing; optional same-origin sitemap discovery.
- Defaults: 12 requests, 8 documents, 4 MiB, depth 1; host fairness enabled, sitemap discovery disabled.
- Normalization: trim lines, normalize public URL spelling using the URL parser, deduplicate URLs, count host names. Reject embedded credentials, non-HTTPS, custom ports, IP-literal targets, private/internal-looking names, fragments, control chars and unsafe size. These are helpful client preflights **only**. The canonical server rechecks all untrusted inputs.
- Authorizations: separate switches for request/storage consent and rights acknowledgement. Neither can be pre-checked nor inferred from previous missions.
- Create: one stable idempotency key is bound to the exact payload; send through `createCrawl`. A successful response presents a new durable mission and moves the user to acquisition.
- Failure: retain the original payload and key. An uncertain timeout does not permit a new create key without reconciliation.

### Stage 2 — operation and checkpoint
- Display: current session title, state, version, last committed timestamp, current consent, requests used/maximum, captured documents, bytes and quota, pending frontier and uncertain byte reservation.
- Actions: canonical refresh, at most four work steps per user trigger, pause or resume only when `session.capabilities` permits, transition to source library, or open advanced crawler for cancellation, automation and permanent erasure.
- Before a mutation: fetch the latest canonical session revision. On success use that revision as `expected_version` and generate one idempotency key. Retain the exact command if outcome is ambiguous.
- On response: reconcile committed state, then refresh the retained source inventory. Never assume an HTTP timeout means zero work happened.
- Recovery: if the session is interrupted, pending, paused, terminal or consent-expired, show the backend state. Never fabricate a worker-join or Mongo checkpoint witness, refund uncertain bytes, or resume terminal work with a new consent inferred from a prior grant.

### Stage 3 — captured source library
- Reuse the existing `CrawlerSourceLibrary` component: search, provenance, reading paged text, preserved Unicode span selection, source freshness, enabled/disabled policy, and bounded source exports.
- UI must clearly distinguish unreviewed data, active source-use authorization, capture-age expiry and unsupported remote-freshness claims.
- Editor/admin can mutate authorized source policy through the canonical backend. Viewer cannot independently grant increased rights; viewer's explicitly allowed revocation path remains governed by the existing source library.
- Any version/policy change immediately invalidates the prior Atlas receipt and any in-memory selected review draft.
- Export is explicit, source-bound and digest-checked by the canonical client. Binary/publication license is not inferred from a successful download.

### Stage 4 — Dragon Atlas analysis
- Reuse the existing `CrawlerResearchAtlasPanel`: 1–8 bounded objectives, dimension/stage choices, lexical/balanced retrieval, review-effort budgets, and deterministic metadata.
- The Atlas backend already revalidates `CrawlRun`, current protected Mongo source policies and consent, then creates forensic/operational receipts, verifies their chains and performs a second owner-scoped Mongo read before returning.
- Add `onReport` as an optional, non-authoritative frontend callback so the user journey can show the exact already-verified Atlas receipt without a second backend API or second analysis.
- Whenever the authenticated account, session or revision changes, clear the screen's old Atlas status. The callback must not be able to authorize publication, training, new network fetches, or source-payload export.
- Client checks source-owner and policy digests, release-hold booleans, all fixed stage counts, bounded counts, and an exact SHA-256 over canonicalized pilot receipt fields. Hashes provide tamper evidence only, not a second authentication system.

### Stage 5 — human review and knowledge
- Reuse `DragonKnowledgePanel` instead of duplicating SQLite knowledge owner. Candidate review can only consume a selection from a validated source span and must satisfy the existing editor, rights, purpose, decision, and idempotency checks.
- A source review and a factual claim review are separate. Human review status is never fabricated from the Atlas source-count metric.
- Local learning or game practice remains subject to the existing explicit constraints. No automatic publishing or model training emerges from the new pilot.

### Stage 6 — user exit receipt
- Advisory readiness fields are bound to the exact `atlas_digest`, `snapshot_digest`, `source_policy.digest` and `run_sequence`.
- Ten source-only internal gates include policy coverage, source-linked evidence, review queue, active-content/privacy, provenance/grounding, context bounds, durable replay custody, source robustness, measured host/resource pressure, and robots/origin review.
- Even when every source-only gate is qualified, only `ready_for_human_review` may be shown.
- Ten external release categories are always `not_qualified` inside this receipt. They require independent exact-head CI, security, devices, recovery, provenance and human evidence.
- The share action produces only digest references and gate decisions, explicitly stating no publication, training, network or product release authority.

## Canonical architecture

| Plane | Owner | Required trust boundary |
| --- | --- | --- |
| Expo experience | `frontend/app/dragon-crawler-pilot.tsx` and `frontend/src/features/Jeeves/CrawlerReleasePrototype.tsx` | User inputs are always untrusted |
| User preflight and UI states | `frontend/src/features/Jeeves/crawlerPilotFlow.ts` | Can reject, never grant network or publication |
| API transport | `frontend/src/product/crawlerClient.ts` and `frontend/src/utils/apiClient.ts` | Existing JWT/transport epoch, no credential forwarding to another host |
| Owner/policy control | `backend/core/dragon_crawler.py` | Authenticated tenant/owner, Mongo policy/revision, consent and CAS |
| Physical fetch + extraction | `skeleton/ai/webcrawler/operations.py` and existing `core.py`, HTTP/DNS/robots modules | Only canonical admission, bounded network |
| Research Atlas | `skeleton/ai/webcrawler/dragon_campaign_stack/` | Read-only, exact snapshot and current policy |
| Pilot readiness | `backend/core/dragon_campaign_pilot_qualification.py` | Metadata-only, deterministic, no mutation or new DB |
| Human review | Existing Dragon knowledge and design-reference modules | Human rights and approval are separate |
| Export | `frontend/src/product/crawlerExport.ts` and existing source export API | Digest-verified, explicit consent to user-initiated file export |
| Release governance | Exact-head CI + independent device and rollout evidence | Source-only proof cannot self-promote |

The new screen does **not** extend the list of runtime services beyond frontend/backend/skeleton/Mongo/optional Chroma, does not register a second source-of-truth, does not introduce a new model provider, does not require a user-configured local SQLite file and does not alter canonical capture rights.

## API and state contracts

| Action | Canonical client | Preconditions | Receipt |
| --- | --- | --- | --- |
| Read runtime readiness | `getCrawlerReadiness` | Signed in | available/configured/action and limits |
| List owned missions | `listCrawls` | Signed in | bounded cursor page |
| Create mission | `createCrawl` | editor/admin, two explicit consents, validated scope | durable session/version; no implicit execution |
| Load current mission | `getCrawl` | owner identity | canonical session version |
| Run finite slice | `runCrawl` | editor/admin, `can_run`, current consent, idempotency key, expected version | state, counters and retained checkpoint |
| Pause/resume | `controlCrawl` | owner role, backend capabilities and CAS | new canonical version |
| List and read sources | `listCrawlSources`, `getCrawlText` | current source-use rights | source and preserved text page |
| Search sources | `searchCrawlSources` | same scope and consent | anchored source hits |
| Review candidate | `DragonKnowledgePanel` via existing client | selected intact span, editor decision/rights | independent review receipt |
| Analyze research | `getCrawlAtlas` | complete fresh source-policy universe | Atlas source-only and pilot receipts |
| Export source | `exportCrawlSource` | current source use, digest validation | bounded JSON/Markdown user export |
| Share pilot receipt | `portablePilotReceipt` | current typed/verified Atlas response | metadata only, no release rights |

### Canonical state diagram

```text
signed-in, read-only dashboard
     |
  authenticated setup/admission
     |
  explicit consent and rights
     v
bounded mission CREATED (zero requests)
     |
  manual finite slice, canonical CAS/lease/robots/SSRF guard
     v
RUNNING / READY / WAITING / PAUSED / FAILED / TERMINAL
     |
  committed snapshot, source-use policy, retained evidence
     v
source library --> optional user export
     |
  operator-authored objective + source-policy verification
     v
ATLAS ANALYSIS (no network)
     |
  metadata-only release-pilot receipt
     v
human review queue --> independently reviewed design reference
     |
  external release gates remain NOT QUALIFIED
```

Unknown command outcomes move to a **reconcile/retry-same-key** decision. They never jump to new commands. Mutations are refused when a prior outcome is unresolved.

## Threat model and invariants

**Untrusted page attacks:** HTML, PDFs, feeds and source text can contain prompt-injection instructions, private links, scripts, false citations and rights claims. The pilot cannot interpret these as policy or code. The canonical Atlas and source inspector scan them, preserve exact spans, and hold sensitive or suspicious material for review.

**SSRF and source scope:** user-entered URLs may point to private addresses after DNS changes, redirects or address rebinding. Client syntax screening is not a security boundary. The canonical physical transport must enforce pinned DNS and public-IP policy at every request/redirect, host allowlist, robots checks, rate limits, media/byte limits and timeouts.

**Tenant isolation:** the browser must never specify tenant or owner identifiers to expand scope. Every API action binds the logged-in server principal. A session from another tenant must be indistinguishable from a missing session.

**Idempotency and CAS:** duplicate requests cannot be made unique by fabricating a key after an ambiguous response. The retry action reuses the identical key/body/version. A stale version conflict requires an authoritative refresh; it does not grant automatic retry.

**Privacy:** no source body, JWT, cookie, principal email, full serialized Atlas context, credential, raw exception stack, or deployment secret is included in readiness receipts. Only explicit source export can yield retained text under current permissions.

**Revocation:** stale, withdrawn, policy-changed, consent-expired and cancelled sources must invalidate old evidence. A previously downloaded third-party file cannot be retroactively revoked; warn users.

**Durability:** the existing Mongo snapshots/leases and separate reviewed-knowledge store are authoritative. The pilot screen's state is ephemeral and disposable. It cannot resolve interrupted workers or checkpoints itself.

**Rate and resource controls:** no unbounded polling/hidden worker, no read-all-source memory load, no user-selected arbitrary file path for ingestion, no infinite retry. All counters and page sizes obey canonical server limits.

**Trusted model use:** Jeeves and any optional model downstream must receive only permitted source context from the current policy and must not act on external text as privileged instructions. No model provides rights or certainty by prediction.

## User experience and accessibility acceptance

- Safe Area, accessible headers, labeled buttons, switches, inputs and stage buttons.
- Responsive wrapping of controls under narrow Android/iOS dimensions and desktop web.
- Keyboard can submit or dismiss inputs without unexpectedly creating a crawl.
- No external evidence is implicitly sent on mount. Opening the route fetches readiness and owner-scoped session metadata only.
- The screen remains navigable when backend, AI provider, Mongo or source text endpoint is unavailable.
- Error text does not echo raw captured pages, access tokens or server exception stacks.
- Every pending operation has a visible busy state, ambiguous-result guidance and refresh action.
- Role gating is repeated at the server; UI-only disabled controls do not count as authorization.
- A viewer sees the underlying source status but cannot create, resume, mutate rights or promote knowledge.
- A recently logged-out user must not receive stale owned sources after sign-in changes; abort in-flight reads/mutations and clear the screen.
- The metadata-only exit screen is readable and shareable without relying on color to encode readiness.
- A first-install user has quick paths to Setup and advanced recovery without needing developer tools.

## Acceptance matrix: deterministic and negative cases

| Case | Evidence required |
| --- | --- |
| First visit, no backend | Screen renders, actionable configuration error, no blank page |
| Viewer role | Existing source read allowed if server permits, create and run disabled |
| New editor mission | Explicit rights/consent and bounded input produce one durable session; no implicit requests |
| Duplicate URL | Rejected before dispatch |
| Local/private URL or embedded credential | Rejected preflight and server denial independently |
| Budget over cap | No request dispatched; bounded validation error |
| Normal run | At most four canonical steps; counters and source inventory sourced from server |
| Ambiguous POST | Exact prior key/version retained; refresh before retry |
| Concurrent control | Backend CAS conflict, no silent force |
| Consent expiry | No fresh acquisition or unreviewed content promotion |
| Withdrawn source | Not included in Atlas retrieval/review eligibility |
| Policy changed during research | Second Mongo read rejects stale receipt |
| HTML prompt injection | Evidence remains untrusted; no tool execution |
| Source exported | Content hash verified; explicit user action; no automated publication |
| Human review | Existing reviewed-knowledge role and rights gates hold |
| Atlas trace manipulated | Cryptographic/typed validation refuses receipt |
| Source-only pilot all green | Status only ready for human review; release stays false |
| External security jobs skipped | Remain unqualified; no release |
| First-install/WLS2/Windows/native unavailable | Explicit external gate hold, never inherited CI pass |
| Source privacy | No raw text, cookie, JWT or email in user pilot receipt |
| Logout / account change | In-flight effects fenced; owned content reset |

### Latency and capacity acceptance targets, not proven performance

| Dimension | Target | Required measurement |
| --- | --- | --- |
| UI first usable render | No blocking sync network on render | Device tracing, p50/p95 |
| Readiness and owner catalogue | Bounded explicit request | p50/p95/p99, timeouts, error rate |
| Short slice | Finite `max_steps=4` | Physical request count, byte reservations, tail behavior |
| Atlas inspection | No external network, capped objective/evidence universe | CPU, RSS, wall clock, p95/p99 |
| Export | Max protocol size and on-device cleanup | Payload byte bound, hash match, file cleanup |
| Backend/engine failure | Actionable status, no stale grants | Recovery test, forced disconnection |
| Crash/worker handoff | Fenced pending work and uncertain reservations | Kill/restart and CAS replay testing |
| Memory pressure | Avoid retaining full source bodies in pilot UI | Mobile memory pressure and long-session soak |

Metrics must be collected under the same workload, device, source fixtures and exact code revision. Targets are not proof of observed results.

## Release process: source-only proof versus production qualification

Release has **three distinct states**. They cannot be substituted for one another:

1. **Implemented prototype:** source code, UI workflow and tests exist in a review PR. It can be previewed by developers and signed-in staging users after deployment; not approved for general release.
2. **Pilot qualified for user testing:** all focused source and backend/client integration tests pass at exact PR head, deployment credentials and source policies are configured, and the planned user journey is independently exercised in a safe staged environment.
3. **Production release authorized:** CI and security, independent Windows 11/WSL2/Docker/native GGUF/hardware-pressure device qualification, crash/recovery/rollback, release provenance, privacy/rights, observability and launch sign-offs have individually succeeded at the same exact release SHA.

Unrelated repository CI defects are not waived by a healthy crawler test. The existing product-surface delegated SHA drift in `frontend/src/features/discourse/discourseJob.ts` is a distinct upstream artifact contract issue and must be repaired or independently resolved, not relabeled as crawler success.

### Exact-head CI checklist
- Commit identity: checkout expected pull-request head with credentials disabled, validate exact `git rev-parse HEAD`.
- Source: compile changed Python, exercise focused `backend/tests/test_dragon_campaign_pilot_qualification.py` and real owner bridge `backend/tests/test_dragon_atlas_bridge.py`.
- Frontend: Node 24 source-only journey tests and Expo strict TypeScript check.
- Core regression: `tests/test_ai_webcrawler_dragon_campaign_stack.py` plus Atlas/forensics/operational tests.
- Architecture: `check_architecture_map.py`, `check_ai_app_construction.py`, `check_capability_interfaces.py`, `check_state_topology.py`, `check_provider_bootstrap.py`; canonical AI tree parity and ownership.
- CI/security: Backend Quality, Workflow Input Security, CodeQL, Secret Scanning, Malware Gate, Artifact Policy, Dependency Review, Repository Hygiene, delegated product surface, App Foundation E2E, Merge Readiness and repository rulesets.
- Hardware: Windows 11 and WSL2 full first install, Docker clean startup, Android/browser UI flow, native GGUF where applicable, memory pressure and network fault tests.
- Custody: stale consent/withdrawal, source hash tamper, CAS conflicts, lease fencing, partial commits, Mongo restart, OS kill, deduplicated retry and recovery.
- Release: signed immutable provenance, SBOM/artifact scan, release build installation, rollback and canary evidence.
- No test marked skipped, superseded, cancelled, queued, ancestor-only, manually asserted or mocked may qualify an independent release gate.

### Focused post-build commands
```sh
PYTHONPATH=backend:. python -m unittest discover -s backend/tests -p 'test_dragon_campaign_pilot_qualification.py' -v
PYTHONPATH=backend:. python -m unittest backend.tests.test_dragon_atlas_bridge -v
python -m unittest discover -s tests -p 'test_ai_webcrawler_dragon_campaign_stack.py' -v
cd frontend
node --experimental-strip-types --test scripts/test-crawler-pilot-journey.mjs
yarn typecheck
yarn lint:ci
cd ..
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_state_topology.py
python scripts/check_provider_bootstrap.py
```

## Rollout, first-install and rollback procedure

1. Prepare a staged environment identical to a first-install user: newly provisioned DB and provider routing, no existing captured state or rights records, no cached local credentials.
2. Confirm sign-in via the existing GameForge identity. Verify roles and tenant owner isolation.
3. Open the `/dragon-crawler-pilot` route. It must load even if crawler readiness is degraded. Capture no URLs merely by visiting.
4. Test one licensed public HTTPS source, small budgets and explicit dual consent; record exact source timestamps, checkpoint identity and source policy.
5. Run one bounded slice; compare server counters to network fixtures and stored sources. Reject any unexpected private host/redirect.
6. Select a source, inspect current source-use policy, create an Atlas question and verify no external network requests are performed by Atlas.
7. Move a preserved passage to human review; verify independent reviewer permissions and no automatic knowledge promotion.
8. Export one authorized source and one metadata-only pilot receipt; inspect absence of secrets and verify bytes and hashes.
9. Force consent expiry, source withdrawal, interrupted dispatch, lost response and account change; all old receipts must be invalid.
10. Perform independent platform/CI/security/recovery/provenance qualification and obtain sign-off before production promotion.
11. Canary with smallest allowed resource budget, observe error/latency/resource telemetry and user review queues. Abort on any tenant, privacy, source-rights, authority or acknowledged-state-loss regression.
12. Roll back by reverting the additive route/pilot screen and client callback/codec while preserving canonical Mongo and reviewed-knowledge state. No new DB table or migration is required. Recheck source-policy receipts after rollback.

**No release button or automatic merge exists in the pilot; the correct production status remains held until independently qualified.**

## Release-automation blocking rules

A release workflow must produce a signed exact-head and environment-bound receipt identifying: commit, artifact digest, builder, dependency manifest, security-policy version, source-contract version, test suite and attempt, OS/device/hardware, model/runtime versions, rollback procedure and independent verifier. It must never treat `pilot_status=ready_for_human_review` as approval for production release.

The pilot's delivery is complete as an **implementation exercise** when code and docs are committed, tests actually run and the PR documents exact-head status. It is complete as a **user product release** only after the full production checklist is independently validated and deployed, not because the assistant wrote a checklist.

## Addendum — stale-session containment and safe receipt sharing (Nov 12, 2026)

The guided screen keeps an ephemeral, immutable **Atlas snapshot witness** that binds the existing verified Atlas report to the current authenticated session ID, exact session version, report digest, source snapshot digest, source-policy digest, run sequence and pilot qualification digest. This witness is a local stale-data detector only; it is neither a capability token nor a source-use permission.

Before the user intentionally shares a source-only receipt, the UI must re-read the current owned session with `getCrawl` through the existing authenticated transport and compare its version, identity and consent to that witness. A mismatch, withdrawn consent, cancelled session, report-digest change, current read failure or account switch must prevent sharing and require a new Atlas inspection. The prior receipt is invalidated in local state. The user-facing copy must clearly state that even a successfully shared receipt is **historical snapshot metadata**, never proof that source rights remain valid now.

An in-flight Atlas response must additionally match the exact session version observed at request submission, not merely the session ID observed when the response arrives. The Atlas panel already fences its request against account/revision changes; the guided page independently checks the submitted revision before retaining the report.

Read failures are handled independently: a failed source-library fetch must not suppress a successful authoritative session refresh that records expired consent or changed counters. In that case clear cached source rows, selected review spans and Atlas evidence; display the authoritative session and explain that source rights could not be verified. A readiness/catalogue failure must clear any stale positive readiness indication and disable new acquisition.

Duplicate sharing is blocked until the first share request finishes. Account-change and component-unmount fences abort outstanding authenticated receipt-refresh operations. Once a copy has left the app via the device share sheet, no revocation of that exported copy can be promised.

**Additional acceptance cases:** version unchanged/share permitted; revision increment/share refused; mismatched account/session, stale source-policy digest or report digest/share refused; withdrawn consent/share refused; cancelled session/share refused; source-list failure with good session refresh/counters displayed but evidence cleared; account transition during receipt refresh/no share; Atlas response from old version/no receipt; repeated share tap/one in-flight read.

**Limit of this hardening:** `getCrawl` does not reproduce the Atlas engine's full owner-scoped source-policy digest read. A metadata share only checks for a changed session revision and explicit consent. Any new *source usage* or factual review must still re-enter the canonical source/Atlas APIs for current per-source policy and freshness authorization. The receipt remains advisory even when every source-only gate is qualified.

## Browser-level first-user acceptance

The existing `tests/e2e/playwright.config.mjs` discovers
`tests/e2e/app-foundation/dragon-crawler-pilot.spec.mjs` when the full
production frontend/backend/docker stack is running. This test deliberately
uses a newly registered isolated user and **does not launch a crawler**.
It confirms that the exported route resolves, anonymous users see the login
gate, valid sign-in reveals six stages, source capture remains disabled without
explicit grants, loopback URL preflight fails without network dispatch, the
receipt explicitly denies release/publication/training, and responsive mobile
stage controls do not disappear.

The production-stack browser job is skipped while the PR remains draft.
Its workflow-level green status from unrelated retry-contract jobs is not
browser evidence. Run the full App Foundation E2E stack in an approved
isolated environment at the exact final head, then independently qualify
device installs, source-rights behavior, recovery and provenance. Any missing
browser execution leaves that release dimension **unqualified**.

## Independent malware and artifact gates during review-only qualification

PR #5281 is the only draft admitted to the existing read-only Malware Gate and
Artifact Policy workflow jobs. The exception is tied to the PR number,
same-repository head identity, exact source branch, and open PR action.
Forks and unrelated drafts continue to skip these resource-intensive scans.
Both security jobs checkout the exact `pull_request.head.sha` with full
repository history and verify that SHA before invoking their original scanners.
Their package-lifecycle, malware IOC, malicious active-content, artifact
placement, immutable-reference and test-regression checks are unchanged.
A new hermetic admission contract protects against future accidental widening
of this draft exception.

The exception is **evidence collection only**, not a release or automation
permission. Merge Readiness retains its original draft barrier and its protected
dependency aggregation. CodeQL security alert closure, independent device
installation, system recovery, source-rights review, signing and rollback remain
unqualified until their own executed current-head evidence exists. No skipped
gate is counted as success.
