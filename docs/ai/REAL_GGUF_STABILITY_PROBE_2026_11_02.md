# Real native-GGUF endurance probe and capacity integration

`python -m skeleton.ai.runtime.operational_ai.model.qualification.cli --model-root /private/approved-model --result-dir /private/reports --report-name run-001.json --tenant local --subject operator --trials 12`

This operator-only runner opens an independently approved model manifest, acquires a kernel-held **global capacity lease** for the exact manifest, starts the **real GGUF subprocess**, and executes a fixed, bounded, original set of harmless prompts. It never downloads weights, constructs fake predictions, executes model-selected tools, imports private conversation prompts, or falls back to a hosted model. A suite running a synthetic `Generated` fixture verifies the harness contract, not the quality of any actual language model.

Every trial checks the backend's fresh headroom and exact model lease before inference. It verifies model/tokenizer digests, native response SHA-256, legal output length, token counts, finite monotonic elapsed time and supported finish reasons. At most 256 trials can be requested, with finite timeouts. Any process failure immediately aborts; there are **no automatic retries** after ambiguous native execution.

The result file is a single private, atomically no-clobber JSON report. It contains model and tokenizer digest, timing percentiles, aggregate tokens/sec, finish reason and SHA-256 of output, but **never** generated text, model paths, secrets or user conversations. A failed trial does not publish a false success report. Any partial file publication is a hold requiring independent review.

The underlying report status is `backend-receipts-observed-not-release-certified`; only the real-model CLI, which activates an independently approved GGUF image, may additionally report `real-model-observed-not-release-certified`. A passing probe does **not** establish hallucination resistance, model accuracy, tokenizer provenance independent of the GGUF image, power/thermal performance, GPU VRAM headroom, exact first-install operation, target-device reliability, release policy or the genuine 1.9 GB ecosystem archive.

This probe must run on approved real GGUF weights before its results can be counted as native acceptance. A test-only fixture `Generated` is deliberately not a release qualification. Use this together with the conversation/restart/replay and security gate suites at the final GitHub SHA.
