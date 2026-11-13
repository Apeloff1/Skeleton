# Dragon research pilot — source-bound release qualification

Status: **prototype implementation, not approved for release**. Source: closed, unmerged PR #4876 at `f649032f66496c5afc4a6dd413e31602ec1567b9`; current implementation uses the canonical components already present on `main`, not a cherry-pick of old branch history.

## Owner and vertical
The only physical crawler remains `skeleton/ai/webcrawler/operations.py` under the existing canonical crawler owner. The only durable source/capture/policy state remains the tenant/owner-fenced `backend/core/dragon_crawler.py` Mongo authority. The existing Dragon Atlas frontend `frontend/src/features/Jeeves/CrawlerResearchAtlasPanel.tsx` calls the backend route that performs an owner-scoped Atlas inspection; there is no second network service or worker. The pilot qualification module is a **read-only presentation** of the same verified Atlas metadata.

## User journey
1. Sign in with the existing authenticated GameForge identity, select an existing owned crawler session with current capture consent.
2. Select bounded operator-authored objectives, retention limits, and retrieval mode in the existing Crawler Research Atlas panel. This uses **already retained captures only**.
3. The application checks the full persisted canonical CrawlRun, the protected Mongo source-policy universe and current consent before analysis.
4. Existing policy-first Atlas assembles deterministic retrieval, citations, review queue, operations, forensics and a hash-linked trace. It verifies the trace and forensics, then re-fetches Mongo source and policy authority before returning.
5. The additive pilot qualifier validates digests, counts, stage chains, source text redaction, trust flags and no privileged side effects. It returns bounded check statuses, operator repair actions, and a digest bound to the exact Atlas/snapshot/policy identities.
6. UI renders **pilot readiness for human review**, withheld conditions, and the **separate unqualified production release gates**. It must never describe the source-only receipt as factual verification, permission for training, authorization for publication, permission to dispatch work, or first-install certification.
7. Any changed source, consent, ownership, policy revision, or application code invalidates the previous receipt. Every subsequent action goes back through the canonical protected authority.

## Check and hold semantics
A pilot may be ready *for human review* only when its source policy is current and complete, its indexed evidence is bound, work has a bounded human-review queue, forensics show no active-content/privacy/grounding defects, replay uncertainty is resolved, the source set covers multiple hosts, measured capacity is present, and the existing host/robots analysis contains no stale authority. These are **advisory projections**, never independent evidence of remote truth or safe HTTP eligibility.

Release is always held until separate exact-head evidence: Merge Readiness, Backend Quality, frontend typecheck/App Foundation E2E, architecture/source-tree parity, Workflow Input Security, CodeQL, Secret Scanning, Malware/Artifact/Dependency/Hygiene, Windows 11/WSL2/Docker/native device, crash recovery/rollback/provenance, and independent human source-rights/factual review.

## Implementation depth (L00–L13)
- L00 ownership: existing crawler and Mongo authority; backend presentation-only qualifier.
- L01 architecture: no new runtime service, provider, database, route owner, or network path.
- L02 contracts: versioned `campaign_pilot_qualification.v1` receipt with schema, digest, typed checks and explicit non-authorities.
- L03 admission: authenticated tenant scope, consent and source-policy validation occur in the existing Atlas boundary before the qualifier.
- L04 control flow: capture -> verified Atlas -> independent metadata checks -> metadata-only UI.
- L05 state: no new persistent state; the receipt is derived and must be regenerated at every use.
- L06 security: no raw external text, secret, page instruction, or user identity; no training/publication; denied on authority-field drift.
- L07 recovery: uncertain bytes, pending dispatch, journal gaps and clocks retain holds; no automatic retry or unsafe budget refund.
- L08 operations: structured checks, next actions, deterministic digest and release-check matrix with explicit pending status.
- L09 performance: constant-size bounded metadata projections, at most 10 local checks and 10 external gates; no extra external I/O.
- L10 tests: hermetic positive, source withdrawal, budget/recovery, tamper, missing evidence, policy, authority and privacy regressions.
- L11 deployment: additive backend field with backwards-compatible optional frontend reading; rollback by reverting the projection, no migration.
- L12 operator: inspect each blocked check, repair only in the canonical owner, re-run the original Atlas against current Mongo authority, then re-qualify.
- L13 exit: all exact-head validators, frontend/typecheck/e2e, security/CodeQL, device and recovery/release-provenance evidence are required; no inherited success or skipped checks qualify.

## Focused checks
Run after all implementation files are present:
```sh
PYTHONPATH=backend:. python -m unittest backend.tests.test_dragon_campaign_pilot_qualification -v
python -m unittest discover -s tests -p 'test_ai_webcrawler_dragon_campaign_stack.py' -v
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
cd frontend && yarn tsc --noEmit
```
The above commands are an **acceptance plan**, not evidence they ran. Test-only green is not a release authorization.

Rollback: revert the qualifier import and additive API metadata property, then revert the optional UI and client presentation. No schema migration or worker state change.
