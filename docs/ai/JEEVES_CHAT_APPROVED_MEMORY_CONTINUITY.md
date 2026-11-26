# Jeeves Chat: approved memory and conversation continuity

This source wave extends the cognition and conversational-quality candidate from #5469, pinned at 3c453bdd165322c1d86dba7543230064d9c52e71.

## Implemented user paths

**Approved memory:** local-only model/tokenizer-scoped records in the existing private SQLite chat store. Store only an explicitly approved note or exact source excerpt. Categories: preference, fact, goal, constraint, rejection, correction, style and project. Records carry revisions and SHA-256 identity, optional UTC expiry and tags. Update and deletion require the exact record pin. Source-linked entries require a verified user-message excerpt and cascade on source conversation deletion. Metadata-only updates may retain an unchanged historical source after append-only growth.

**Indexed recall:** deterministic Unicode-normalized words and bounded character subwords, including CJK bigrams. Indexed first-pass selection, kind scoping, distinct exact pins, expiry filtering, cursor pagination and integrity checks of materialized records/postings. This is not learned semantic retrieval; truncated candidate scans are disclosed. There is no global index completeness assurance, physical capacity qualification or independent tamper-proof signature.

**Review to actual model conversation:** select one to four saved records, preview the full augmented draft, and explicitly apply only after a second matching server composition. The preview never calls inference. The user can inspect, edit and send the new visible user message through the original token admission and durable chat path. No hidden injection, system privilege, automatic memory update, implicit source selection, tool authorization or training. Notes already copied into a chat are independent of memory deletion; deleting a note does not scrub old messages, exports, clipboard or backups. Expiry does not erase records. Existing SQLite plaintext-at-rest custody and secure_delete configuration are inherited; physical erasure from WAL, backups and storage media is not asserted. A source note can be deliberately detached before manual edits.

**Conversation continuity:** edit an earlier user message, or retry an earlier answer's question, in a new conversation fork. Read the exact parent snapshot and verify the resulting child prefix before applying the draft. Preserve the parent, use the existing fork API, never auto-submit. Forked historical turns do not constitute fresh model execution evidence; original grounding settings are not automatically restored.

**Presentation:** local DOM-only limited rich-text renderer for assistant answers: headings, lists, blockquotes, simple tables, inline code/bold, fenced code with copy, raw text fallback and toggle. No HTML parsing, active links, images, remote rendering, scripts, artifact execution or third-party dependency. Unsupported Markdown remains literal. Copy the original visible response; a grounded publication is not replaced by an unverified raw model draft.

## Qualification

Run on the exact candidate after source assembly:

```sh
python -m unittest skeleton.testing.test_jeeves_chat_cognition_quality skeleton.testing.test_jeeves_approved_memory skeleton.testing.test_jeeves_chat_memory_workspace
python -m compileall -q skeleton/app/jeeves_approved_memory.py skeleton/app/offline_http.py skeleton/app/offline_web.py
```

Tests cover canonical SQLite lifecycle/restart, scope isolation, expiry, CAS, source validation and cascade, search features, exact composition, index corruption, route validation, inert renderer and complete JS parsing. Node-based checks skip when Node is absent. The small Node DOM fixture is not a real browser. Also require browser E2E (lock, reconnect, stale memory, deletion, cross-session recall, branch editing, actual inference), native/GGUF acceptance, full exact-head CI, canonical parity and security gates. No tests were executed in the authoring session; no SOTA score, physical storage performance or release readiness has been demonstrated.

## Remaining competitive work

Pretrained local embeddings and reranking, automatic context integration with distinct durable request/evidence receipts, long-window semantic compression, memory conflict resolution and consented adaptation, genuine native multimodal and voice, model reasoning refinement, tool execution, live streaming, expanded competitive evaluation and physical device qualification. This wave does not alter default model weights, trained intelligence, provisioning guard bootstrap or the existing application activation hold.
