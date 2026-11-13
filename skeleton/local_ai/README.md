# Local AI compatibility seams

This package is a legacy adapter inventory, **not** the authoritative inference
runtime. Creating `LocalAIComplete` does not load a GGUF model or establish a
reviewer, tokenizer, shared guard epoch or writer fence.

Run `python -m skeleton.local_ai.bootstrap_cli --status` for a conservative
diagnostic. It exits 2 with `LOCAL_INFERENCE_NOT_BOUND` until the legacy
facade is replaced by a verified binding. Use the canonical
`skeleton/provider_runtime.py` path for model dispatch; never treat a
synthetic bridge string as model output.
