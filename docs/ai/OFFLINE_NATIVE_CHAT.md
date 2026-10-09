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

## Real GGUF/open-weight deployment in the standalone desktop

The existing Windows **Local AI (offline)** window supports two explicit
loaders. **Load native checkpoint** restores Skeleton's internal transformer
checkpoint format. **Load local GGUF** loads an operator-owned deployment
manifest through the canonical `LocalModelDeployment` authority.

The GGUF manifest pins both the llama.cpp executable and the GGUF model by
SHA-256, rejects unexpected remote artifact acquisition, and validates the
GGUF header. The subprocess receives prompts in a private temporary file;
model and executable identities are checked again on every invocation.
There is no implicit download, hosted API fallback or provider token.

A GGUF file **alone** is not an executable model deployment: the operator
must also install an appropriate compatible `llama.cpp` CLI, define a
manifest using `skeleton.local_model.deployment.v1`, and set the exact
digest-pinned local paths. See the existing deployment module
`skeleton/ai/runtime/inference/deployment.py` for the validated schema.

The same model-identified SQLite conversations are available in both GUI
and headless operation. The GGUF tokenizer binding derives from the exact
verified model artifact bytes; native checkpoint/tokenizer binding keeps
its existing explicit tokenizer hash.

### Headless native or GGUF chat on Windows, Linux or macOS

```bash
# Start a real locally installed GGUF/llama.cpp deployment, no Tk required:
python -m skeleton.app.offline_chat_cli \
  --gguf-deployment ./local-gguf-deployment.json \
  --interactive

# Use the same per-model saved state with a native checkpoint:
python -m skeleton.app.offline_chat_cli \
  --native-checkpoint ./model.json \
  --message "hello" --json

# Read saved sessions without creating an empty conversation:
python -m skeleton.app.offline_chat_cli \
  --gguf-deployment ./local-gguf-deployment.json \
  --list --json

# Export a selected conversation including all durable turn receipts:
python -m skeleton.app.offline_chat_cli \
  --gguf-deployment ./local-gguf-deployment.json \
  --export-session YOUR_SESSION_ID --output ./private-backup.json

# Restore into a new ID without overwriting another session:
python -m skeleton.app.offline_chat_cli \
  --gguf-deployment ./local-gguf-deployment.json \
  --import-bundle ./private-backup.json
```

### Branch a previous conversation without losing its original

The desktop's **Fork** action creates an independent conversation. You can
also branch from an earlier committed turn by using the command line:

```bash
python -m skeleton.app.offline_chat_cli \
  --gguf-deployment ./local-gguf-deployment.json \
  --fork-session SOURCE_SESSION_ID --fork-after-turn 3
```

A fork copies exactly the chosen prefix of user/assistant turns, including
the applicable original system instruction and idempotency receipts. The
parent and its later dialogue remain unchanged. Revisions and future
inference on each branch are independent; invalid or uncommitted fork
boundaries fail closed. No local-model call occurs during the copy.


The GUI and headless entry points default to the same local model-specific
database under `~/.skeleton/offline-ai/`. Override with `--database` if a
separate store is preferred. Terminal commands `/id`, `/new`, `/list`,
`/resume SESSION_ID` and `/exit` are supported.

For an **actual model acceptance smoke** rather than the bundled untrained
native demonstration, on Windows run:

```powershell
Skeleton.exe --local-gguf-smoke .\local-gguf-deployment.json
```

A zero exit code requires successful real GGUF inference and persisted session
restoration. This is an execution check, **not** a model-quality or security
certification. Checkpoint quality and legal model-use rights remain external
operator responsibilities.


## Localhost browser workspace and authenticated offline API

A standalone browser service lets local clients use the same model-bound SQLite authority, including recovery, forks, backups and stable request receipts. Start an operator-owned model from this repository:

    # Native transformer checkpoint
    python -m skeleton.app.offline_http --native-checkpoint ./local-model.json --token-file ./new-private-token.secret --port 8137

    # Or a preinstalled, digest-pinned GGUF/llama.cpp deployment
    python -m skeleton.app.offline_http --gguf-deployment ./my-gguf.json --token-file ./new-private-token.secret --port 8137

Open http://127.0.0.1:8137/ on **the same computer**. Paste the bearer token from the new owner-readable secret file into **Local access token**. The browser uses only the same-origin local service; it includes no CDN, remote font, external script, account login, provider fallback, browser localStorage or cookies.

The installed Windows frozen launcher exposes the same feature:

    Skeleton.exe --local-http --local-gguf-deployment .\my-gguf.json --local-token-file .\new-private-token.secret --local-port 8137

Use `--local-native-checkpoint` instead of `--local-gguf-deployment` for the native format.

### API operations

| Method | Route | Action |
| --- | --- | --- |
| GET | /v1/status | Exact local model identity and token default |
| GET, POST | /v1/sessions | List / create persistent conversations |
| GET, DELETE | /v1/sessions/{id} | Retrieve full history / delete |
| POST | /v1/sessions/{id}/turn | Native or GGUF inference and durable commit |
| POST | /v1/sessions/{id}/fork | Fork at a committed revision |
| GET | /v1/sessions/{id}/export | Retrieve full integrity-checked backup |
| POST | /v1/sessions/import | Import into a new conversation ID |

Every API call requires the `Authorization: Bearer <private-token>` header. All POST routes use JSON. Example turn request:

    {"message":"hello","request_id":"my-stable-retry-001","max_output_tokens":32}

The server binds exclusively to numeric 127.0.0.1, checks the Host and Origin, denies cross-origin requests and encoded paths, uses no permissive CORS, restricts HTTP body and connection budgets, and never logs prompts or secrets. The token is held in browser tab memory only. Reusing a request ID with identical inputs replays the recorded answer; changing its inputs rejects the request without a new model execution.

The browser UI supports model status, multi-turn chat, full saved-history recall, new sessions, deletion, forking and portable backup. **Backups remain plaintext** and should be protected as private records. This local single-user surface is not yet an independently security-assessed, authenticated multi-user product.

Black-box acceptance:

    python -m pytest -q tests/test_app_offline_http.py

The integration test binds a real ephemeral localhost port, executes native inference, checks token/origin/host protections, concurrent exact-once retries, complete-history backups, forks and local token-file permissions.


## Local reference library: verified searchable source passages

The authenticated localhost app can ingest operator-supplied text/Markdown files
into the **same model-specific SQLite authority** as saved conversations.
The local browser sidebar has **Local reference library** controls for uploading,
listing, searching and removing references. No web crawler, HTTP fetch, remote
model, filesystem path execution, remote search or shell command is involved.

The REST workflow is:

- `POST /v1/knowledge/documents`: `{"title":"GPU notes.md","text":"..."}`
  with at most 65,536 UTF-8 bytes of source content.
- `GET /v1/knowledge/documents`: model-scoped document catalog with SHA-256.
- `POST /v1/knowledge/search`: `{"query":"rasterizer edge functions","limit":6}`.
- `DELETE /v1/knowledge/documents/{document_id}`: remove one local document
  and its dependent index chunks.

Documents are exact-byte deduplicated within the admitted model/tokenizer
identity and limited to 256 documents / 4,096 chunks per model. Searches apply
deterministic Unicode-normalized lexical scoring, not remote embeddings. Every
returned passage contains the source title, source SHA-256, indexed character
offsets, source chunk index and a local citation ID.

**Adversarial provenance control:** search and list read a consistent SQLite
snapshot, check the original full document bytes against the declared SHA-256,
and recompute every original chunk/offset. Missing chunks, corrupted source
bytes or falsified citations make the request fail rather than return bogus
source evidence. The text is treated as untrusted reference content and is not
given tools or elevated instruction authority.

**Scope:** this implements searchable reference evidence only. It does **not**
assert that a local language model used those passages in a generated answer.
Search results are displayed separately from generated chat responses. Full
retrieval-grounded answer generation will require explicit prompt/citation
binding, stored evidence manifests, drift-safe replay and answer-attribution
evaluations. Accordingly, the project's `assistant.retrieval_grounded`
capability remains partial rather than being promoted to complete.

Release test entry points:

    python -m pytest -q tests/test_app_offline_knowledge.py tests/test_app_offline_http.py
    Skeleton.exe --local-http-smoke

The frozen Windows HTTP smoke now includes actual localhost reference import,
search and **fresh SQLite reopen after service teardown**, as well as native
generation and replay. Real model quality and installer signing remain separate
release gates.


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
  **The full dialogue is retained** while only a smaller temporary copy is
  sent to the model after context-window eviction. Historical assistant
  responses are never truncated from the durable record to fit inference.
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
python -m pytest -q tests/test_ai_offline_native_chat.py tests/test_app_offline_chat_persistence.py tests/test_app_offline_chat_cli.py tests/test_app_offline_http.py
python -m skeleton.ai.model_runtime.offline_chat --help
```

This milestone contributes a real, usable local serving surface; it **does not**
change `machine/ai_capabilities.json` states or assert that the whole AI app is
complete. Product completion still requires tested conversation ingress,
quality qualification, attached-product UI/API, release/installer acceptance,
and exact-head CI.
