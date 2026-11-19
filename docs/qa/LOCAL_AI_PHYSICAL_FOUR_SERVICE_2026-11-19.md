# Physical synthetic offline Docker four-service acceptance

This experimental exact-head GitHub CI probe is **not** a production
standalone Jeeves deployment. It proves essential Docker Engine runtime
semantics using four disposable containers and no downloaded base image.

## Construction and execution

On an isolated Ubuntu 24.04 Linux amd64 GitHub runner:

1. Compile a minimal raw x86_64 Linux-syscall executable locally with the
   already installed GNU assembler and linker. It needs no libc, shell,
   package manager, DNS, model weights or Python inside Docker.
2. Package the ELF into a one-file rootfs tar. Create four distinct random
   synthetic Docker images using local Docker image import, differing only
   by a role environment marker.
3. Generate a random Compose project with exactly four synthetic service
   roles: mongo, skeleton, backend and frontend. All references are
   immutable local image IDs; none use external registries.
4. Set an internal-only bridge, read-only root filesystems, ALL capabilities
   dropped, no-new-privileges, bounded memory/CPU/PID budgets, four
   disposable named data volumes, and process healthchecks.
5. Run Docker Compose with --no-build --pull never --wait, requiring real
   healthchecks instead of treating container existence as readiness.
6. Physically inspect every running image ID, project/service identity,
   cap/security/resource boundaries, internal-only bridge and absence of
   any published host port.
7. Run one actual UDP sendto attempt from each disposable container toward
   an external address. The static probe exits success ONLY if the kernel
   refuses to route the outbound packet. This is narrower than a complete
   firewall or exfiltration security assessment.
8. Tear down ONLY the randomly generated test project and its disposable
   volumes and remove ONLY its random synthetic image references. Never
   run global prune, remove-orphans, modify user volumes or touch real
   application images.

The physical scope is intentionally Linux amd64 only; cross-architecture
Linux/arm64, physical Windows 11/WSL2 and NVIDIA/ROCm must be independently
validated on compatible devices. The test is a source-bound, review-only
CI qualification job, not a program that the normal installer runs.

## Evidence limitations

A successful receipt can prove: four actual synthetic containers executed,
four distinct local image IDs matched, four healthchecks passed, the
container root filesystems were read-only, security limits remained, all
service members used the internal bridge, and four external UDP sends were
rejected by the Linux kernel. It can also prove that Docker image import
and Compose launch did not require registry pulls.

It CANNOT prove:
- four production Skeleton/Jeeves/Mongo/backend/frontend images can boot
  with their real app binaries and user secrets on a given host,
- licensed GGUF model weights or native llama.cpp execution works,
- GPU/WSL2 driver offload, long-context streaming or pressure adaptation,
- active tokenizer/reviewer trust, protected chat or actor epoch fencing,
- Mongo majority durability and coherent cross-store database recovery,
- signed/reproducible release provenance or user installation readiness.

Do not claim 100 percent readiness or merge/release authorization from
this physical synthetic check. Keep the feature branch draft and
require actual target-device acceptance with independent evidence.
