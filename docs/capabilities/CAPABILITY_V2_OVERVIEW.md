# Local Model Console Emulator Capability — v2 (10× Expansion)

Date: 2026-10-15  
Schema: skeleton.local_model.console_emulator_capability.v2  
Fleet: 83 declared libretro cores

## What changed from v1
- Rich static database (`fleet_database_v2.json`) with era, category, accuracy, BIOS flag, and notes for every core.
- Full filtering (`filter`, `search`, `by_era`, `by_category`).
- Multi-stage curriculum generator.
- Multiple export formats (JSON matrix, choices, CSV, Markdown table).
- Expanded tool schema and `dispatch()` entry point for model loops.
- Detailed vs compact model cards.
- CLI v2 with 15+ commands.
- Comprehensive test suite (runs under pytest when available).
- Live registry overlay still supported; falls back cleanly.

## Key numbers
- 83 cores total
- 20 require BIOS/firmware (never downloaded by this layer)
- Eras: 8bit (26), 16bit (20), handheld (17), 32bit (8), arcade (6), pc (3), 64bit (3)
- Categories: home-console (39), home-computer (21), handheld (17), arcade (6)

## Files in this expansion
- `local_model_console_capability_v2.py` — main module
- `local_model_console_capability_cli_v2.py` — full CLI
- `test_local_model_console_capability_v2.py` — tests
- `fleet_database_v2.json` — source of truth for static metadata
- `QUALIFICATION_MATRIX_V2.json`
- `EMULATOR_CHOICES_V2.json`
- `FLEET_SUMMARY_V2.json`
- `CORE_TABLE_V2.md`
- `FLEET.csv`
- Plus the original v1 artifacts for reference

## Usage
```bash
python3 local_model_console_capability_cli_v2.py summary
python3 local_model_console_capability_cli_v2.py filter --category handheld
python3 local_model_console_capability_cli_v2.py recommend --goal accuracy
python3 local_model_console_capability_cli_v2.py plan --hardware snes --accuracy
python3 local_model_console_capability_cli_v2.py curriculum
python3 local_model_console_capability_cli_v2.py markdown > cores.md
```

In code:
```python
from local_model_console_capability_v2 import make_capability_v2
cap = make_capability_v2()
print(cap.model_card("detailed"))
print(cap.plan_session("nes"))
```

## Safety (unchanged and strengthened)
- No native library load
- No network
- No firmware fetch
- Prompt length capped
- Status truthful (declared / installed / qualified)
- Isolated host remains the only execution path

The local model now has a complete, filterable, exportable, curriculum-aware capability surface over the entire 83-core fleet.
