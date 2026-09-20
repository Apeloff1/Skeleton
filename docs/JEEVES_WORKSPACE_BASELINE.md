# Jeeves conversation workspace baseline

The existing `/jeeves-chat` route now opens a device-local workspace built around
the existing `/api/jeeves/chat` service. The route and provider configuration stay
compatible with existing deployments.

## User capabilities

- Create up to 30 independent conversations, with up to 100 messages each.
- Keep a separate draft, project context and output-format preference per chat.
- Search conversation titles, context and messages; pin, archive, restore or delete chats.
- Rename conversations and export a Markdown transcript through browser download
  or native sharing.
- Start from game-planning, debugging, learning and design-review prompts.
- Copy messages or fenced code blocks without executing returned HTML or code.
- Attach one image or PDF up to 5 MB, and save supported generated artifacts.
- Stop a reply or retry a failed turn without duplicating the user message.
- See storage failures, interrupted requests and unavailable server history explicitly.

## Architecture

`frontend/features/Jeeves/workspace.ts` owns the typed data model, bounded history,
search, transcript export and explicit persistence allow-list.

`WorkspaceController.ts` owns the lifecycle. Its injected storage and transport
interfaces allow deterministic tests of slow writes and late responses without
mounting React Native. A single write loop coalesces pending snapshots. A request
can update state only while it owns the current request token. Switching chats,
deleting the active chat, leaving the screen or pressing Stop aborts that request.

`ChatWorkspace.tsx`, `MessageContent.tsx` and `chatFiles.ts` provide the screen,
inert code-block display, pickers, downloads and native sharing. The route file
re-exports the screen so existing links remain valid.

`backend/gameforge/jeeves/chat_contract.py` validates input before retrieval or
generation. The existing composer accepts optional `context` and `history`, uses
recent user questions in retrieval, and sends quoted conversation data to the
configured generative provider. Context is never promoted to a system message.

## API additions

Existing requests containing only `message` remain supported.

```json
{
  "message": "How should I handle collisions?",
  "context": "Godot 4, beginner, a small 2D platformer",
  "history": [
    {"role": "user", "content": "How do I move the player?"},
    {"role": "assistant", "content": "Start with a character body."}
  ],
  "force_all_forms": false
}
```

Bounds: 16,000 characters per message, 4,000 characters of project context,
20 history messages with 4,000 characters each and a 24,000-character aggregate
history budget. History roles are limited to `user` and `assistant`; blank text,
invalid base64, oversized attachments and simultaneous image/PDF attachments
are rejected with HTTP 422.

The response adds `persisted` and `history_messages_used`. A failed MongoDB write
does not discard a generated response, but `persisted` is false. History reads
return the newest requested window in chronological order, accept limits from
1 through 100, and expose `available: false` on storage failure.

## Persistence and recovery

The new AsyncStorage key is `@tutolage/jeeves-workspace:v1`. On the first visit,
the old `@tutolage/jeeves-chat:v2` transcript migrates if no new workspace exists.
The old key remains as a recovery copy. Invalid or unknown workspace schemas
block loading and editing, preserving the original stored value.

Only text and metadata are persisted. Attachment bytes and generated file bytes
never enter storage or transcript exports. Interrupted pending messages become
retryable failed turns after reload. A retry requiring an attachment after reload
restores the draft and requests reattachment. Backend session IDs expire locally
after six hours; transcripts remain available. Reaching a conversation/message
limit does not silently evict another conversation or its transcript.

The client disables automatic POST retries because the existing backend does not
provide durable idempotency. Explicit retry after a lost response may still cause
duplicate server history or repeated provider work; local duplicate user turns
are prevented. Cancelling a request prevents late UI updates but cannot guarantee
that an already-started server/provider task stops.

## Verification

From `frontend`:

```sh
npm run test:jeeves
npm run typecheck:jeeves
npx eslint features/Jeeves/ChatWorkspace.tsx features/Jeeves/MessageContent.tsx features/Jeeves/WorkspaceController.ts features/Jeeves/workspace.ts features/Jeeves/chatFiles.ts app/jeeves-chat.tsx --max-warnings=0
```

From the repository root, in an environment with pytest, FastAPI, httpx,
matplotlib and networkx:

```sh
python -m pytest tests/test_jeeves_chat_workspace.py -q
```

The 23 controller tests cover migration, corrupt storage, request cancellation,
late completion, duplicate sends, retry, interrupted attachments, write ordering,
storage quota failure, session expiry, search and retention limits. The 29 HTTP
tests exercise validation, contextual retrieval/generation, backward-compatible
requests, provider fallback reporting and history availability/order.

Browser checks used an isolated Expo preview of the actual screen: desktop and
phone layout, details editing, starter prompts, new conversations, search, draft
restoration after reload and failed-response handling. Live provider generation,
MongoDB integration and native-device attachment/share flows were not exercised.

## Existing integration constraints

The full frontend typecheck and full-app Metro preview on Windows are blocked by
the repository's pre-existing case-colliding `frontend/components/UI` and
`frontend/components/ui` trees. The focused Jeeves typecheck passes. The isolated
preview does not substitute for a complete app build on a case-sensitive host.

This is a local workspace, not account-synchronized chat storage. Provider behavior
still follows the existing free-tier cascade: local/free extraction uses available
knowledge; configured paid escalation is the generative path. The screen does not
claim that an unavailable provider answered a question. Multimodal understanding
continues to depend on the existing backend attachment pipeline.
