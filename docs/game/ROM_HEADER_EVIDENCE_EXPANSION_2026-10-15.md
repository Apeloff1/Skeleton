# Additional ROM evidence formats — 2026-10-15

This pass expands the canonical **source-header observation** path in `skeleton/jeeves/game_learning_ingestion.py`. It does not add a new independent emulation runtime or assert any new ROM can be played.

| Format | Identification | Captured, bounded metadata | Fail-closed cases |
| --- | --- | --- | --- |
| Atari Lynx .lnx | `LYNX` header at byte 0, 64-byte header | Bank-0/1 page sizes, revision, title, manufacturer, rotation, AUDIN/EEPROM fields, exact content digests | Missing/truncated header, absent cartridge data, unknown bank sizes, revision or orientation |
| Atari 7800 .a78 | Header version + `ATARI7800` from offset 1, 128 bytes | Declared/supplied cartridge bytes, mapper bitset, controller types, TV flags, save peripherals, regions with SHA-256 | Truncated body, invalid declared size/version, absent header |
| Sega SMS / Game Gear | `TMR SEGA` at 0x7FF0, 0x3FF0 or 0x1FF0 | System/region nibble, checksum field, version/ROM-size nibbles, content identity and header offset | Bad signature or unsupported region identity |

Only signed, structurally bounded forms are admitted as recognized headers. Unheadered or ambiguous cartridge dumps remain unclassified rather than guessing a platform from a filename. ROM contents are not bundled, transmitted or executed. Parsed data is labeled `rom_header_observations`, not gameplay behavior or mapper compatibility. Canonical Dragon hardware targets remain unchanged at 169.

Header interpretation references: https://www.smspower.org/Development/ROMHeader, https://7800.8bitdev.org/index.php/A78_Header_Specification, https://atarigamer.github.io/lynxcc/lnx.html.

## Remaining acceptance work

Per-core video/audio timing, BIOS choices, mapper/flash and peripheral behavior, cartridge checksums, replay stability and legal source rights still require real emulator execution with independently qualified homebrew inputs. No model parameter gains are inferred from header metadata.
