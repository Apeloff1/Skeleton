# Native libretro core controller handshake — 2026-10-15

This patch improves the existing Jeeves sandboxed native libretro host and worker. It adds support for libretro environment commands 11 (SET_INPUT_DESCRIPTORS) and 35 (SET_CONTROLLER_INFO). The worker records bounded native core input labels, per-port supported devices and a separate routing verdict. The host validates these declarations independently and binds their digest to the environment and transition evidence.

An absent core device announcement stays unknown rather than certified. Explicit nonstandard peripherals are refused when a core announces that it does not support them. The canonical comparison controller deck can now display native legends below the game image, keeping the viewport unobstructed. Input on disconnected ports is rejected.

## Construction levels L00–L13

- L00 Ownership: existing Jeeves emulator host and worker.
- L01 Architecture: no additional service, provider or storage root.
- L02 Contracts: maximum 4 ports, 32 device options per port, 128 input legends.
- L03 Admission: registry-approved core and governed media required.
- L04 Runtime: native advertisement during core initialization and loading.
- L05 State: announcement observed, not hardware functionality proven.
- L06 Security: fixed-size data-only labels, exact approved source identities.
- L07 Failure: invalid declarations, contradictory verdicts and disconnected-port input fail closed.
- L08 Evidence: digest, status, core ID and native input legends.
- L09 Economics: no polling/AI model calls added for descriptor collection.
- L10 Deployment: existing Linux bubblewrap worker unchanged.
- L11 Evaluation: focused callback and host validation tests added, not executed.
- L12 Operations: operator separately builds, approves and qualifies lawful cores.
- L13 Rollback: reverting changes needs no data migration.

## Operator qualification

Run the focused test file and architecture checks separately; no runtime or native-ROM qualification is claimed by this change. The existing source-pinned recipes are not precompiled cores. Native controller metadata is not proof of accurate physical mappings. Core subclasses, lightguns, sensors, GPU context and disc-changing support remain outside this implementation.
