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

## Windows desktop product integration

The installed Windows launcher already includes a **Local AI (offline)**
option. The desktop implementation in `skeleton/app/local_ai.py` now
connects the existing canonical `LocalInferenceEngine` execution adapter to
the same `OfflineChatStore` state authority used by the terminal product.

**This matters operationally:** closing the window or restarting the computer
no longer discards the latest successfully committed conversation.

- Select an actual local native checkpoint. Its SHA-256 model identity chooses
  an on-device SQLite database under `~/.skeleton/offline-ai/`.
- The most recently updated compatible conversation is restored on startup.
  Older conversations can be selected in the saved-conversation selector.
- **New conversation** creates a new persistent session rather than clearing
  previous user content.
- **Resume** reloads previous prompts and replies. **Delete** removes a
  selected conversation and its turn receipts; deletion asks for confirmation.
- **Export** writes a new portable JSON bundle with owner-only file permissions.
  **Import** checks record shape, checksum, model/tokenizer identity, turn
  continuity, and history before creating a *new* session ID. Existing sessions
  cannot be overwritten by an import.
- The existing cancel action remains bound to the canonical cancellable local
  inference engine. A cancelled or failed model operation leaves the durable
  state unchanged.
- Imports preserve one initial system instruction and carry it into subsequent
  native local turns as an explicit `LocalInferenceRequest.instructions`
  field. No imported data receives tool permissions or network execution.

The SQLite authority is intentionally local and single-user. Backups contain
**plaintext conversation content** and must be protected by the operator.
The bundle SHA-256 digest detects accidental changes, but does not establish
cryptographic authenticity against a malicious editor. A trained and independently
qualified native checkpoint is still required for useful responses.

## Portable CLI backups

```bash
# Export a specific conversation, including saved idempotency receipts.
python -m skeleton.ai.model_runtime.offline_chat \
  --checkpoint model.json --database chat.sqlite3 \
  --export-session YOUR_SESSION_ID --output private-chat-backup.json

# Restore to a fresh session ID for the exact same native model/tokenizer.
python -m skeleton.ai.model_runtime.offline_chat \
  --checkpoint model.json --database chat.sqlite3 \
  --import-bundle private-chat-backup.json
```

Exports are **create-only**: existing files are never silently overwritten.
Import validates the entire bounded payload before any persistent transaction.
The backup format is not an authentication or encryption format and should not
be used as an untrusted instruction feed.

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
python -m pytest -q tests/test_ai_offline_native_chat.py tests/test_app_offline_chat_persistence.py
python -m skeleton.ai.model_runtime.offline_chat --help
```

This milestone contributes a real, usable local serving surface; it **does not**
change `machine/ai_capabilities.json` states or assert that the whole AI app is
complete. Product completion still requires tested conversation ingress,
quality qualification, attached-product UI/API, release/installer acceptance,
and exact-head CI.
