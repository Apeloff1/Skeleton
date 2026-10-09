# Native offline chat: direct standalone runtime

This is an operator-facing, **network-free text chat** entry point for the existing
`skeleton.ai.model_runtime` implementation. It runs the in-repository
`TinyTransformer` runtime on locally supplied model weights; it does **not**
route requests to OpenAI, Anthropic, or any other remote model provider. It
does not start Docker, MongoDB, a web server, or an agent automation plane.

## Required model artifact

Supply a Skeleton native runtime checkpoint, generated after model construction
or training using the existing `NativeLLMRuntime.checkpoint_json()` API.
The loader validates the checkpoint schema, model bytes, architecture, tokenizer,
and checkpoint digest before inference. This is **not** a GGUF reader;
GGUF/llama.cpp models follow the separate admitted local-inference path.

A portable example (only a *random, untrained demonstration model*):

```python
from pathlib import Path
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime

model = TinyTransformer(vocab=("hello", "world", "you", "are", "an",
                               "assistant", "answer", "the", "question"),
                        dim=8, ctx=256, seed=7)
runtime = NativeLLMRuntime(model)
Path("demo-native-model.json").write_text(runtime.checkpoint_json(),
                                          encoding="utf-8")
```

This model proves the **execution route only**: it has not learned a useful
conversation skill. A useful offline assistant needs qualified trained weights,
appropriate tokenizer, independent model evaluations, and release acceptance.

## CLI usage

```bash
# Interactive multi-turn chat. Print and preserve the session ID.
python -m skeleton.ai.model_runtime.offline_chat \
  --checkpoint demo-native-model.json \
  --database ./my-private-chat.sqlite3 \
  --interactive --max-new-tokens 4

# One durable turn, with a retry id and machine-readable receipt:
python -m skeleton.ai.model_runtime.offline_chat \
  --checkpoint demo-native-model.json \
  --database ./my-private-chat.sqlite3 \
  --message "hello" --request-id request-001 --json

# Resume after restart using the printed session ID:
python -m skeleton.ai.model_runtime.offline_chat \
  --checkpoint demo-native-model.json \
  --database ./my-private-chat.sqlite3 \
  --session YOUR_SESSION_ID --interactive

# Find resumable sessions for the same checkpoint:
python -m skeleton.ai.model_runtime.offline_chat \
  --checkpoint demo-native-model.json \
  --database ./my-private-chat.sqlite3 --list --json

# Delete a session and all its saved retry receipts:
python -m skeleton.ai.model_runtime.offline_chat \
  --checkpoint demo-native-model.json \
  --database ./my-private-chat.sqlite3 --delete-session YOUR_SESSION_ID
```

Interactive mode recognizes `/id` (print session ID) and `/exit`; EOF
also terminates. The checkpoint remains local. No implicit model downloader,
provider fallback, tool access, file editing, external networking, or privilege
elevation is enabled.

## Safety and consistency properties

- SQLite is authoritative for the local conversation and saved turn receipts.
  Each persistent conversation is pinned to **exact model and tokenizer digests**.
- Full generated turns are stored in one transaction using optimistic revision
  compare-and-swap. Failed inference, stale revisions and oversized transcripts
  do not commit partial assistant output.
- A request ID is reusable **only** for the same prompt and generation settings.
  A completed retry replays the committed receipt without running the model.
- The SQL schema avoids dynamic statements and enables foreign-key cascades;
  deleting a session removes its retry receipts. A new SQLite file is created
  with owner-only permissions on POSIX.
- Local interaction is single-user and assumes a trusted device and checkpoint
  distribution process. It is **not** a tenant-isolated, authenticated HTTP API.
- A power loss during generation leaves the previous conversation revision
  intact; interruption after SQLite commit can be retried with the same
  request ID. A model or tokenization change is rejected for existing sessions.

## Verification

```bash
python -m pytest -q tests/test_ai_offline_native_chat.py
python -m skeleton.ai.model_runtime.offline_chat --help
```

This milestone contributes a real, usable local serving surface; it **does not**
change `machine/ai_capabilities.json` states or assert that the whole AI app is
complete. Product completion still requires tested conversation ingress,
quality qualification, attached-product UI/API, release/installer acceptance,
and exact-head CI.
