# Offline local resource monitor

Run `python -m skeleton.ai.runtime.inference.resource_monitor --count 10
--interval 1 --operator-max 4` to stream bounded JSONL receipts from the
existing canonical OS-backed local inference sampler. Each receipt includes
measured provenance, RAM/swap/commit/PSI/thermal fields when available,
hysteretic pressure state, effective local concurrency and a SHA-256 digest.

This CLI never activates a model, reads prompts, sends network requests,
changes kernel memory policy or claims hardware qualification. Unknown
measurements remain null and are not silently replaced by zero.
The monitor is bounded to 1000 samples per invocation and a 60-second
maximum interval; Ctrl-C terminates without a background daemon.

Tests: `python -m pytest skeleton/testing/test_local_resource_monitor.py -q`.
