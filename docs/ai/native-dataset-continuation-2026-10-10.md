# Verified dataset to native checkpoint continuation

The existing offline application adapter now connects its deterministic
prepared corpus to `local_ai_improvement.improve_local_model`. The adapter
adds no trainer, model registry, provider boundary or promotion authority.

```bash
python -m skeleton app local-ai \
  --improve-dataset /path/prepared \
  --improve-model /path/parent.json \
  --output-model /path/new-candidate.json \
  --verify-sources /path/original-documents \
  --epochs 3 --json
```

Use the repository's CLI entry point; the frozen application accepts the same
arguments after `Skeleton.exe --offline-command local-ai`. The Python API is
`improve_native_dataset(checkpoint, dataset_directory, destination, epochs=1,
original_sources=None, protected_suite=None)`. `--protect-suite` continues to
require the independent category benchmark before publication. Raw corpus
switches and unrelated inference/evaluation modes are rejected in this mode.

## Construction and operating contract (L00–L13)

- L00/L01: Existing application corpus adapter owns file admission. Native
  improvement remains the canonical owner of training and candidate admission;
  the optional benchmark owner evaluates protected categories.
- L02: The dataset v1 manifest and its verification report are unchanged. A
  `skeleton.ai.native_dataset_improvement.v1` envelope contains `dataset`, the
  existing replay-compatible `improvement` receipt, and snapshot-use status.
- L03: All explicit source selection, bounds, vocabulary admission, held-out
  separation and no-replace publication remain enforced. This local CLI does
  not grant rights or consent for a service tenant. The candidate must be
  outside dataset and optional original-source directories.
- L04/L05: Verification returns both evidence and the exact bytes it checked.
  The bounded (32 KiB per corpus) bytes are copied to private temporary regular
  files, consumed by the existing bounded CPU trainer, and removed on success
  or failure. There is no verify-then-reopen race on the operator's corpus.
  Dataset files are authoritative for this selected snapshot; temporary files
  are derived. Source verification is a snapshot assertion, not a lasting lock.
- L06: No network, credentials, provider SDK or background acquisition occurs.
  Hostile manifest, corpus mutation, symlink and split-contamination checks
  remain fail closed. Retention of the operator's originals remains explicit.
- L07: Invalid data, non-improvement and protected regression propagate as
  errors; the wrapper never retries training or promotes a rejected model.
  Protected benchmark admission errors use the improvement owner's typed error.
  Original weights remain the rollback source. Exact native receipt replay
  continues to work on the nested `improvement` object and original corpus bytes.
- L08/L09: JSON binds dataset ID, manifest/train/validation digests, source
  verification status, parent/candidate identities, epochs, steps and measured
  perplexities. Temporary storage is bounded by corpus limits. No throughput,
  p95 latency or large-model capability is asserted from these toy CPU tests.
- L10: Tests execute real native training, independent receipt replay, frozen
  CLI routing, pre-training tamper refusal, and replacement after verification
  proving the captured bytes are used. Existing training/benchmark/replay
  regressions remain required, as do exact-head hosted assembly gates.
- L11/L12: No migration or automatic installation/promotion occurs. Preflight
  with `--verify-dataset` and optional `--verify-sources`, retain the parent,
  inspect the returned receipt, and serve only an explicitly selected candidate.
  Extract `improvement` as the existing replay receipt. Roll back by selecting
  the retained parent. Interrupted commands leave no wrapper temporary corpus;
  operating-system forced termination may require normal temp-directory cleanup.
- L13: Passing local held-out improvement is evidence for this selected corpus,
  not independent model quality, historical disjointness or enterprise grade.
  Existing masterplan, dossier, hardware and hosted CI gates still apply.
