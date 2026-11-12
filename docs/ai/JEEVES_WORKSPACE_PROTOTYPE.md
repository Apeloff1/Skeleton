# Jeeves local workspace prototype

The standalone workspace runs the existing Jeeves local model adapter and
private SQLite conversation store. It provides chat, local reference selection,
context preview, recovery, and conversation organization without a hosted model.
The integrated mobile/backend deployment has its own setup and qualification;
see [the installed-model guide](INSTALLED_AI_CHAT_PROTOTYPE.md).

## Start with an approved local model

Use an installed, licensed GGUF and compatible llama.cpp executable. Prepare the
digest-pinned deployment using the existing guide; model files are not bundled
with the prototype. Then start the authenticated numeric-loopback service:

```sh
python -m skeleton.app.offline_http \
  --gguf-deployment /absolute/private/jeeves.json \
  --database /absolute/private/jeeves.sqlite3 \
  --token-file /absolute/private/new-workspace-token.txt \
  --open-browser
```

Use a private directory. The token file must be a new path: the service creates
it privately and never overwrites an existing file. The terminal reports the
local URL and token-file path. Paste the token into **Local access token** and
choose **Connect locally**. The token input clears after connection; credentials
and drafts stay in tab memory rather than browser storage. **Lock** clears the
visible workspace and requires explicit reconnection.

The interface displays model readiness. A trained model and actual compatible
runtime are required for useful answers. The source acceptance harness uses an
untrained miniature native model solely to verify execution and persistence.

## Complete daily-use journey

1. Choose **+ New**, enter a message, and generate locally. Response settings
   expose the output budget and full-history requirement; Ctrl/Cmd+Enter sends.
2. Use **Rename** for a persistent title, or save an empty title to restore the
   automatic first-message title. **Pin** puts a conversation first in its
   collection. Search matches titles and saved transcript text, with Unicode
   case folding and literal substring handling.
3. **Archive** moves the conversation to the archived collection. It preserves
   history, source receipts, and the current tab's draft. Open **Archived** to
   reopen or restore it. Archiving is organization, not deletion or access
   revocation.
4. Expand **Reference library** to import local text, select sources, and inspect
   exact retrieved passages. Enable local evidence and choose **Preview context**
   before generation. Preview is read-only; it does not execute the model or
   certify factual support. A removed selected source blocks generation until
   the user changes the selection or explicitly resets to all references.
5. Expand **Conversation tools** to branch, export a portable backup, export
   Markdown, or import a backup into a separate conversation. A branch preserves
   the human title and starts active and unpinned.
6. After reload, reconnect and choose the saved conversation. After a server
   restart, use the same database with a new token-file path. Committed history
   and organization survive; unsaved tab drafts do not survive tab destruction.

Local image/audio/video observations and Dragon excerpts remain explicit,
human-reviewed advisory text. Their imports do not perform OCR, transcription,
video inference, hosted generation, or publication.

## Failure and recovery behavior

| Situation | Expected behavior | Recovery |
|---|---|---|
| HTTP delivery is lost after a turn was admitted | The original request ID is polled; a verified committed receipt wins. | Check the original status; replay the original request rather than inventing a replacement. |
| Context does not fit | Full-history mode refuses silent trimming. | Reduce the requested output, explicitly change the context policy, or branch/start another conversation. |
| Another process holds local inference custody | New execution is denied while saved history remains readable. | Wait for the owner to settle, refresh model status, and retry deliberately. |
| A title/pin/archive was changed in another tab | Metadata compare-and-set returns conflict. | Refresh saved history and review the latest state before editing. |
| Metadata save succeeds but collection refresh fails | The confirmed save remains successful; a separate list warning is shown. | Refresh the collection; do not repeat the already committed mutation with a stale revision. |
| A selected source was removed | Source-restricted generation stays blocked. | Change the selection or explicitly choose all references. |
| A backup is malformed, incompatible, or has altered evidence | Import fails before creating the destination. | Preserve the original file and recover a valid model-compatible backup. |
| The workspace is locked during a request | Aborted/late responses cannot repopulate the locked tab. | Reconnect and recover committed state from the server. |

Explicit long-form approval denials retain HTTP 403; malformed knowledge queries
retain HTTP 400. Corrupt or unavailable selected source content remains a
separate rejection. Private storage/model exceptions are not returned verbatim.

## Persistence, migration, and rollback

Organization uses the existing `OfflineChatStore` and an additive
`offline_session_metadata` table. The store creates the table on open. Old
conversations default to their automatic title, active, unpinned, and metadata
revision zero. No transcript rewrite or destructive migration occurs.

`POST /v1/sessions/{session_id}/metadata` accepts `title`, `pinned`, `archived`,
and optional `expected_metadata_revision`. The UI always sends its observed
metadata revision. Metadata mutations have a separate clock; they never advance
the model-turn revision, regenerate responses, or change inference receipt
identity. Reads and writes require the existing model/tokenizer scope.

Portable bundles retain v1/v2 schemas when organization is default. Nondefault
organization uses explicit v3 with a checksum-bound `metadata` field and the
existing immutable evidence list. New code imports all three versions. A v3
import receives a new conversation ID and fresh metadata clock. An older client
may reject v3; preserve the original backup and reopen it with the newer client.

Rollback can restore the prior application code while retaining the SQLite
database and additive table. Older code ignores the metadata table. Never drop
the table, reinitialize the database, remove source evidence, or edit receipts
as a rollback shortcut. Back up the database using SQLite-aware backup or export
after execution has settled; copying a live WAL database incompletely is unsafe.

## Reproduce the focused acceptance

From a development environment with the project and its local-inference test
dependencies installed:

```sh
python -m pytest -q --noconftest \
  tests/test_jeeves_conversation_organization.py \
  tests/test_app_offline_http.py \
  tests/test_app_offline_chat_persistence.py \
  tests/test_app_offline_chat_cli.py \
  tests/test_ai_offline_native_chat.py
python -m pip install 'playwright==1.62.0'
python -m playwright install chromium
python scripts/qualify_jeeves_workspace_browser.py --output /tmp/jeeves-browser
```

The browser harness starts the production HTTP handler, real native adapter,
and private temporary SQLite store. It exercises desktop/mobile interaction,
three model turns, lost-response recovery, source restrictions, v3 backup
round-trip, organization, restart, and locking. Reports bind source hashes,
commit/dirty state, fixture model, browser, Python, platform, and viewports.
Screenshots mask the token field. Outbound-request checks cover the browser
context only; they do not establish an operating-system-wide network audit.

The draft workflow runs these checks on the PR commit and retains nonsecret
browser artifacts. Source/native fixture success does not qualify production
GGUF quality, physical devices, protected deployment bootstrap, or competitors.

## Construction coverage for this increment

| Level | Implementation or acceptance responsibility |
|---|---|
| L00 ownership | Existing `skeleton/app` adapter and `OfflineChatStore`; no additional runtime service. |
| L01 dependencies | Existing loopback HTTP, native model adapter, SQLite, static same-origin UI. |
| L02 contracts | Separate metadata revision; explicit v3 backup; legacy import compatibility. |
| L03 admission | Existing bearer/origin checks, model/tokenizer identity, bounded metadata fields. |
| L04 control flow | Validated mutation → transaction/CAS → confirmed UI update → collection refresh. |
| L05 state | Additive table, transactional snapshots, new-ID imports, immutable turn history. |
| L06 privacy | Safe text rendering, no browser persistence of credentials/text, stable public errors. |
| L07 recovery | Stale edits, interrupted delivery, restart, import rejection, and lock fencing. |
| L08 observability | Safe UI status plus source/environment-bound acceptance report. |
| L09 capacity | Bounded title/query/page fields; existing execution/context/resource admission. |
| L10 verification | Real HTTP/SQLite tests, hostile inputs, Unicode search, browser fault injection. |
| L11 deployment | Existing service entrypoint; additive migration; preserved database on rollback. |
| L12 operations | Setup, backup, restore, conflict recovery, and source withdrawal instructions above. |
| L13 exit | Prototype evidence only; [competitive acceptance](../plan/JEEVES_DRAGON_COMPETITIVE_ACCEPTANCE_2026_11_12.md) remains independent. |

This table documents the scoped increment. It does not sign off or close an
entire masterplan volume, enterprise grade, device qualification, or release.
