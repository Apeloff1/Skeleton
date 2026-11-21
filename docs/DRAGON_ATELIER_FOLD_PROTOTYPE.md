# Emerald Atelier Fold — original asset prototype

Only the final fold reconstruction is targeted. Earlier rendered illustrations, painted poses, 2.9D layers and the orange UI companion are not the same asset. Historical build reports identify emerald-atelier-fold/Models/emerald_continuum.glb and emerald-atelier-fold-source.zip, 360 rebuilt animation clips, 86,294 pose samples, 64/64 improved ground poses, 138.2 mm reported minimum clearance and 20 retained predatory flights. These figures are reported historical evidence, not measurements of bytes in this PR. The previous Apex Continuum reported a 92-joint rig; the prototype conservatively requires at least 92 unique skin joints and 360 distinct clips. The final file is not included and the thresholds may require reconciliation against the genuine archive.

## Offline asset admission

An operator who has the original model and independently trusted SHA-256 can run:

    python scripts/dragon_atelier_admit.py /trusted/emerald_continuum.glb --sha256 <trusted-digest> --families /trusted/clip-families.json > admission.json

Use explicit exact exported clip names in the four family arrays: ground (at least 300), takeoff, flight, landing (at least 20 each); every exported clip must be assigned exactly once. No synthetic aliases count. The digest must be obtained independently from the original custodian, not inferred from a filename or a copy under review. The receipt is not a signature, a guarantee of safe graphics-driver execution, or evidence of the native Unreal/RTX path. Only embedded resources are admitted. Keep the original ZIP and source assets separately under custody; no archive extraction or external acquisition occurs here.

A prototype renderer must remain opt-in, presentation-only, local, and bounded; preserve the ordinary two-dimensional companion on absent/rejected data. Capture, promotion, consent, archive and model authority remain in their existing authenticated boundaries. Do not merge or release on source-only evidence. Handcrafted AAA+ anatomy, native texture provenance, real-device resource limits, physical membrane simulation, compiled Unreal and physical RTX remain independent holds.
