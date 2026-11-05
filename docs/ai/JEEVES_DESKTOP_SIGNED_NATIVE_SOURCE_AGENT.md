# Advanced Jeeves desktop — operator-signed native source agent

This is a real integration of the existing `NativeJeevesRuntime`,
`NativeSignedEvidenceProvider`, `BoundSignedSourceTool`, HMAC-signed
`SignedSourceManifest` and canonical installed-GGUF source fence into the
desktop UI. It adds one useful operational capability: **during a bounded
Jeeves agent run, the model may ask for read-only retrieval from an
operator-approved, signed local source collection**.

It does **not** grant the model general filesystem access, network access,
shell commands, credentials, external API keys, source modification, Git
commits, automatic tool approval or another model. Plain chat and durable
restart work orders retain their previous no-tool behavior.

## Operator enablement

A source lookup grant is OFF by default. To enable it:

1. Use the repository's existing offline-cognition signed-source manifest
   workflow to create and independently approve source receipts. The
   manifest must attest to the **real installed GGUF model and tokenizer
   SHA-256, tenant, subject, original source bytes, issuance and expiry**.
   This desktop does not generate signing keys or mint a manifest.
2. Place the manifest under a protected private POSIX/WSL2 directory
   and supply the independent operator key through the already existing
   `SKELETON_OFFLINE_OPERATOR_KEY_HEX` environment mechanism. Do not put
   its bytes in chat, the GUI fields, subprocess arguments, committed
   source files or terminal output.
3. In the desktop startup pane, set **Approved source root** and
   **Signed source manifest** to absolute local paths. Select the checkbox
   **I explicitly authorize bounded read-only lookup of operator-signed
   sources**. Set maximum source count (1–6) and per-run lookup calls (1–3).
4. Start the local native model. **Before any GGUF load or new SQLite
   session**, the worker verifies the signed manifest HMAC, principal,
   declared model/tokenizer scope, expiry and descriptor-anchored original
   file bytes. A missing key, changed path, expired signature or bad HMAC
   prevents model activation entirely.
5. Once real GGUF startup succeeds, the exact current native identity must
   match the signed scope again. The host binds `BoundSignedSourceTool`
   to the one installed worker. The private ready receipt tells the UI
   whether the source tool was actually installed and binds the original
   signed manifest SHA-256.
6. Use **Signed source status** for a read-only status and source inspection
   response. With a signed tool enabled, select **Run native Jeeves agent**
   to permit up to the operator's specified number of signed lookups.
   These are **only** the existing `jeeves_signed_source_lookup` tool with
   `READ_ONLY` risk, explicitly registered as a host-side capability
   and granted to that single bounded `RunInputs`.

### During execution

The existing strict agent runtime owns planning, tool admission, budgets,
verification, evidence and answer formation. A model can propose a bounded
source-search query, not an arbitrary path. It cannot invent a tool grant
or retrieve unsigned files. The existing source tool re-reads and verifies
HMAC expiry/original source bytes at selection, before the host observation,
and on source selection replay. The desktop also checks current signed
source before and after the agent run.

The source content is untrusted evidence, **not** instructions to the
host. Model output may still be mistaken or contain malicious suggestions;
no external or write tools are made available. Verified responses disclose
a source manifest SHA-256, actual count of lookup calls, original model
SHA-256, run ID and answer digest without disclosing signing keys or
private source paths.

When the checkbox is OFF, the desktop launches without either signed-source
CLI paths or any read-only tool grant; unexpected tool calls are rejected.
An expired or revoked source, model swap, unknown native effect or broken
SQLite evidence receipt is a terminal hold. The worker will not silently
downgrade to unsigned evidence, fall back to hosted providers, reissue
uncertain inference or re-sign source packages.

## Source-only qualification vs real evidence

Tests for this feature exercise strict startup permissions, grant shape,
no-tool default, principal/source bounds, model-call quota and mid-run
source revocation. They do not simulate real GGUF inference as a release
proof. Before consumer delivery, the target Windows 11/WSL2 laptop must
still run an actually licensed installed local model, execute an
operator-signed source lookup, receive a committed answer, replay it
across a cold restart and pass required native memory pressure,
cancellation, security and release qualification.

This feature does **not** replace the simpler **Search project sources**
GUI. That GUI remains a manual read-only search which only sends a selected
excerpt after a human attaches it to a later prompt. The signed-source tool
is the only dynamic model-requested retrieval capability, and is separately
opted in before model startup.
