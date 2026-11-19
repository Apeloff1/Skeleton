# Emerald offline visual assets
This is a local, optional presentation asset extension to the canonical Jeeves crawler and Dragon companion. It does not create a second crawler, provider, scheduler or knowledge store. Capture, policy, XP and review remain owned by existing application services.

Install the exact separately supplied `emerald-skeleton-web-assets.zip` from the repository root:
```sh
python frontend/scripts/install_emerald_assets.py /path/to/emerald-skeleton-web-assets.zip
python frontend/scripts/install_emerald_assets.py --verify
python frontend/scripts/test_emerald_assets.py
```

Run the existing frontend build/export after installation. The static directory is ignored by Git; deployment must explicitly stage it before building. Never deploy an unverified replacement under v1. Missing assets must fall back to the existing companion. No external CDN or automatic download. New versions need a new source-reviewed pin and visible mode change. Web package contains actual artwork, motion and renderer sources, not generated showcase boards; the model is separately distributed. Native reconstruction is experimental, no artistic approval or physical RTX qualification is asserted. Native auxiliary equipment remains off. The canonical application must remain operational without the asset pack.

Qualification: local installer positive and negative tests; exact-head frontend typecheck/export, actual installed browser playback, real authenticated capture fixture, motion accessibility, account/session change, native Unreal compilation, and physical RTX trace are distinct gates.