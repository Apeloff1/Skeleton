# Jeeves local AI: guarded exact-ID Docker first launch

**Source candidate only.** This is a fresh-install controller stacked after
the canonical local-AI runtime, complete image archive, tagless image transport
and exact-ID Compose overlay. It has NOT yet qualified a real four-image
application install with licensed GGUF and physical GPU hardware.

It is NOT a migration, upgrade, repair, restore or overwrite operation.
Live Docker application state changes require explicit operator opt-in.

## Fresh-install state machine

| Phase | Required proof | Side effects | Result |
|---|---|---|---|
| Image archive | Four pinned config IDs, all rootfs diffIDs, out-of-band receipt SHA-256 | None | Offline image custody |
| Image import | Local staged IDs matching source and destination platform | Explicit Docker image store mutation | Untagged images |
| Compose binding | Exactly four IDs and whole canonical Compose config equality | NEW private overlay and receipt | No-pull Compose admission |
| Fresh-state plan | No existing target containers or named data volumes | None | Candidate for fresh installation |
| Native GGUF | Actual pinned model preflight and engine digest-bound one-shot by exact ID | Network-disabled, read-only one-shot | Local model turn qualified |
| Recheck | Source and target state unchanged after GGUF execution | None | Best-effort race reduction |
| Fresh launch | Operator volume-creation approval; explicit no-build/no-recreate/no-pull | NEW writable volumes and app containers | Started, not guarded chat |
| Post-start | Live Docker image IDs, labels, networks, ports, mounts, resources and health | None | Physical container observation |
| Backend | Existing local-provider readiness response | None | Provider observation only |

A passing earlier phase never authorizes later phases automatically.

## Read-only fresh-state admission

    python scripts/local_ai_docker.py --mode cpu plan-fresh-offline-launch \
      --directory /home/operator/private-offline-ai/transfer-001 \
      --expected-receipt-sha256 INDEPENDENT_64_HEX_RECEIPT_SHA256 \
      --overlay-directory /home/operator/private-offline-ai/bindings/local-cpu-001

The plan denies missing image IDs, tampered archives or overlays, platform or
accelerator mismatch, noncanonical Compose security, existing target
containers (running OR stopped) or any existing canonical Mongo, engine,
backend or frontend named volume. Other unrelated volumes are not touched.
An existing application is a recovery problem, NOT a first-install problem.

## Explicit opt-in to state creation

Only on a new project with no canonical containers or volumes:

    python scripts/local_ai_docker.py --mode cpu launch-fresh-offline \
      --directory /home/operator/private-offline-ai/transfer-001 \
      --expected-receipt-sha256 INDEPENDENT_64_HEX_RECEIPT_SHA256 \
      --overlay-directory /home/operator/private-offline-ai/bindings/local-cpu-001 \
      --allow-new-app-volumes

This command qualifies a real local GGUF turn FIRST, checks the original
image and empty-state conditions again, and only then runs:

    docker compose <canonical-files-and-private-ID-overlay> up -d \
      --no-build --no-recreate --pull never --wait --wait-timeout 180 \
      mongo skeleton backend frontend

The displayed <canonical-files-and-private-ID-overlay> is descriptive, not a
literal argument. The actual implementation constructs the approved Compose
argv from the repository's canonical operator; it does not interpolate
arbitrary shell commands or let the user alter the admission policy.

No image pull, build, tag, pruning, down or automatic destructive rollback is
used. Optional Chroma is not started. The startup CAN create writable Docker
volumes and the services CAN write application state.

## Read-only runtime attestation

    python scripts/local_ai_docker.py --mode cpu attest-running-offline \
      --directory /home/operator/private-offline-ai/transfer-001 \
      --expected-receipt-sha256 INDEPENDENT_64_HEX_RECEIPT_SHA256 \
      --overlay-directory /home/operator/private-offline-ai/bindings/local-cpu-001

The returned JSON whitelists four roles and exact image IDs, running and
health observations, local-only ingress, one canonical network and exact
storage mounts. It never prints raw Docker inspect JSON, env credentials,
private volume contents or generated model text.

Post-start rejection conditions include substituted image IDs, wrong project
labels, a non-running process, privilege escalation, dropped read-only root,
lost capability restrictions, missing PID/memory limits, unexpected network
membership, a non-loopback host port, volume substitution, altered mount
read-only status, extra mounted files or unhealthy required healthchecks.

## Limits requiring explicit operator acknowledgement

1. First-install-only: existing Docker state is denied, not migrated. Any
   partially initialized volumes after a failed first launch remain intact.
2. Empty-state admission is NOT atomic with Docker writes. Other Docker
   clients can race the preflight. No-recreate prevents a known class of
   container replacement but does not transactionally protect volumes.
   Do not use this on shared daemons with competing external writers.
3. No hosted model inference: the one-shot GGUF uses Docker network=none
   and matching pinned executable/model bytes. The subsequent app services
   run on the canonical private Compose bridge; a Compose-only source check
   does NOT establish firewall-enforced internet egress isolation.
4. No protected chat claim: live backend provider availability alone does not
   prove active GGUF tokenizer, bounded independent reviewer, source/writer
   epoch fencing, complete adversarial replay or guarded chat receipts.
5. GPU/Windows-WSL2: real NVIDIA/ROCm driver, kernel, device mapping,
   memory/resource pressure and physical execution are separate gates.
6. Database recovery: named volume creation is NOT coherent Mongo/SQLite
   backup, shared Mongo epoch authority, writer quiescence or restore proof.
7. Security and release: exact-head mandatory security/native/device checks
   and independent signed provenance remain mandatory.

Source tests use synthetic Docker JSON and adversarial mutations. The parent
CI already verified tagless image transfer and Compose parser behavior with
disposable synthetic assets. The new first-launch controller has NOT executed
production containers in CI. Keep every stacked draft review-only.
