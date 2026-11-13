# Real local GGUF + SQLite cold-reopen acceptance (operator procedure)

This is a **real-device test command**, not a source-only simulator and not a
release certification. The prior `scripts/run_ai_laptop_native_e2e.py` ran a
first-turn acceptance function without passing the installed GGUF receipt or
`require_real=True`. It also stripped exact private stdin bytes and emitted a
second, unguarded result after native teardown. That path could never qualify
the full real-source contract.

The script now delegates **exclusively** to the authoritative
`laptop_runtime.cli --mode cold-reopen`. No parallel inference or database
owner exists. The canonical runner enforces these transitions:

1. All arguments and source paths admitted before reading private stdin.
2. Independently verified installed model bytes, rights, tenant and subject,
   manifest and a capacity-admitted **live isolated** GGUF child.
3. Exactly one native effect and independently committed SQLite replay.
4. Full first-worker teardown, then a new source/rights/capacity admission.
5. An independently activated second live native worker reads the existing
   committed SQLite record without any second generation.
6. Exact principal, source, model/tokenizer and digest checks after replay.
7. Bounded JSONL publication inside the second source/lease guard, before
   worker teardown; errors fail closed without replaying uncertain effects.

## Device command

From a clean, trusted checkout with a separately installed model whose
**rights are independently approved** and with private state/capacity
directories preconfigured by the standard installer:

```bash
python scripts/run_ai_laptop_native_e2e.py \
  --model-root /absolute/private/installed-model \
  --state-dir /absolute/private/sqlite-state \
  --capacity-root /absolute/private/capacity \
  --tenant local --subject owner \
  --context 2048 --max-new-tokens 256 \
  --threads 4 --gpu-layers 0 --inference-ms 90000 \
  --prompt-stdin --approve-real-model-test
```

Send a private UTF-8 prompt into stdin through a trusted local channel; do not
place it in a process argument or job log. The script itself does not
download models, fabricate rights, read stdin, trim its bytes, open another
store, retry a failed native turn or print the private prompt. It forwards
all processing to the canonical CLI.

**Expected only when the real native checks succeed:** a single bounded JSONL
record with `status: native-cold-reopen-sqlite-verified`,
`second_generation_attempted: false` in the evidence and
`release_certified: false`. A synthetic CI test must never count as the
device result. Any error, source drift, uncertain generation, missing SQLite
commit, capacity denial, partial stdout or revoked lease is a hold.

Before consumer release, additionally collect device-specific Windows 11/WSL2
startup, native cancellation, sustained memory/disk-pressure and cold-process
recovery evidence plus final-head security/quality gates and independent
approval. Do not infer device certification from these steps.
