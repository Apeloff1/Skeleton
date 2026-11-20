# Standalone Jeeves Docker: physical isolation, recovery and release holds

**Scope:** review-only source candidate, stacked on the canonical local-AI
Docker runtime, offline image transport, image-ID Compose binding and guarded
fresh-launch controller.

## Internal-only application network

The opt-in docker-compose.local-ai.yml overlay now explicitly marks the
single canonical application bridge internal: true. Localhost-published
ports alone do NOT prevent outbound connections.

The offline Compose verifier rejects any noninternal canonical bridge.
The real running-container attestor separately inspects the actual Docker
daemon bridge identity, driver, Internal flag, Attachable flag, exact
Compose project/network labels, and all four service memberships.
Before creating new app state, the first-install controller checks EVERY
existing project container using daemon-wide Compose labels, including
stopped, unknown and orphaned members.

A physical CI probe creates one random internal-only bridge, validates its
Docker metadata using the same runtime guard, rejects a noninternal
adversarial inspection, and removes only that random CI-owned bridge.
It never starts an application container or accesses production volumes.

**Boundary:** Docker network metadata does NOT replace packet-level
egress tests, host firewall policy, WSL2 networking qualification or
proof that a network is truly physically air-gapped.

## Source and destination file-byte rehydration

The cold backup already rehashed source volume bytes but lacked a
corresponding create-only rehydration rehearsal. A new host-local tool
now independently verifies the complete cold archive and copies each
indexed file into a NEW owner-private target directory using streamed,
exclusive writes. It independently hashes all destination files, matches
the exact sorted index, and writes the receipt last.

First create an operator-owned private parent directory (0700).
Then run:

    python scripts/local_ai_docker.py rehearse-byte-restore \
      --source /home/operator/private/cold-001 \
      --destination /home/operator/private/rehydrated-001 \
      --expected-receipt-sha256 INDEPENDENT_COLD_RECEIPT_SHA256

    python scripts/local_ai_docker.py verify-byte-rehydration \
      --source /home/operator/private/cold-001 \
      --destination /home/operator/private/rehydrated-001 \
      --expected-receipt-sha256 INDEPENDENT_COLD_RECEIPT_SHA256

A trusted source must provide the exact receipt SHA-256 independently
from the archive. The source and target may never overlap. Existing
destinations, symlinks, hardlinks, duplicate paths, modified files,
undeclared payloads and interrupted copies fail closed. No Docker
volume or container is modified; no credential or model byte is included.

**Boundary:** A byte-level rehearsal is NOT coherent Mongo/SQLite/Chroma
recovery. A true production recovery needs writer exclusion, majority
durability, Mongo logical consistency, SQLite WAL checkpoints and
actual application replay. Never attach this new directory as a
live database volume without independent database restore admission.

## Physical CPU/GPU/daemon capacity admission

    python scripts/local_ai_docker.py --mode cpu probe-device

CPU, NVIDIA and ROCm are explicit modes. The read-only probe checks
Linux Docker daemon OS/architecture, CPU affinity and quotas, memory,
free local storage and the matching physical GPU interface when chosen.

This does NOT execute a licensed GGUF, CUDA kernels, ROCm inference,
high-context pressure, WSL2 cross-host qualification or native tokenizer.
Source-level device tests do not replace real device execution.

## Read-only readiness matrix

    python scripts/local_ai_docker.py --mode cpu audit-offline-readiness \
      --directory /home/operator/private/transfer-001 \
      --overlay-directory /home/operator/private/binding-001 \
      --expected-receipt-sha256 INDEPENDENT_IMAGE_RECEIPT_SHA256

Optional independent file-byte restoration evidence requires all of:
--restore-source, --restored-directory and --expected-restore-sha256.

This matrix checks verified Compose/images, physical device inventory,
running image/network/mount isolation and backend provider observation.
It can independently rehash a restored file-byte copy.

A successful local observation NEVER raises the following missing gates:
licensed actual model inference, trusted active tokenizer, independent
bounded reviewer, end-to-end protected chat, shared majority-durable
Mongo writer epoch/migration, cross-store coherent recovery, pressure
and physical WSL2 qualification, or independently signed release custody.

No mocked source test, simulated native call, container health flag,
backend provider availability or self-hashed JSON may authorize release.

## Independent acceptance gates still required

| Gate | Independent evidence before release |
|---|---|
| Four canonical images | Physical production import/start with no registry pulls |
| Native GGUF | Real pinned executable/model/tokenizer, on selected hardware |
| Independent reviewer | Bounded independent policy authority with replay denial |
| Protected chat | Authenticated backend-to-engine guarded request and real response |
| Mongo/writer epochs | Majority-durable shared epoch and external writer exclusion |
| Recovery | Coherent database snapshot + isolated live restore/replay rehearsal |
| Hardware | Real GPU/CPU pressure, Windows 11/WSL2 drivers and restart |
| Release | Full exact-head CI and independent signed provenance |

Keep every stacked branch draft and review-only. Do not auto-merge,
release, prune data volumes or download models as a workaround.
