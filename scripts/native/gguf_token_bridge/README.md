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
