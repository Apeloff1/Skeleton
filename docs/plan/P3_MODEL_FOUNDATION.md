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


## FLGB-02 text/token pipeline audit (2026-10-08)

Current gap: `TextTokenPipeline.stream` retains a duplicate raw-chunk list and tokenizes raw text before normalized preparation, while `verify_round_trip` encodes normalized text twice. Proposed bounded single-feed/single-encode repair is pending repository write approval and exact-head regression verification. Do not mark this volume complete until the repair is merged, chunk-partition/Unicode tests pass, and CI verifies the resulting head.
