# Exact Fold Dragon reconstruction — original model recovered

On 2026-11-17, the missing original was reconstructed from the retained source lineage. All four generated model SHA-256 values matched the historical receipts exactly. The final file is **463,149,740 bytes**, SHA-256 `c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a`, identical to the existing repository pin. No digest, artwork, geometry, or animation substitutions were made.

| Stage | SHA-256 |
| --- | --- |
| Retained relief base | 377153261f91a4815cc8e3ffa2e3b9bbb633b4c82ef544edcc1b71cbe3e5c8ed |
| GPU sculpt candidate | 8adfb562e6b784b97e57a42e11b5347ab26379526d09806b3a60d1adcdcbc433 |
| Flank study | 5535732fedb393f79f6b319bf60b7a5834691270276c4cade8d7972ce17e3ec9 |
| Artisan | 95541717327877a5be79fb3531e79334d423398450069d3369d0f951ac51da86 |
| Fold | c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a |

The actual GLB header, all 56,307 buffer-view ranges, 56,296 accessor count, 380 animations (320 ground, 20 orbit, 20 takeoff, 20 landing), 108 joints, 365,997 vertices, 719,312 triangles and four embedded image SHA-256 identities were independently inspected. The embedded maps match the original Fold archive's basecolor, normal, ORM and emission PNG bytes. This is source/model identity evidence, not a physical rendering qualification.

## Reproduce or restore

The source replay uses the six pinned ZIPs listed in the script, with their released NumPy arrays and maps. Python 3, NumPy, SciPy and Pillow and the native GL loader import dependencies are needed; no rendering or GPU work is requested by the exporters. Provide an existing trusted output parent directory with ample space (recommend at least 8 GiB scratch space). The observed reconstruction used Python 3.13, NumPy 2.3.5, SciPy 1.17.0 and Pillow 12.3.0. The historical choreography import is restored from the continuum source; the already-encoded normal map is reused rather than generating a different PNG bitstream.

```sh
python scripts/rebuild_emerald_exact_binary.py rebuild --directory /retained/archives --output /assets/emerald_continuum.glb
```

Alternatively, place the two exact transfer parts in one directory:

```sh
python scripts/rebuild_emerald_exact_binary.py assemble --directory /retained/parts --output /assets/emerald_continuum.glb
```

Then use the existing offline preflight, web installer and native stage scripts with the two original ZIPs and recovered GLB. The two original ZIPs remain pinned and separate from the model. Do not store the model or transfer parts as ordinary Git blobs. The successful reconstruction used retained user assets outside Git; this PR preserves the rerun path, not the binary bytes. The exact-head CI for the new runner is separate. The earlier retained archive CI reached the Emerald test step successfully and then failed at inherited creator contracts; downstream companion, typecheck and export were skipped.

Do not enable equipment, merge, publish a release or infer Unreal, RTX, artist, device or performance acceptance solely from this recovery.
