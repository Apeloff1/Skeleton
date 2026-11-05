# Retrieval operational AI assurance module

## Purpose and trust boundary

This domain provides **twelve independent computations** over supplied numerical
observations. Each computation checks exact field membership, finite nonnegative
counters, a bounded result, and an input SHA-256. It never imports model text,
issues tool grants, invokes a provider, or declares a model qualified for release.

## Measurement inventory

| Contract | Meaning | Required counters |
|---|---|---|
| `precision_k` | Fraction of retrieved chunks independently relevant | `relevant_retrieved,retrieved` |
| `recall_k` | Recall of known relevant approved chunks | `relevant_retrieved,relevant_total` |
| `mrr` | Mean reciprocal rank across supplied queries | `reciprocal_rank_sum,queries` |
| `ndcg_k` | Normalized discounted retrieval gain | `discounted_gain,ideal_discounted_gain` |
| `query_coverage` | Coverage of accepted retrieval questions | `answered_queries,total_queries` |
| `stale_source_fraction` | Sources revoked or changed before commit | `stale_chunks,selected_chunks` |
| `chunk_overlap_ratio` | Redundant characters across indexing chunks | `overlap_characters,all_chunk_characters` |
| `evidence_bytes_per_hit` | Evidence payload bytes per retrieval hit | `evidence_bytes,retrieved_hits` |
| `unique_document_fraction` | Diversity of document origins in context | `unique_documents,retrieved_hits` |
| `source_revocation_rate` | Share of approved knowledge later withdrawn | `revocations,approved_documents` |
| `index_density` | Index entries per source document | `indexed_chunks,source_documents` |
| `citation_identifier_validity` | Verified citation-token membership in evidence | `valid_citations,citations_checked` |

## Correct invocation and failure behavior

Import the named module from `skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.retrieval`
and call `measure()` with exactly the required numeric counters. An unexpected,
missing, nonfinite, Boolean, negative, or oversized value is rejected.

Counters need independent source custody: production deployments should derive
inputs from the authoritative SQLite spine, Linux kernel observations,
operator-authorized model metadata, or separately executed evaluation data.
These computations do not verify their own external inputs and are **not**
release evidence unless the input collection is independently attested.

## Regression guarantees

Each contract is covered by independent exact-oracle, deterministic fingerprint,
missing-field, unexpected-field, Boolean, negative, nonfinite, oversized,
zero-denominator and wrong-input-type regression tests. They are run only
after the implementation is complete. Never interpret a skipped real-model
test as a passing result.

## Integration

The domain registry exposes a closed set of names. The `measure()` function
can support a future readiness report but must remain observational. For
release admission, consult authoritative final-head workflow checks and
real checkpoint/hardware qualification rather than these scores.
