# Dragon crawler — governed acquisition, revision evidence and exact-span distillation

**Implemented 2026-10-12 (UTC).** Scope: 248 curated editorial source candidates, canonical owner-scoped policy workflow, resource-granted article acquisition, content-version custody, and unreviewed source quotation handoff. The implementation does **not** prove the sources have been fetched or independently reviewed.

## Production change

The previous milestone registered the 248 source candidate URLs across 22 research families. This milestone adds a **network-capable, consented acquisition worker** and **durable acquisition ledger** while preserving the existing Dragon policy queue and signed idle hatchling resource controls.

**1. Entry permission.** Actual capture requires a trusted authenticated worker, the signed adult Dragon nest with the three unlocked hatchlings, explicit idle-only consent, current resource telemetry and a real shared global resource grant. It additionally requires a previously completed, nonexpired Dragon almanac **policy** step whose ledger evidence confirms robots, terms, reference permission and SSRF checks. A source URL alone is not permission to crawl.

**2. Safe source transport.** `acquire_canonical_technical_article` only accepts the article lane. It calls the existing `CrawlEngine`, `CrawlBudget` and `SafeHttpFetcher` with socket-bound DNS, one allowlisted HTTPS host, robots.txt, zero redirects and single-document constraints. The same live worker checks owner, consent, background activity, ticket expiry, preemption and device limits before every HTTP request, and checks again before committing the capture. Every trusted worker exit path, including unsafe transport configuration or a denied policy receipt, acknowledges a real stop and releases its capacity. Robots crawl-delay beyond five seconds defers work to a separate scheduler.

**3. Content-bound revision history.** `DragonSourceCaptures` retains up to 64 capture events per source, with an owner-bound digest chain, checked head, canonical source ID, exact fetched URL, observed timestamp, SHA-256 digest of real extracted text, original extraction/provenance metadata and measured HTTP response length. Changes are classified `new`, `unchanged` or `changed`. Identical content never becomes a fresh knowledge improvement. Same-request retries with identical idempotency identity are safe; conflicts, timestamp rollback, tampering and broken history fail closed.

**4. Evidence-only distillation.** Newly observed or changed texts produce at most six short, strictly verbatim quote proposals. Spans refer to the exact extracted characters and have deterministic task-topic relevance ranks. The journal refuses mutated quote spans. Quoted text is not a verified fact; no synthetic citation, hallucinated summary, independent corroboration or automatic model improvement is credited.

**5. Existing canonical sequential authority.** A separate fetch-stage claim can be completed from a current capture with a real measured HTTP response byte count and the source text hash. An extract-stage claim can then be completed using the exact quote-span map and version identity. These are the existing five workflow stages (`policy` → `fetch` → `extract` → `analyze` → `canonical_review`), and only the first three are established by this acquisition milestone. Analysis, rights renewal, independent reviewers, Wiki/HOAG verification and actual model-promotion experiments remain distinct mandatory gates.

## Included files

| File | Purpose |
| --- | --- |
| `skeleton/ai/game_builder/dragon_technical_source_captures.py` | Durable source text capture lineage and exact-span review packets |
| `skeleton/ai/game_builder/dragon_technical_source_acquisition.py` | Real, bounded network fetch adapter under live idle and global resource checks |
| `skeleton/ai/game_builder/dragon_technical_source_cli.py` | Trusted capture history, current review packet and owner capture census inspection |
| `tests/test_dragon_technical_source_captures.py` | Custody, rights, deduplication, stage receipts, corruption, and tenant isolation |
| `tests/test_dragon_technical_source_acquisition.py` | Offline transport tests for policy-first HTTP, robots handling, consent revocation, and grant release |
| `.github/workflows/dragon-ai-verification.yml` | Includes new Python modules in the existing Dragon CI suite |

## Local operator commands

```sh
python -m skeleton.ai.game_builder.dragon_technical_source_cli capture-census \
  --database /path/to/studio.sqlite --owner studio --trusted-local-operator

python -m skeleton.ai.game_builder.dragon_technical_source_cli capture-history \
  --database /path/to/studio.sqlite --owner studio --source-id source-<64hex> \
  --trusted-local-operator

python -m skeleton.ai.game_builder.dragon_technical_source_cli capture-review \
  --database /path/to/studio.sqlite --owner studio --source-id source-<64hex> \
  --trusted-local-operator
```

Add `--include-captured-text` only for an operator who is authorized to inspect retained reference excerpts and documents. CLI operation never starts network acquisition.

## Test and acceptance status

The new regression modules contain **17 tests** (12 journal/extract/fetch-stage tests and five offline-network worker tests). Tests construct actual `CrawlDocument` output from the repo's extraction primitive and validate that the policy stage precedes real capture, that unchanged revisions do not recredit knowledge, and that source tampering or unsafe transport is rejected. The `Dragon AI Verification` workflow is configured to execute these modules; GitHub's CodeQL status is not a substitute for their runtime pytest result.

### Open completion work

Capture is now implementable, but production cannot claim active crawling without a live service configuration, official source-site permission evidence, real device idle detection and telemetry, scheduler deployment, cross-process crash recovery, a bounded robots-delay queue, authorized periodic recrawls and verified source independence. Videos still require separate media-authorized workers. The `analyze` and `canonical_review` stages must independently examine each quotation, resolve contradictory or superseded source versions, assign original-game-building relevance and compare measured model performance in an adversarial sandbox before any approved weight promotion.

**No live sources were downloaded in this work turn.** Registered URLs, executable acquisition capability, and independently verified knowledge are three distinct states.
