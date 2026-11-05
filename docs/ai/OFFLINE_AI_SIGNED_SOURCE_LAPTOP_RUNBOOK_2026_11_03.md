# Signed original sources → real local GGUF: operator runbook

## Authority and limits

The signed source manifest is a data-ingestion trust boundary. It is not a
parallel inference server, a new database, a network fallback or permission
from model-generated text. The existing installed GGUF supervisor, private
ExecutionSpine SQLite database, signed work-order ingress, and replay are
the only execution and durable state owners.

A source HMAC binds source bytes, tenant, subject, model and tokenizer to an
independent trusted operator key. An associated external rights-review SHA
represents the operator's declaration and does not independently prove
copyright clearance or third-party permission. All source text is untrusted
quoted DATA, not system instructions or tool authority.

The manifest verifier uses a domain-separated HMAC over canonical JSON.
It rejects duplicate JSON keys, nonfinite numbers, unexpected fields,
invalid source/actor IDs, bad model digests, extra source rows, invalid
approval or old/future timestamps. A signed document never grants
automatic command execution.

## Platform and private roots

This command requires Linux or Windows 11 with a supported WSL2 Linux
environment. Do not treat a Windows host path or shared/untrusted mount
as equivalent to private Linux filesystem and model-custody guarantees.

Choose operator-owned private absolute paths for the real installed model,
private execution spine, signed work-order database, approved source files
and operator authorization artifacts. Illustrative locations:

    /private/installed-model
    /private/spine
    /private/work-orders
    /private/sources
    /private/operator

The selected source and operator directories must be operator-owned,
private mode 0700 directories on the Linux/WSL2 filesystem. The descriptor
walker rejects a symlink at *every path component*, including ancestors.
The private signed manifests use mode 0600. Each source is a bounded regular,
singly linked local file, owned by the execution UID and not group/world
writable.
Symbolic links, FIFOs, devices, relative paths, parent traversal and
oversized files are refused. No implicit mkdir, model installation or
automatic repair is attempted by this CLI.

## Step 1 — independent rights and installed model identity

Obtain an actually installed, rights-reviewed GGUF using the existing
guarded installer. Its installed shard and archive receipt, and the
tokenizer SHA, are determined by the canonical installer and supervisor,
not inferred from a model name, URL, generated string or source filename.

The existing read-only laptop doctor can inspect model and state identity:

    python -m skeleton.ai.runtime.operational_ai.laptop_runtime.cli_doctor \
      --model-root /private/installed-model \
      --state-dir /private/spine \
      --tenant local --subject owner \
      --model-sha256 ACTUAL_MODEL_SHA256 \
      --tokenizer-sha256 ACTUAL_TOKENIZER_SHA256

A doctor report is still not a completed native inference or device
acceptance test.

## Step 2 — independently review original sources

Put between one and eight approved source files in the private source
folder. Maximum original byte length is 262144 per file. Obtain an
independent rights-review receipt for each one and determine its original
SHA-256 from actual verified bytes.

Create a private source record file, record.json, with these exact fields
(replace every illustrative value with operator-verified values):

    {
      "schema": "offline-signed-source-manifest.v1",
      "tenant": "local",
      "subject": "owner",
      "model_sha256": "ACTUAL_64_CHAR_LOWERCASE_HEX_MODEL_SHA",
      "tokenizer_sha256": "ACTUAL_64_CHAR_LOWERCASE_HEX_TOKENIZER_SHA",
      "issued_at": 1,
      "expires_at": 3601,
      "nonce": "ACTUAL_32_CHAR_LOWERCASE_HEX_RANDOM_NONCE",
      "sources": [{
        "source_id": "document",
        "filename": "source.txt",
        "sha256": "ACTUAL_64_CHAR_LOWERCASE_HEX_SOURCE_SHA",
        "rights_receipt_sha256": "ACTUAL_64_CHAR_LOWERCASE_HEX_RIGHTS_RECEIPT_SHA",
        "approved": true
      }]
    }

The shown timestamps are not real approvals. Use a trusted current
host Unix timestamp; require issued_at <= now < expires_at with at most
3600 seconds validity. Nonce generation is external and unpredictable.
The signer never invents an approved license or source digest.

## Step 3 — sign through the trusted operator channel

Set the independently provisioned secret SKELETON_OFFLINE_OPERATOR_KEY_HEX
in the trusted local runtime environment. Its value must be 32 to 4096
bytes of high-entropy key material represented as lowercase hex. Do not
print, log, expose to the LLM, paste into prompts, store in source code
or place it on a command line.

After reviewing the original source rights:

    python scripts/sign_offline_ai_source_manifest.py \
      --record /private/operator/record.json \
      --source-root /private/sources \
      --signed-out /private/operator/signed.json \
      --approve-source-rights

The signer verifies an operator HMAC then re-opens each actual original
file through a pinned directory descriptor. It checks inode/mtime/ctime,
file type and permissions, source byte length, exact signed SHA and path
replacement before output publication. It publishes exclusively with
mode 0600, fsync, and no overwrite. The signer never performs native
inference. Correct actual source/security faults rather than bypassing
verification.

## Step 4 — explicitly invoke one real native GGUF turn

With a verified installed model and matching signed source principal:

    printf 'What does the approved source actually establish?' |
    python -m skeleton.ai.runtime.operational_ai.offline_cognition.grounded_cli \
      --model-root /private/installed-model \
      --state-dir /private/spine \
      --queue-dir /private/work-orders \
      --source-root /private/sources \
      --source-manifest /private/operator/signed.json \
      --tenant local --subject owner \
      --context 2048 --max-new-tokens 128 \
      --threads 4 --gpu-layers 0 --token-ceiling 16384 \
      --prompt-stdin --approve-native --emit-answer

The program accepts a bounded 8192-byte UTF-8 question via stdin only.
The emit-answer flag explicitly permits the user-visible original model
output to be printed; omit that flag for digest-only diagnostics.
The trusted operator key never appears in process arguments or output.

Before any costly GGUF activation, the command checks signed manifest
time/scope, user question and source SHA receipts. Activation delegates
to the actual installer-verified supervised backend. Native work uses
the existing HMAC WorkOrder authority and independently authorized
operator key, consumes a fresh admission nonce transactionally, reserves
real SQLite capacity, fences native dispatch uncertainty, and performs
exactly one supervised generation.

After the canonical durable commit, a read-only replay checks the
response hash and native model/tokenizer identity. This is not a second
generation. A clean success reports output digest, source receipt hash,
token charge, model scope and a non-release status.

On any ambiguous dispatch, process crash, changed source, failed manifest,
expired grant, bad native result or resource fault, do not retry that
request. The authoritative SQLite store and spine must reconcile it
read-only with separate operator intervention. No assistant-created
model release, hidden provider fallback, automatic rights approval,
or retry is allowed.

## Qualification and attack matrix

Source-only tests (no model weights, no native GGUF generation):

    python scripts/check_offline_cognition.py --focused
    python scripts/check_offline_cognition.py --full
    python -m unittest skeleton.testing.test_offline_cognition_manifest_custody -v
    python -m unittest skeleton.testing.test_offline_cognition_manifest_matrix -v

The manifest matrix contributes 256 original adversarial cases:
64 forged source digests that pass signature shape but fail byte proof;
64 validly signed foreign-subject manifests rejected by scope checks;
64 parent-directory traversal filenames rejected before file IO;
64 altered HMAC nibbles rejected before source data access.
These extend 256 existing retrieval/quotation scope attacks and 2560
operator-domain profile admission source fixtures. Fixture counts are
not evidence of real model correctness.

## Mandatory release holds

This signed-source path remains draft and unqualified until exact-final-SHA
Merge Readiness, Backend Quality, App Foundation E2E, Workflow Input
Security, Sealed Context Guard, Artifact Policy, Malware Gate, Repository
Hygiene, Secret Scanning and Dependency Review have all succeeded.

Also required: independent model-rights review, real target Windows/WSL2
clean install, device-pressure qualification, a real GGUF native response,
postcommit replay, native cancellation, cold recovery and privacy/
retention checks. Skipped, missing, pending, cancelled and superseded
checks are not passing results. An apparent green source fixture result
never proves model, device or release acceptance.

## Symlinked-ancestor and path-replacement hardening

All three source-custody boundaries now use the pre-existing canonical
`open_private_root` descriptor walker, rather than checking only the final
directory or filename. This applies to: reading original source documents,
reading a signed operator manifest, and exclusive publication of a signed
manifest. A symlink in any ancestor component is rejected. The root of
each operator-approved source or signing directory must be private mode
0700, even when an intermediate component is under a normal system root.

Open-file inode, size, mode, mtime and ctime checks are repeated after
content reads, and final-path metadata is compared using `dir_fd` and
`follow_symlinks=False`; old or modified original bytes are rejected
against the signed SHA-256. A symlinked parent alias must never be
silently resolved into an otherwise approved source folder.

Focused regression coverage includes symlink ancestors of each of those
three boundaries, along with the existing malicious basename, FIFO,
hardlink, writable directory and filename replacement probes.

Nothing in these source-level guards constitutes a completed target
Windows 11/WSL2 clean install or any real GGUF model E2E result.
