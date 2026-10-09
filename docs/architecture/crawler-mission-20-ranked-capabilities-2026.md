# Crawler: twenty ranked mission capabilities (October 2026)

This increment implements **20 executable Python operations** in the
policy-bound crawler's AI file tree. Priority is determined by the mission:
building a functioning native text-to-token data feed that can learn from
authorized, attributable research without conflating repetition and
independent evidence. Ranking describes **expected mission usefulness**,
not calling order. A caller must sequence permissions, ingestion, analysis
and training gates in the correct causal order.

The ranking is introspectable from
`skeleton.ai.webcrawler.CAPABILITY_CATALOG`. Every entry maps to a real,
individually testable function; no entry represents a proposed-only method.

| Rank | Capability | Why it matters for functional AI/LLM |
|---:|---|---|
| 1 | `encode_verified_tokens` | Native-model text→token IDs with injected tokenizer and exact roundtrip, not guessed word counts |
| 2 | `require_training_grant` | Deny training without source-, revision-, purpose- and expiry-bound permission |
| 3 | `curate_training_fragment` | Licensed, query-relevant, content-addressed passage selection with PII masking and injection quarantine |
| 4 | `scan_untrusted_instructions` | Surface instruction injection from web documents rather than executing it |
| 5 | `mask_personal_data` | Coordinate-preserving email/phone minimization before examples are fed to a model |
| 6 | `segment_passages` | Bounded, overlapping source character spans for evidence retrieval and tokenization |
| 7 | `pack_token_windows` | Budget-correct native-token windows with deterministic IDs and overlap |
| 8 | `assign_dependency_splits` | Keep identical content and declared derivative sources out of cross-split leakage |
| 9 | `rank_query_passages` | Grounded relevance ordering with reproducible original offsets |
| 10 | `near_duplicate_groups` | Detect near-copied sources beyond identical SHA-256 texts to prevent false corroboration |
| 11 | `exact_revision_groups` | Collapse verbatim duplicate captures with hash integrity verification |
| 12 | `compile_training_manifest` | Reproducible token, provenance, grant and data-split accounting |
| 13 | `rank_acquisition_candidates` | Spend finite requests and bytes on higher predicted information gain |
| 14 | `allocate_host_dispatches` | Host fairness and scheduled readiness; refuse forged admission flags |
| 15 | `plan_adaptive_recrawls` | Revisit volatile, valuable sources sooner without turning a planner into a fetcher |
| 16 | `locate_uncertainty_cues` | Find negations and hedges that require contextual assessment |
| 17 | `extract_citation_candidates` | Extract reproducible DOI and canonical URL verification targets |
| 18 | `measure_information_quality` | Flag low-content and repetitive pages before allocating expensive analysis |
| 19 | `balance_decade_windows` | Prevent token corpora from ignoring older eras or overfitting abundant recent sources |
| 20 | `decide_mission_stop` | Stop sufficient research, escalate novelty plateaus, and never confuse budget exhaustion with truth |

## File layout and execution classes

- `dragon_mission_quality.py`: public source-quality scans, training-grant
  checks, PII masking, citation discovery, deduplication and evidence ranking
- `dragon_mission_token_feed.py`: curating rights-bound fragments; real-tokenizer
  adaptation, exact token windows, provenance cluster splits, historical cohort
  balancing, immutable training manifest
- `dragon_mission_scheduler.py`: bounded information-gain acquisition ranking,
  host-fair dispatch proposals, adaptive recrawl intervals, mission-stop decision
- `dragon_mission_catalog.py`: ordered, typed, lazy-resolvable registry of
  the twenty callable capabilities
- `tests/test_ai_webcrawler_dragon_mission_*.py`: focused regressions,
  including invalid permission, injection patterns, malformed token output,
  split leakage, forged dispatch admission and stalled research

No new network client or provider dependency is introduced by these modules.

## Native model feed: an exact, permissioned pipeline

1. An upstream crawler enforces SSRF restrictions, robots/terms, redirect
   safety, host cooldown and fetch budgets; it emits a validated
   `CrawlDocument`.
2. An authorized rights reviewer attaches a **trusted** `RightsGrant` scoped
   to that content digest, URL, purpose and expiry. A string in a web page
   claiming permission is not a trusted grant; the upstream source of the
   grant must itself be authenticated.
3. The `curate_training_fragment` path checks the grant and rejects
   known prompt-injection patterns; it preserves passage offsets and
   masks detectable personal information before tokenization.
4. The **real native model tokenizer** is injected via
   `encode_verified_tokens(fragment, encode, decode, tokenizer_id=...)`.
   IDs must be bounded non-negative integers and the decoder must exactly
   reproduce the curated text. The module does **not** pretend UTF-8 bytes
   are native tokens; byte encoders are suitable only as test fixtures unless
   that is deliberately the model's actual tokenizer.
5. `pack_token_windows` uses the verified IDs, not character or word counts,
   to enforce context geometry and produce deterministic source-anchored IDs.
6. `assign_dependency_splits` uses the crawler's existing transitive
   provenance closure so known mirrored/derived sources cannot leak across
   train/validation/test. Unobserved off-platform common ownership cannot be
   proven absent by this algorithm; publisher attestations should be
   supplied upstream.
7. `balance_decade_windows` provides bounded year-bucket down-selection
   based on externally grounded publication years. It does not invent dates.
8. `compile_training_manifest` verifies per-source assignment, rights
   fingerprints, token-window shape and experiment split consistency. It
   never executes gradient updates or automatically promotes research.

### Minimal example

```python
from skeleton.ai.webcrawler import (
    RightsGrant, curate_training_fragment, encode_verified_tokens,
    pack_token_windows, assign_dependency_splits,
    compile_training_manifest,
)

# document: upstream-valid CrawlDocument
# grant: authenticated rights record with digest, source, purpose and expiry
fragment = curate_training_fragment(
    "source-A", document, grant, purpose="native_model_training",
    now=trusted_timestamp, query="query from the approved mission",
)
tokens = encode_verified_tokens(
    fragment, native_tokenizer.encode, native_tokenizer.decode,
    tokenizer_id="model-tokenizer-version",
)
windows = pack_token_windows(tokens, max_window_tokens=2048,
                             overlap_tokens=128)
splits = assign_dependency_splits(
    independently_attested_manifest, seed="experiment-01",
)
manifest = compile_training_manifest(
    "native-pretraining", windows, splits, authorized=True,
)
# Human governance, revalidated grants and a training implementation
# remain prerequisites. Do not promote this manifest automatically.
```

## Acquisition planner authority boundaries

The acquisition scorer ranks a list of **requests for consideration**;
it cannot grant permission to fetch them. The host dispatcher **revalidates**
the URL and destination against policy even if a caller forges a
`PrioritizedAcquisition(admitted=True)` object. The executor must still
load fresh robots, DNS/IP resolution, redirect and host-budget policy.

Adaptive recrawl calculates due times using recorded volatility, importance
and consecutive unchanged observations, respecting hard interval bounds.
It does not schedule a background automation or make HTTP calls.

Mission stopping distinguishes three important outcomes:

- Evidence meets conservative research review criteria: stop new fetch
  attempts and submit for human review.
- Available budget is exhausted with unresolved questions: stop external
  requests but report unresolved evidence and escalate.
- Recent information gain stays below an explicit threshold: stop the
  repetitive low-value acquisition strategy and escalate. This is *not*
  approval to publish the uncertain claim.

## Risks, limitations and deployment work

- Pattern-based injection and PII scans cannot catch all prompt-injection
  language or personal data; they are screening signals. The runtime must
  always treat source content as data rather than instructions.
- Heuristic near-duplicate similarity can join unrelated pages, or miss a
  paraphrase. It is an alert, not proof of source dependence or ownership.
- Rights grants are structurally validated, not cryptographically verified.
  A trusted authorization system must issue and periodically revalidate them.
- Historical cohort balancing relies on externally established publication
  years. Inferred dates must not silently be treated as ground truth.
- Source independence is conservative only for known content, lineage and
  publisher relationships; off-platform shared authorship may still exist.
- The tokenizer is an injected interface, not a bundled pretrained model.
  Training the native model and evaluating it require separate execution.
- No new API routes or background jobs are installed by this increment; the
  capabilities are now importable in the crawler plane and ready for
  authorized runtime integration.

## Verification and landing dependencies

Run:

```bash
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  tests/test_ai_webcrawler_dragon_mission_quality.py \
  tests/test_ai_webcrawler_dragon_mission_token_feed.py \
  tests/test_ai_webcrawler_dragon_mission_scheduler.py \
  tests/test_ai_webcrawler_dragon_mission_catalog.py
python scripts/check_ai_webcrawler.py
```

The exact-head `AI Webcrawler Research Plane` GitHub workflow includes
all `tests/test_ai_webcrawler_*.py`. The existing provenance custody (#3538)
and recrawl revision (#3540) PRs are upstream dependencies for this branch.

**Merge order:** #3538 → #3540 → this capability PR, with exact-head CI
success, code review and actual base-diff reconciliation between steps.
Queued or skipped checks do not certify passing tests.
