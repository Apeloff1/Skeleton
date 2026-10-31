# Offline dual-runtime package verification

Canonical owner: `skeleton.ai.game_builder`. A game operator can verify an
existing exported HTML5/Godot source package without running an external model,
network request, native compiler or browser. The verifier requires an
**independently obtained SHA-256 digest of release.json**; a digest read only
from the untrusted package itself is not a trust anchor.

Run:

```sh
python -m skeleton.ai.game_builder.original_game_studio_cli verify-export \
  --package /path/to/export \
  --expected-manifest-sha256 <64-lowercase-hex-digest> \
  --trusted-local-operator
```

The operation walks every filesystem component using POSIX directory handles
and `O_NOFOLLOW`; unsupported platforms fail closed until their own
handle-safe implementation is qualified. It rejects symlinks, hardlinks,
unexpected files, nonregular entries, unsafe paths, duplicate JSON members,
nonfinite JSON, noncanonical release metadata, unknown source versions, missing
manifest entries, oversized objects, digest mismatches and mutated replay
proofs. The verifier reconstructs the actual typed world and independently
re-executes the winning action trace through the canonical Python game
simulator. Every declared browser and Godot source file is SHA-256 checked.
It reads but never modifies the original package.

The returned deterministic receipt identifies the exact manifest pin,
world and replay digests, source file/byte counts and executed replay steps.
It deliberately leaves `godot_executed`, `rights_certified` and
`release_certified` false. A valid source package is not proof of
consumer device operation, legal originality or publication authorization.

## Construction implications (L00-L13)

L00/L01: owned by the existing game-builder package, no new runtime root.
L02: accepts dual-runtime-package v1 and emits verification receipt v1.
L03: requires explicit operator authorization and independent source pin.
L04/L05: descriptor-anchored read, manifest audit, canonical replay, receipt.
L06: no external files, plugins, network, scripts or credential-bearing calls.
L07: all errors fail closed; no writes or automatic cleanup.
L08: bounded counts and deterministic evidence for operator diagnostics.
L09: no new provider, infrastructure, model or cloud spend.
L10: regression tests cover real playable exports and hostile paths.
L11: POSIX-only; Windows/macOS device qualification remains outstanding.
L12: existing package export remains unchanged; no migration needed.
L13: no release, legal, native execution or consumer readiness certification.
