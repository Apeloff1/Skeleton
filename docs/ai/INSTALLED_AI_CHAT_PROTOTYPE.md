# Installed Jeeves AI chat — connected prototype and live acceptance

This is a real app integration, not a fake offline chatbot. The governed conversation UI is at /ai-chat; /jeeves-chat is the legacy compatibility route. Both rely on the canonical authenticated backend and engine. A green HTTP health response is not proof that a model can answer.

## 1. Make the installed app reach the backend

On Android/iOS, localhost points to the phone, NOT your laptop or container. Native APK production/preview builds require an explicit HTTPS origin for the real backend API, for example from the frontend/ directory:

    EXPO_PUBLIC_BACKEND_URL=https://api.your-domain.example npx eas build --profile apk --platform android

EXPO_PUBLIC_BACKEND_URL is a public network location, NEVER an AI provider secret. Set DNS/TLS and a reverse proxy to the existing backend /api routes. The default Docker Compose host backend listener is loopback-bound, so changing the URL to a private IP is not enough. Do not publicly expose MongoDB, engine privileged routes, or provider credentials.

Native release build preflight rejects missing, loopback, HTTP, credential-bearing, query/fragment-bearing and path-suffixed origins. Runtime endpoint validation also refuses unsafe native backend URLs; browser local development remains supported. The /setup screen shows the actual application API origin and a warning when the installed application was not connected.

## 2. Make real chat ready

All four capabilities must work: (1) signed-in account and correct tenant; (2) durable conversation store with engine admission; (3) authorized engine; (4) a selectable activated text model. The chat screen now reports distinct storage, engine, provider credentials, missing model and protected local guard failures.

For a hosted provider, after the canonical installer has created the private .env, the owner can opt in through the new secret-safe activation command:

    python scripts/configure_ai_chat_hosted.py --model gpt-4.1-mini --prompt-key --apply

This validates the chosen model, accepts the server-side key through a hidden prompt, holds the setup lock, updates only AI_PROVIDER, AI_MODEL and OPENAI_API_KEY atomically in owner-private .env, and does not overwrite an existing key or configured local deployment without explicit rotation/switch flags. The command reports real_inference_verified=false and requires engine recreation. The provider receives chat content, so use this only when approved for your data policy. Keep provider credentials out of Expo EXPO_PUBLIC variables. The model must genuinely exist under your provider account, and the installer, owner/bootstrap, storage and engine scope requirements still apply. Refer to FIRST_INSTALL_AI_AND_CRAWLER.md.

For local GGUF: the default Compose setup is documented as missing the trusted guard and source authorities. Downloading weights alone DOES NOT make the protected local path work. A compliant trusted app bootstrap requires native tokenizer/sampler attestations, reviewer, task-scoped canonical source authority, shared writer epoch and majority-durable Mongo. Never disable the guard, use an unsafe developer bypass, or substitute fake model output in a release.

From the Skeleton repository root:

    python scripts/install_app.py --production --start
    python -m skeleton app doctor --live --json
    python -m skeleton app status --live

## 3. One-command hosted chat deployment

Run the complete owner-controlled deployment on the server, not on the handset:

    python scripts/install_ai_chat.py --model gpt-5.5 --prompt-key --apply --start

The command sets up the real private environment, activates the approved hosted
provider (without overriding a configured required local guard), invokes the
canonical production installer, and waits for its normal service and route
checks. It fails closed if any required installer step fails. It reports
`inference_verified=false` until a real turn is executed. The model name is an
example: use a model actually authorized by your provider account.

To provision an owner at the same time, add:

    --admin-email owner@example.com --admin-password-file /absolute/private/owner-password.txt

To also make the run a real model-turn acceptance, add:

    --exercise --base-url https://api.your-domain.example --login-email owner@example.com

The private account password is prompted without echo. This explicitly opts
into sending one bounded confidential test message to the hosted model. The
installer will not claim `inference_verified=true` without a provider receipt
and saved, independently replayed answer. A release still additionally requires
actual installed-device testing and exact-head security gates.

## 4. Verify an actual model-generated chat answer

The new stdlib-only smoke command uses the same API that the installed app uses. It does not load a model or invent an answer. A private interactive password prompt avoids secrets in process arguments:

    python scripts/ai_chat_installed_smoke.py --base-url https://api.your-domain.example --login-email owner@example.com

This read-only mode authenticates the account and validates the versioned readiness contract and independent storage/engine/model checks. It does not create a conversation.

Submit exactly one test turn only when explicitly requested:

    python scripts/ai_chat_installed_smoke.py --base-url https://api.your-domain.example --login-email owner@example.com --exercise --timeout 180

The command creates a confidential canonical conversation, prints a nonsecret thread/request ID for recovery, admits one idempotency-keyed deferred message, polls the exact same turn, verifies terminal assistant output and real engine provider receipts, then reads the saved assistant from canonical history and checks the completed turn independently. It reports answer character count and receipt count, not message text or account tokens. If a transport times out after admission, do not resubmit: use the recorded IDs to recover the existing turn.

For a preexisting bearer token you may use --token-file /absolute/private/chat-token instead of --login-email. On POSIX it must be mode 0600 and never a symlink. Insecure HTTP is allowed only to actual loopback when you explicitly specify --allow-loopback-http; public hosts require HTTPS.

### Recover a saved turn after a network interruption

If a POST may have been accepted, do not send the test prompt again. Use the
nonsecret `thread_id` and `request_id` printed before admission:

    python scripts/ai_chat_installed_smoke.py --base-url https://api.your-domain.example --login-email owner@example.com --recover-thread THREAD_ID --recover-request REQUEST_ID

Recovery only performs authenticated GETs, including provider-receipt and
canonical transcript verification. It works even if the provider has gone
offline after the original answer was committed. It never sends another chat
turn or silently changes the selected model. After restarting the server,
repeat recovery to qualify persisted continuation.

## 5. Qualification and limitations

Focused tests:

    python -m pytest -q tests/test_ai_chat_installed_smoke.py tests/test_configure_ai_chat_hosted.py tests/test_install_ai_chat.py
    cd frontend && node --test scripts/test-installed-chat-endpoint.cjs
    cd frontend && npm run typecheck
    cd frontend && npm run test:app-foundation

Full consumer release still requires a fresh installed APK and device validation, HTTPS ingress, engine grants, a genuinely configured provider or protected local GGUF runtime, service-restart conversation recovery, cancellation/pressure/security tests and exact-head CI. None of those independent physical qualifications is established by code-only changes. This PR remains review-only until tested.

First-install failure lookup:

| Signal | Remedy |
| --- | --- |
| Native URL missing, localhost or HTTP | Rebuild with the real HTTPS backend origin |
| Network/TLS error | Repair ingress, DNS, certificate or host firewall |
| 401/403 | Authenticate and verify tenant and engine authorization |
| Conversation storage blocked | Repair Mongo, canonical writer epoch and storage admission |
| Engine unavailable | Repair internal service endpoint and grants |
| local_model_not_configured | Activate a real approved model, or hosted provider |
| local_guard_unavailable | Complete trusted protected-local bootstrap; weights do not fix it |
| local_guard_configuration_invalid | Repair the guard configuration; do not disable it |
| provider_credentials_missing | Configure provider credentials privately on the host |
| No provider receipt / saved reply | Treat the turn as failed, not as successful chat |
