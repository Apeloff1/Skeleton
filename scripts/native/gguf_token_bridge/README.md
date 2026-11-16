# Exact GGUF token transport (source candidate)

Build against a separately obtained, reviewed clean llama.cpp b11429 checkout:
```sh
cmake -S scripts/native/gguf_token_bridge -B /private/build/gguf-bridge -DLLAMA_CPP_SOURCE=/private/llama.cpp
cmake --build /private/build/gguf-bridge --config Release
```

The helper is a CPU-only, greedy, text-generation protocol, not a full llama-cli
replacement. The operator must independently verify the source commit, build
provenance, executable and model hashes, runtime closure, and actual device runs.
It never inserts BOS/EOS, interprets text as a control token, applies chat
templates, downloads a model or executes tools. Models that cannot losslessly
round-trip the exact admitted rendered prompt are denied. Other models may need
an independently reviewed template and special-token contract; do not claim
quality parity with their original chat template. The worker retokenizes and
compares the exact admitted IDs before invoking llama_decode on those IDs.
Binary frames use SKG1 magic and little-endian uint32 lengths/IDs. No raw prompt
or token list is emitted in public status or logs. This build source is not a
prebuilt or qualified executable.

The existing first-install reusable CI workflow includes a separate compile-only
job pinned to the same upstream source SHA. It checks malformed invocations
without downloading model weights. This receipt must not be represented as
local inference or hardware qualification.

The roundtrip operation returns both the exact token vector and detokenized text
from one vocabulary load. Native output file size and core dumps are bounded
with POSIX resource limits. The host still validates all frame lengths and echo
bytes. No throughput improvement is claimed until a physical benchmark runs.

Linux transport now pins executable and model descriptors, hashes the actual
opened bytes before and after execution, seals input memfd against writes and
seals response after the worker exits. Linux refuses to fall back to named
prompt files if memfd/procfs/sealing is unavailable. Other POSIX hosts retain
the private named-file path, not descriptor custody. This does not attest
system loader closure, immutable storage, swap exclusion or physical device
behavior; these remain independent qualification requirements.

The guarded native verification worker now signals cooperative cancellation
when its owning async task times out or is cancelled. The bridge observes
that signal during descriptor hashing, admission and physical subprocess
polling. The native slot remains occupied until the thread exits; arbitrary
noncooperative callbacks are not forcibly terminated. Generation and output
verification share one wall-clock budget, not two independent timeouts.

The bridge profile now rejects adjacent shared-runtime inventories (the CMake
build links llama/ggml statically; system loader closure is still unqualified).
Linux launch verifies descriptor ctime as well as the pre/post digest, freezes
resource settings before admission, and rechecks immediately before spawn.
The guarded native callback budget is at most 30 seconds for this backend,
subject to the caller's shorter existing wall-clock deadline.
