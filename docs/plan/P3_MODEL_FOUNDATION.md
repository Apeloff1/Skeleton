# P3 Model Foundation

This slice implements the executable foundation owned by
`P3-MODEL-FOUNDATION-01` without claiming masterplan maturity or independent
sign-off.

It adds rights-bound training datasets, deterministic local training receipts,
reloadable learned model artifacts, independent promotion requirements,
correction-aware research-source lineage, an engine-neutral simulation adapter
whose rollouts are explicitly non-real evidence, and one sanitization contract
for document/image/audio/video intake.

The portable reference trainer is a proof of a real local training path: it
learns transition weights from corpus data and reloads the content-addressed
artifact without provider credentials or network access. It is not a claim that
a small reference n-gram model is the target quality model.

Run:

    python -m unittest -q skeleton.testing.test_p3_model_foundation


## FLGB-02 canonical integration status (2026-10-08)

The native text-to-token and temporal-corpus pipeline was landed onto `main`
by #3521, based on the strict tokenization changes in #3500, with model/causal
batch deserialization hardened by #3522. Native generation now also supports
pretokenized sequences and streaming text feeds (#3517), and cancelled/error
usage receipts avoid reentering tokenizer code (#3523).

The pipeline validates normalized UTF-8, deterministic chunk-boundary-independent
text ingestion, token/window/batch provenance, causal target construction,
historical/decade training signals, and bounded candidate-only training receipts.
The stream path consumes a bounded feed once, normalizes before tokenization,
and does not retokenize the raw feed in a second pass.

**Validation is pending:** Code and focused tests have been committed, but the
latest exact-head `AI Text-to-Token Integration` workflow has not yet reported
a passing pytest result. Do not sign `P3-MODEL-FOUNDATION-01` complete merely
because GitHub accepted a merge. Before signing, run and retain results for:

- `python -m unittest discover -s tests/flgb -p 'test_flgb_02_text_normalization.py' -v`
- `python -m pytest -q tests/ai_pipeline/test_text_pipeline.py`
- The exact-head FLGB masterplan, native inference, provenance, and security gates

This is an implementation checkpoint, not frontier-model equivalence or evidence
that trained production weights exist.
