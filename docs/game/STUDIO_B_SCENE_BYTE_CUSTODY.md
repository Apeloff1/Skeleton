# Studio B offline scene byte custody (WIP)

The byte boundary is deliberately separate from filesystem persistence. It accepts
only exact `bytes`, rejects payloads exceeding 2 MiB before parsing, requires
strict UTF-8 and unique JSON keys, and uses the existing canonical scene
replay verifier for semantic custody. The transport checksum is an integrity
check, **not** an authentication signature. Untrusted source authorship must be
enforced by the caller. `encode_scene_bytes` emits canonical JSON; its output
can be passed to `decode_scene_bytes` after process restart.

Acceptance: create a session, collect the original demo key, serialize bytes,
discard the in-memory session, decode and resume through the victory ending.
Negative cases: oversized input, malformed UTF-8, duplicate object keys,
nonfinite numbers and tampered digest. This does not establish Windows device
readiness or crash-atomic filesystem persistence. Future canonical file writer
must use descriptor-anchored paths, durable fsync and atomic replacement.

Focused test: `python -m unittest skeleton.testing.test_scene_bytes -v`.
