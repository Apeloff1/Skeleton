# Cross-era homebrew platform registry and port planning

**Owner:** `skeleton/ai/game_builder` (canonical AI-native game builder).  
**Status:** candidate platform coverage and deterministic port blueprints, **not** native game compilation, tooling certification, or release approval.

## Why discontinued and obscure platforms matter

Every catalogued system can be selected as a **creative basis**, as a **destination for a porting plan**, or both. Production discontinuation is *not* a reason to drop it. PC, game console, handheld, arcade board, calculator, mobile runtime, toy and hobbyist microcontroller histories all contain valuable gameplay and interaction designs.

The registry includes 300 entries and 21 approximate capability presets. It deliberately tracks the unusual, regional, transitional and failed commercial systems alongside mainstream machines. Examples: Fairchild Channel F, Interton VC 4000, Super Cassette Vision, Watara Supervision, Gamate, Mega Duck, WonderSwan and SwanCrystal, Neo Geo Pocket, PC-FX, FM Towns Marty, CD-i, CD32, Pippin, Nuon, Jaguar CD, Gizmondo, Tapwave Zodiac, Atari ST, RISC OS, ZX80/81, Thomson MO5, MSX, PC-88/98, X68000, Sega Model 2/3 arcade, Konami GX, Sega NAOMI, TI/HP calculators, Palm OS, BREW, J2ME, Arduboy and RP2040.

The UI-neutral selector in `editor_platforms.py` exposes all 300 systems as browsable source/destination options, with search, family/type filters and a full target-directed design graph. It never presents an unverified native exporter as available. Connect the selector through the product API and actual editor surface in a subsequent integration step.

The approximate tier and preset are **planning heuristics**, not machine-specific hardware specifications, verified instruction sets, video timings, RAM addresses or supported executable targets. Individual regional models, hardware revisions, add-ons, controllers, multiformat media and FPGA reimplementations need machine-specific adapters and test evidence.

## Source and destination are separate

A historical game design **basis** is not a permission to copy the original game's ROM, art, soundtrack, script, trademark or characters. Port planning accepts only an original/cleared homebrew project with a stable rights-evidence reference. User-provided SHA-256 is an *assertion/reference*, not proof of independent verification.

Every platform is a candidate for source or destination **planning**. Only an independently qualified adapter can turn a blueprint into a real output format. The current registry marks **every toolchain unverified**; there are zero verified game binaries, builds, or releases implied by this change.

Source systems that are difficult to target directly may still serve as inspiration for original mechanics and aesthetics while shipping to an accessible destination. Do not infer that emulation or porting justifies proprietary BIOS, firmware, decryption keys, SDK redistribution or a commercial game rip.

## Modes

| Mode | Direction | Design rule |
| --- | --- | --- |
| `faithful` | Any -> any | Preserve original game loop, identity, visual language; adapt controls, storage, audio and rendering |
| `enhanced` | Usually old -> modern | Increase animation, lighting, fidelity, simulation, accessibility and controls **without** losing the original style |
| `reverse_constrained` | Modern -> earlier hardware | Quantize/retarget tiles, sprites, palette, sound channels, world scale, performance and inputs |
| `cross_hybrid` | Two cleared homebrews -> any | Combine authorized mechanics, transform expressive assets and give the result an independently authored identity |

Portability is a directed **planning graph**. The same source project may have multiple independent target blueprints, each with its own constraints and digest. `compile_port_route` is a multi-destination fan-out from the original platform, **not** a verified multi-hop build chain. Multi-target planning is not evidence that an intermediate port exists. A true build pipeline must hand each verified artifact to the next independently qualified target adapter.

## Example

    from skeleton.ai.game_builder.platform_registry import default_registry
    from skeleton.ai.game_builder.port_planner import (
        HomebrewSource, PortMode, PortRequest, compile_port, compile_port_route
    )

    registry = default_registry()
    print(registry.summary())

    owned = HomebrewSource(
        project_id="my-original-game",
        platform_id="bandai_wonderswan",
        rights_basis="project_owned",
        evidence_sha256="a" * 64,  # replace with genuine, independently reviewed evidence
        creative_identity=("tactical turn sequence", "ink outlines", "short rounds"),
    )
    design = compile_port(PortRequest((owned,), "windows_modern", PortMode.ENHANCED))
    assert design.planning_status == "design_only_toolchain_unverified"
    assert not design.releasable

    variations = compile_port_route(owned, (
        "windows_modern", "sega_dreamcast", "nec_pc_fx", "arduboy",
    ))

## Build adapter qualification still required

1. Confirm **independent homebrew source authority** through the existing game-builder rights ledger, source inventory, license/attribution rules and legal review where needed.
2. Register an **appropriately licensed/redistributable SDK or open toolchain** for that exact platform and hardware revision, plus reproducible tool versions, build environments and target ABI.
3. Implement/export the real format: ROM, optical-disc image, cassette/disk executable, arcade board image, native installer/package or firmware, as appropriate. No HTML-only substitution for native console outputs.
4. Verify frame pacing, video mode, memory and VRAM budgets, palette behavior, audio channels, input mapping, save compatibility, accessibility, reliability and original-game replay.
5. Validate on legal emulator configurations and, where possible, representative physical hardware. Where native toolchains are infeasible, document the limitation and produce **design-only** output rather than claiming support.
6. Bind each passing gate to independently inspectable receipts; only then may a separate release pipeline certify the adapter and artifact.

## Coverage expansion policy

A platform record must have a stable identifier, historically reasonable name/family, interaction/render profile, explicit catalog maturity and test coverage. **Do not invent machines merely to reach a quota.** Distinguish a real standalone platform from a software peripheral, an arcade board family, a configuration or a secondary display accessory. Confirm historical details and local toolchain availability before promoting records to hardware-verified status.

Licensing and trademark policy is fail-closed. "Clone", hybridization and decompilation do not waive copyright, trade secret, access-control, trademark, privacy or contractual obligations. Original gameplay concepts may inspire wholly new homebrew, but copied distinctive expression and misleading branding require review. Successful compilation is not legal clearance.

## Regressions and integration

- `skeleton/testing/test_game_builder_platform_porting.py` tests catalog breadth, data validation, missing targets, rights rejection, determinism, retro-to-modern feature expansion, modern-to-retro demotion, hybrid behavior and multi-destination planning.
- `platform_catalog.json` is included in the installed Python package data.
- `platform_registry.py` and `port_planner.py` are canonical AI-native modules, not mirrored legacy forge code.
- This increment adds **design/inventory capability**; future increments must supply compiler adapters, tested toolchains, genuine game content generation, real target packages and independently signed builds.
