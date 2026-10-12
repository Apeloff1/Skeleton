# Resumable game-knowledge acquisition

The existing `CrawlEngine` and `KnowledgeDrivenGameBuilder` now expose bounded,
non-blocking acquisition turns. Previously, the builder repeatedly called
`step(now=the_same_timestamp)` even when every host was cooling down. Recursive
links and pre-existing frontier items could also exceed the later indexing cap,
raising an error only after fetching and partially indexing the batch.

`discover_and_acquire_batch` returns documents plus a scheduling report.
`resume_acquisition` continues the same frontier without another discovery
request. The existing tuple-returning `discover_and_acquire` and
`acquire_game_documents` APIs remain available.

## Scheduling and operator use

Call discovery once with an authorized policy-bound crawler. Inspect
`stop_reason`, `steps`, `requests`, `response_bytes`, `pending_sources` and
`next_ready_at` on the returned batch. Resume with actual current time; never
substitute the future eligibility timestamp for a real clock merely to bypass
a host delay.

| Stop reason | Operator/scheduler action |
| --- | --- |
| `frontier_empty` | No queued work remains. |
| `deferred` | Schedule a subsequent turn no earlier than `next_ready_at`. |
| `document_limit` | Yield after indexing the admitted batch; queued work remains. |
| `step_limit` | Yield after the bounded number of attempted frontier steps. |
| `budget_exhausted` | Stop; a scheduling hint cannot authorize a new budget. |

The document ceiling is checked before each step, including recursive pages.
Official seeds and discovery proposals share the configured source ceiling.
Proposal iteration and source prioritization are bounded even when the input
generator emits only duplicates or policy-rejected URLs.

## VOL-137 ingestion integration obligations

This increment supports the existing ingestion owner; it does not replace the
canonical ingestion engine or introduce a new state domain or runtime service.

| Level | Implementation and boundary |
| --- | --- |
| L00 ownership | Existing webcrawler acquisition and game-builder knowledge index. |
| L01 dependencies | Existing crawler fetcher, policy, frontier, store and SQLite index. |
| L02 contracts | Additive immutable batch report; existing document tuple APIs retained. |
| L03 admission | Builder requires authorization; malformed budgets fail before discovery/fetch. |
| L04 runtime | Inspect readiness, enforce budget, step, validate document, then index bounded batch. |
| L05 state | Existing checkpoint and source/passage tables; no new schema or migration. |
| L06 security | Existing robots, redirect and egress checks still own network admission; reports grant no training authority. |
| L07 recovery | Caller checkpoints/restores the existing crawler; cooldowns and retries survive that checkpoint. |
| L08 observability | Report actual charged request/byte deltas, pending attempts and explicit stop reasons. |
| L09 economics | Bounded attempts/documents/proposals; delayed batches do zero fetches and do not spin. Readiness inspection is linear in frontier size. |
| L10 evaluation | Local fake-transport integration tests exercise retries, cooldowns, multi-host progress, indexing and recovery. |
| L11 rollout | Additive API; rollback code without deleting checkpoints or indexed source history. |
| L12 controls | Caller owns invocation, clock, scheduling, checkpoint durability, authorization and crawl budget. |
| L13 exit | Local correctness increment; no production SLO or enterprise-superiority claim. |

Index persistence and crawler storage are still separate commits. If indexing
fails after a fetch, retain and replay captured documents through
`ingest_captured_documents`; this change does not add a distributed transaction
or an automatic reconciliation worker. The caller must use an owner-scoped
index and approved transport. No live source acquisition, source approval,
model training or weight promotion is claimed by the synthetic tests.

Validation command:

```sh
python -m pytest -q tests/test_game_acquisition_batches.py tests/test_ai_webcrawler_game_knowledge_build.py tests/test_ai_webcrawler_redirects.py tests/test_ai_webcrawler_robots_budget.py tests/test_ai_webcrawler_stress.py
```
