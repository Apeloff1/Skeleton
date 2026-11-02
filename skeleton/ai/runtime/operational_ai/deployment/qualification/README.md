# Mandatory model path qualification (operator-invoked)

On Linux, with an actually approved GGUF checkpoint installed and the original
model manifest, provision a **private** AI state directory (0700). Execute the
real native first-boot probe, creating a private 0600 qualification receipt.

```bash
python -m skeleton.ai.runtime.operational_ai.deployment.qualification.cli \
  --model-root /operator/verified-model --state-dir /operator/private-ai-state \
  --tenant local --subject operator --report-dir /operator/private-receipts \
  --report-name qualification.json
```

This checks the exact model custody under llama.cpp, commits one *actual* chat
turn, closes the native model and SQLite resources, starts a new model instance,
and verifies idempotent replay and database integrity. The qualification
report includes digests and counts, never generated text, prompts, encryption
keys or a private state path. The report is a **local integrity proof**, not a
signature, a model-license proof, a safety benchmark, hardware qualification,
or release certification. It is not itself proof of generation by an
independent third-party system.

The real path is forced by the CLI; injected test doubles are permanently
marked fixture-only. Never count a fixture report as real-model qualification.
No automatic cleanup deletes private state after a failure. A failed run may
leave a held request that requires independent operator review. Never blindly
retry a native request after a crash.
