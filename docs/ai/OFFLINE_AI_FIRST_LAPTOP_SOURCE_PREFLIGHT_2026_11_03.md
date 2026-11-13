# First-laptop source preflight — actual original bytes, no model invocation

The purpose of `first_laptop_preflight` is to detect bad source, private
filesystem, model-installation and budget prerequisites *before* loading an
installed GGUF. It does not replace the existing model installer, native GGUF
supervisor, signed SQLite work orders, model-rights review or cold restart
qualification. It is read-only and never signs jobs or performs inference.

## Exact requirements

The operator must already have an installed, rights-reviewed model with
canonical installed archive and model SHA receipts. A trusted source
manifest must have been signed using an independently provisioned secret
`SKELETON_OFFLINE_OPERATOR_KEY_HEX`, and must not have expired. The original
source files must match their signed SHA-256 digests and tenant, subject,
model and tokenizer identity exactly.

The original source folder, execution-spine folder, signed work-order folder
and manifest's parent directory must be operator-owned mode 0700 on a Linux
filesystem (including WSL2 Linux storage); no symlinks are permitted in any
path ancestor. Original source and signed manifest files must be regular,
singly linked, owned by the active UID and not group/world writable. The
source HMAC file must have independent operator authorization.

Set the key in the protected local operator environment, without logging
or putting it on a shell command line. Paths are deliberately supplied
as absolute arguments; no automatic directory creation or file migration
is performed.

## Run

```bash
python -m skeleton.ai.runtime.operational_ai.offline_cognition.first_laptop_preflight \
  --model-root /private/installed-model \
  --source-root /private/sources \
  --source-manifest /private/operator/signed.json \
  --state-dir /private/spine \
  --queue-dir /private/work-orders \
  --tenant local --subject owner \
  --context 2048 --max-new-tokens 128 \
  --threads 4 --minimum-free-bytes 1073741824
```

The command exits 2 on an untrusted/unsupported/insufficient prerequisite
and reports only a redacted error category. It exits 0 only when source
HMAC, original source byte custody, the installed model archive receipt,
private root descriptors, Linux kernel observation and real filesystem
headroom all pass. Its successful status is deliberately
`preflight-source-verified-release-held`, not a ready-for-release claim.

## What the report does NOT prove

The preflight does not load or tokenize the model, perform inference,
verify the activated tokenizer or GPU driver, test native cancellation,
exercise real memory pressure, prove a clean Windows 11/WSL2 install,
verify external intellectual-property rights, write or replay SQLite
work, measure token quality, certify device performance or grant release.

When the preflight succeeds, use the separately approved real native path
in `OFFLINE_AI_SIGNED_SOURCE_LAPTOP_RUNBOOK_2026_11_03.md`. Keep the
existing signed GGUF work-order flags and final-head CI gates intact.
A successful doctor is not permission for unattended native dispatch.

## Focused source regression

```bash
python -m unittest skeleton.testing.test_offline_cognition_first_laptop_preflight -v
python scripts/check_offline_cognition.py --focused
python scripts/check_offline_cognition.py --full
```

The test suite includes 25 contract cases. The positive installed-model
receipt is *explicitly mocked*: these tests validate fail-closed plumbing
and original source digest handling, not actual GGUF weights or license
rights. This module is intentionally imported by the existing source
qualification runner without adding another GitHub Actions workflow.
