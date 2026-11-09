# C64 and Atari original-homebrew loader validation

Implementation sign-off: Codex, 2026-10-10, PR #3604 continuation. This is native
format acceptance, not physical-hardware, emulator-gameplay or legal approval.

## Capability

The existing native retro intake now accepts eight scoped formats: its prior six
cartridge/tape targets plus Commodore 64 default cc65 PRG and Atari 400/800
48KB-class XEX. Existing C64/Atari native build CI scripts consume these canonical
parsers and the bounded no-follow file reader, rather than a token search or a
RUNAD-presence check. No new capability owner, firmware or service is introduced.

C64 parsing binds the $0801 load address, bounded first BASIC line link, numeric
SYS token/body, end-of-program pointer, actual file-backed entry byte and default
RAM envelope below $D000. A SYS-looking byte elsewhere is not a launcher. Custom
BASIC programs, alternate start addresses and custom banking layouts require a
separate scoped validator; this parser does not claim a universal PRG ABI.

Atari parsing bounds the file and segment table, refuses reversed/truncated
segments and writes into system/I/O/ROM ranges, and requires complete separate
vector records. INITAD must reference code already loaded at that step; its
initialization segment may subsequently be overlaid, matching cc65's loader
ordering. Other program overlap is refused. RUNAD must be unambiguous and point
to a nonempty file-backed byte in the final loaded image. The parser interprets
loader metadata and does not execute any arbitrary 6502 instructions.

Primary format authorities: [cc65 linker formats](https://cc65.github.io/doc/ld65.html),
[cc65 C64 linker configuration](https://github.com/cc65/cc65/blob/master/cfg/c64.cfg)
and [cc65 Atari target](https://cc65.github.io/doc/atari.html). Local acceptance
uses actual compiled outputs in addition to synthetic malformed fixtures.

## Local acceptance

156 focused tests passed across native retro intake, C64/Atari source emission,
byte intake, desktop executable structure and strict release pipeline. Adversarial
fixtures cover dangling and partial vectors, empty entry bytes, malformed BASIC
links, system-region writes, ambiguous overlap, initialization order, excessive
segments, changed hashes and the existing no-clearance receipt invariants.

Both generated original games were actually compiled with cl65:

- C64: 2,953 bytes; SYS $080D points to file offset 14; SHA-256
  82ecf73e8bd966aa4f549094b9d3d2b987ddf58614936624ebdce3dddae87046.
- Atari: 3,448 bytes; four segments, INITAD $2E47 and RUNAD $2001; SHA-256
  a314401f3cf8e5a8214d4a89b0281a6f870b4a33e45bd71f2ff72e3e755b3b6b.

Architecture, construction, capability interfaces and enterprise-superiority
schema checks pass. The lane retains the baseline stale VOL-000 implementation
notes. The shared bounded provider-parser cache fix from PR #3605 is carried here
without changing validation coverage. Two cache regressions pass. The mandatory
bounded provider scan and exact-head hosted checks must be assessed
separately; this is not an all-gates or release-completion signoff.

## L00–L13 and rollout

L00–L03 retain native exporter/intake, game-builder and independent rights owners.
L04–L05 parse the verified file snapshot into bounded loader layout evidence.
L06–L07 preserve no-follow intake, hash identity, refusal and retry behavior.
L08–L09 expose source/digest/address metadata without private payloads and bound
bytes/segments. L10 exercises actual cl65 outputs and corruption fixtures.
L11–L12 require no data migration: roll back parser consumers and the two added
format IDs; previously emitted original game sources remain intact. L13 requires
fresh required CI, real target gameplay, hardware acceptance, independent rights
review and separately authorized release. No receipt flag self-promotes those.
