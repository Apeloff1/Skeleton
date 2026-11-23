# Jeeves standalone Docker — real local chat and canonical replay admission

**Scope:** new opt-in physical chat-route acceptance phase stacked after the
full offline image, Compose, Docker, GGUF, recovery and provenance source
work. This is not an independent review release or migration.

## Why container readiness was insufficient

A healthy Docker container or a successful one-shot llama.cpp execution
does not prove that the real user-facing backend can authenticate an owner,
load durable conversation state, admit a model under policy, execute
engine-owned Jeeves, persist a verified assistant message and recover the
same result without generating again.

This phase exercises that real path through the existing application API.
It never uses a second AI provider or a hosted model client.

### Read-only backend observation

Provision a supported, authenticated existing user via the normal backend
login UI. Write its current bearer token into an **absolute, owner-owned
private 0600 file**; avoid command-line and environment token arguments.
Do not store the token in the repository, CI logs or archive.

    python scripts/local_ai_docker.py --mode cpu observe-local-chat \
      --directory /home/operator/private/transfer-001 \
      --overlay-directory /home/operator/private/bind-001 \
      --expected-receipt-sha256 INDEPENDENT_OFFLINE_IMAGE_RECEIPT_SHA256 \
      --token-file /home/operator/private/auth/session.token

The script:
1. Independently validates the sealed four-image archive/overlay, live
   container immutable IDs, private internal-only network, mounts,
   privileges and resource fences.
2. Obtains the actual published backend TCP port from the independently
   admitted canonical effective Compose JSON. Only IPv4 127.0.0.1 is
   allowed. No arbitrary user URL, proxy, redirect or hosted destination.
3. Calls the authenticated backend readiness endpoint and provider
   inventory. It requires usable conversation storage, engine and models,
   one local engine-owned Jeeves provider and no hosted alternatives.
4. Re-attests all Docker container identities before returning a redacted
   non-authoritative observation receipt.

No conversation turn is submitted, no model is invoked and no database is
modified by the observer.

### Explicit one-turn, durable local-only Jeeves qualification

A real turn changes durable user conversation state. Prepare a dedicated
preexisting private test thread through the normal supported application
workflow. Record the current canonical thread version in advance.
Do not target an important existing conversation.

    python scripts/local_ai_docker.py --mode cpu qualify-local-chat \
      --directory /home/operator/private/transfer-001 \
      --overlay-directory /home/operator/private/bind-001 \
      --expected-receipt-sha256 INDEPENDENT_OFFLINE_IMAGE_RECEIPT_SHA256 \
      --token-file /home/operator/private/auth/session.token \
      --thread-id EXISTING_TEST_THREAD_ID \
      --expected-thread-version EXISTING_THREAD_VERSION \
      --allow-durable-chat-turn

This is an **opt-in write**. The command performs the read-only observation,
then runs the existing exact-ID isolated native Jeeves GGUF preflight/turn
using the same model/executable/manifest. It observes readiness again and
rechecks authenticated principal identity before submitting one canonical
backend POST.

The POST names exactly provider=local and model=jeeves with a unique
idempotency key, the supplied expected thread version, a finite output
budget, and a challenge marker generated locally. No crawler,
external attachment, tool authorization or background workflow is
requested. The backend must produce exactly the challenge marker and a
completed real engine-owned turn with one or more local-only provider
receipts and durable user/assistant transcript identities.

The verifier then makes ONE read-only GET against the canonical chat turn
endpoint. It requires the committed assistant content, engine execution
identity and provider receipt set to match exactly, with provider=replayed
and state=completed. It rechecks running container identities after the
turn. A missing result, hosted provider, changed engine, alternate
response, missing provider receipts, incomplete commit or mismatched
replay is rejected.

The result receipt contains only image and model hashes, the hash of the
actual response text and engine-execution ID, and redacted booleans.
Neither the token, test prompt, model output, user/assistant message
identities, thread identifier, nor raw API responses are printed.

**No retries:** if the POST times out, the durable user turn may already
have committed. The script must NOT resend the same or a new POST.
Inspect the existing test thread manually via the supported application
UI before attempting any further action.

### Authority limitations

A successful protected-route chat plus canonical durable replay
**does not independently attest** an active GGUF tokenizer, bounded
reviewer, majority-durable Mongo writer epoch, schema migrations,
cross-store coherent backup, physical GPU offload, Windows/WSL2
network/device compatibility or signed release provenance.

The receipt deliberately leaves protected_chat_qualified=false, along
with those independent authority fields. Those require separate
authoritative proofs. A read-only backend readiness result is not a
test substitute.

### CI acceptance

Unit tests replace the Docker and HTTP transports with deterministic
fixtures and inject hostile providers, false readiness, missing local
receipts, modified model output, wrong durable identities, tampered
replay, changed container IDs and HTTP redirect destinations. CI never
sends a real authenticated user token or mutates production conversations.

Actual real-API qualification requires the user-provisioned, licensed
model, authenticated test thread and isolated production-equivalent
local hardware. Without these inputs the gate remains explicitly
unqualified, even when the code and synthetic Docker tests pass.

Keep every stacked GitHub PR draft and review-only; no auto merge or release.

## Real loopback HTTP transport acceptance — isolated synthetic test

Before a hardware-authenticated backend can be promoted, CI now exercises the
operator's **actual** Python HTTP transport with a disposable server bound
exclusively to IPv4 127.0.0.1 on an ephemeral port. This probe is independent
from any production Mongo volume, hosted provider, user bearer token, Docker
image or licensed GGUF.

    python scripts/qualify_local_ai_http_loopback.py

The test performs an actual authenticated GET for readiness and provider
status, exactly one challenge POST, and a second GET that must replay the
same synthetic engine execution identity, answer and local receipt set.
It checks HTTP redirect refusal, duplicate JSON key denial, bounded response
bytes, unauthorized token rejection and sanitized 403 handling without
following any remote Location header or proxy environment setting.

The synthetic server is completely shut down after verification. CI prints
only boolean qualification receipts, never the challenge marker or bearer
token.

**Scope:** This proves localhost HTTP transport mechanics against a synthetic
server. It does NOT prove the real application generated a token, authentic
Mongo writes occurred, a real GGUF tokenizer/reviewer was independently
attested, or physical user hardware was qualified. The explicit real-backend
qualify-local-chat command remains the separate required acceptance gate.

## Authentication enforcement and canonical causal replay

Before interpreting provider or conversation-storage readiness, the real
backend must answer GET /api/auth/me for the existing owner-private bearer.
The response MUST report ok=true, enforced=true, authenticated=true,
a non-development viewer/editor/admin identity with an owner field, and
no disabled user. An anonymous development-mode admin is never accepted
as proof of authenticated chat. No accounts or sessions are created.

The owner ID, email, role, bearer and session details are never written to
the machine-readable report. Only an authenticated-owner boolean is shown.

The original durable assistant must also bind causal_user_message_id
to the committed user_message.message_id. Replay must preserve both
operation_id and engine_execution_id, the exact challenge and the full
local provider receipt set. A model response that lacks this causal
thread binding does not pass protected transport qualification.

The disposable CI HTTP server exercises this enforced-auth endpoint before
the redirect, duplicate JSON, oversized body, secret-leak and one-POST replay
tests. It does not prove the real target-device backend is configured for
enforced authentication; that still requires real operator-owned credentials.
