# First playable app journey — source qualification, not release

The canonical application CLI can now run a real, offline original-game
production path: typed intent → Jeeves/Dragon studio orchestration → compiled
winning game → adversarial mirror review → browser and Godot source export →
independent in-process SHA-256 pin → canonical source re-read and replay.

```sh
python -m skeleton app studio-journey \
  --intent original-intent.json \
  --output ./new-original-game \
  --trusted-local-operator
```

The intent uses the existing `GameBuildIntent` JSON contract. The destination
must be new and under an operator-controlled directory. The command refuses
existing outputs, malformed source, unapproved local operation and unsafe
POSIX publication. A failed post-export verification leaves the directory
**unqualified** for explicit operator inspection; it does not delete an
untrusted or concurrently replaced path.

A successful receipt proves actual canonical Python replay of the generated
game's winning actions and byte-for-byte source identity. The trusted digest
is taken from the in-memory package before export, not from a mutable file
after publication. For independent later verification, distribute the digest
separately and use the canonical `verify-export` command. This is not a
publisher signature, consumer install, native Godot run, legal clearance,
hardware test, or release approval.

The app command intentionally does not invoke a provider SDK or claim local
model inference. The guarded AI readiness and provider activation boundary
remain separate; a user can still author an original typed game and obtain
a playable source package while offline. Device, rights, security, malware,
accessibility and platform gates remain held until independently qualified.

Focused regression:
`python -m pytest -q skeleton/testing/test_app_studio_journey.py
skeleton/testing/test_secure_export_publication.py
skeleton/testing/test_dual_runtime_verify.py`.
