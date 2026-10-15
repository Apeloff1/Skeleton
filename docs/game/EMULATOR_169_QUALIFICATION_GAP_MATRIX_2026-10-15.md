# Actionable 169-target emulator gap inventory

Run:

```bash
python3 scripts/audit_game_emulator_169_targets.py \
  --registry /srv/approved/cores.json \
  --output-dir /srv/reports
```

The core manifest is optional. When omitted, the command uses the current `SKL_GAME_EMULATOR_REGISTRY`; if that is also unset, it reports an empty installation rather than inventing built cores.

Two reports are generated: `emulator_169_target_gaps.json` (full machine-readable SHA-linked matrix) and `emulator_169_target_gaps.html` (offline searchable/filterable UI). The latter filters installed/approved, mapped-but-missing, unmapped, and generic-controller targets.

The canonical Dragon registry currently declares **169 hardware identities**. The libretro mapping table supplies declared compatible cores for **99** and no libretro mapping for **70**. **137** target controller panels are generic rather than hardware-labeled. These are source-declaration counts, not measured boot or emulation-fidelity rates.

For every hardware target the dashboard separates actual operator-approved core installation, declared candidate core IDs, pinned source build recipes, native platform/toolchain/SDK status, controller profile precision, real-boot qualification flags and the next concrete implementation task. Installed means approved core/firmware metadata passed the existing registry inspector, **never that an actual ROM played**.

Important: some of the 70 unmapped identities include native PC/OS platforms, specialist handhelds and proprietary modern consoles. Their appropriate implementation may be a legally available native toolchain adapter, historical research, or a platform-specific emulator—not another arbitrary libretro core. No unavailable vendor SDK, protected content or ROM execution is implied.

`tests/test_game_emulator_169_gap_matrix.py` adds source-level coverage contracts for all 169 catalog IDs, counts, integrity of the generic-controller classification, and the offline UI. Tests have not been executed against an installed emulator here.
