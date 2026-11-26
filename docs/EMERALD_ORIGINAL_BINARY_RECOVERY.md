# Original binary recovered — 2026-11-17

The separately retained original Fold source ZIP and web ZIP were retrieved from their original saved files, not regenerated. Both match the unchanged independent repository pin and passed ZIP CRC verification. All 19 web manifest entries were separately hashed.

The large original GLB itself was not present as a retained downloadable file. The original authoring chain was recovered: exact strain-aware GLB, saved GPU candidate geometry, saved multilevel flank geometry and original combined normal PNG, Artisan native maps/geometry, original Fold fit parameters and the original deterministic bake. The four successive rebuilt SHA-256 values were checked:

- Strain input: 377153261f91a4815cc8e3ffa2e3b9bbb633b4c82ef544edcc1b71cbe3e5c8ed
- GPU candidate: 8adfb562e6b784b97e57a42e11b5347ab26379526d09806b3a60d1adcdcbc433
- Flank study: 5535732fedb393f79f6b319bf60b7a5834691270276c4cade8d7972ce17e3ec9
- Artisan: 95541717327877a5be79fb3531e79334d423398450069d3369d0f951ac51da86
- Fold: c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a

Final length 463149740 bytes, hash exactly equals the existing repository pin. The original verify_export.py was rerun against the real model and parent, verifying 380 clips, 360 rebakes, 20 unchanged orbit clips, exact body tracks and unchanged geometry/skin/material definitions and binary prefix. The actual model JSON provided the exact ordered catalogue. All four embedded image payloads independently matched the corresponding original source archive files. These operator observations are recorded in emeraldOriginalRecovery.json (not a signed CI attestation).

The inspector now defaults to the verified catalogue, and still independently checks the complete selected GLB hash and structure. No original bytes were replaced by placeholders. The binary and ZIPs are distributed separately; they are not committed into Git, and the connector does not expose large binary upload. For two-part transport, use:

```sh
python scripts/join_emerald_original.py /trusted/downloads /trusted/downloads/emerald_continuum.glb
```

Then use the exact existing offline installers and model viewer. Keep the original pack separate from any future artistic upgrade. Neither byte identity nor the original export audit qualifies Unreal compilation, physical RTX execution, continuous collision freedom or human artistic signoff.
