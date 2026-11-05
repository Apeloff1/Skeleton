# Candidate boundary: dedup

## Real admission contract

The focus is **source normalized prompt collisions and unchanged source receipts**. Each of the 24 versioned input records
targets the actual Python policy boundary before any native checkpoint
gradient is allocated or any candidate is published.

## Reproducible validation

The files under `skeleton/ai/runtime/operational_ai/native_candidate/vectors/dedup`
are strict JSON inputs. Their allow/deny expectations are independent of
the policy implementation. The module
`skeleton/testing/test_native_candidate_boundary_dedup.py` executes
each input against `native_candidate/vector_evaluator.py`.

A failed Python policy check cannot become a model-quality success.
The expected disposition is verified from the source record, and the
corpus runner refuses missing domains, duplicate IDs, unexpected filenames,
unknown schema and incomplete sets. No synthetic inference is counted.

## Operational implications

- Preserve authenticated owner, model and tokenizer identities.
- Do not allow source content to grant filesystem, network or shell powers.
- Require finite input and output budgets and explicit scope consent.
- Detect ambiguous retries and independently review uncertain writes.
- Keep training samples distinct from validation, holdout and model benchmarks.
- All checkpoint publication remains private, content addressed and held.

## Review

A successful security vector demonstrates only the cited control. It does
not establish clean installation, learned model quality, trained weights,
device performance, production rights, release readiness or exact-head CI.
