# Emerald retained original archive recovery

The exact original web and Atelier Fold source archives were located in retained user files on 2026-11-17. An independent read-only audit of their materialized bytes (not a GitHub Actions or device result) measured:

| Archive | Bytes | SHA-256 | Audit |
| --- | ---: | --- | --- |
| emerald-skeleton-web-assets.zip | 48249605 | 354b7d1dadc02f7919aa6b9b802f949894d2cb6ea0e0e493db9ba9d819d22851 | CRC success, 19 payload hashes and lengths matched pinned manifest, no extra entries |
| emerald-atelier-fold-source.zip | 194733639 | 093feccb25846b39eefe94a4385873e25df125371544545042c3d34b3fe879f5 | CRC success on all 122 entries (201082994 uncompressed bytes), no case-fold duplicates |
| emerald_continuum.glb | 463149740 expected | c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a expected | Not recovered |

Web manifest SHA-256: 4a62d4e967a33af327e4741060df603c7e002b47a8e6230d5aa8224fbc5a013c. The native source manifest declares the pinned model length and digest, 380 clips and 108 joints; these declarations are not an inspection of the missing model. The archive contains the compact ruby equipment GLB, not the standalone Fold Dragon model. Older model versions must not be substituted or repinned.

To independently rerun on a machine holding the files:

```sh
python scripts/qualify_emerald_retained_archives.py --directory /path/to/retained-assets
```

Exit 2 means at least one exact archive was unavailable or not verified; exit 3 means the two archives qualified but standalone model custody did not. Exit 0 means all three exact byte identities and the two archive checks passed; it still does not confer structural model, native staging, Unreal, RTX, artistic, or release qualification. Exceptions are non-success. This audit does not install assets permanently or execute bundled code.

The original archive binaries are not embedded in Git or a release. Copying them into a user-authorized deployment is a separate operation. Preserve all existing review, merge and release holds.
