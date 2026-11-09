# NDS/DSi and PBP container evidence — 2026-10-15

The canonical ROM ingestion path now recognizes .nds and .pbp as *source format evidence* without enabling new native executables.

**NDS / DSi cartridge:** uses the actual 512-byte Nintendo card header, checks the supported unit-code domain and bounded header length (up to 0x4000), binds the ARM9 and ARM7 executable file spans, optional FNT/FAT table spans, title/game/maker codes, stored logo and header CRCs. The DSi card unit field labels the source as DSi when present but **does not** claim that the current core can execute DSi-specific encrypted features.

**PSP/PS1 PBP:** requires the exact 40-byte `\0PBP` signature and eight monotonic, bounded little-endian section offsets. Records nonempty PARAM.SFO, icon, image, sound and executable/data segment spans and hashes. An EBOOT package can contain PSP, PS1, firmware update or encrypted material; the parser does not decrypt it or infer playable content.

Both formats produce `rom_header_observations` under the existing `GameLearningIngestor` owner, with content SHA-256 and no downloaded binaries, BIOS or games. Structural rejection prevents out-of-bounds sections. The measured game quality, bootstrap, actual gameplay and emulator compatibility remain unknown. Canonical hardware denominator remains 169.

References: https://dsibrew.org/wiki/DSi_Cartridge_Header, https://github-wiki-see.page/m/Roughsketch/mdnds/wiki/NDS-Format, https://www.psdevwiki.com/ps3/PBP.

**Review gates:** valid structure is not a license grant or runtime capability; separate actual core execution evidence and operator rights review are required before promoting AI training assets.
