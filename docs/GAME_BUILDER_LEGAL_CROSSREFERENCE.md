# Game hardware history, spiritual successors and lawful independent homebrew
**Scope:** Project policy and traceable research references, not legal advice, legal clearance, or a representation that all historical systems are fully inventoried.  
**Reference review date:** 2026-10-09. Verify changes in law and policy before release.  
**Executable policy:** `skeleton/ai/game_builder/legal_paths.py`; `legal_port_bridge.py`.  
**Source matrix:** `skeleton/ai/game_builder/legal_authorities.json`; `skeleton/ai/game_builder/rights.py`.

## The central distinction — games are not consoles

An independent developer can commonly make **a new, original game** inspired by a genre, gameplay principle, period technique, or machine specification without obtaining a licence from a particular game's copyright owner, **provided no protected expression or other rights are infringed**. Reusing a console's architectural principles, writing an independent engine, and publishing independently authored mechanics are different acts from distributing the console maker's firmware, copying a game ROM, reproducing a character, or selling a bypass tool.

An original game developed **for a console** is not automatically an authorized commercial game for that console. The console may impose hardware boot restrictions, proprietary software-development terms, encryption/signing keys, authorized distribution channels or technical protection measures. These operate on different legal and technical axes. A software licence restricting the distribution of a specific commercial game to one machine does not automatically monopolize its *gameplay ideas* across every other machine; nor does making a clone with new code automatically clear its art, characters, story, title, audiovisual presentation or proprietary assets.

Likewise, **spiritual successor is a description of creative relationship, not a statutory exception**. It permits no automatic reuse of copyrighted expression and no implication of official endorsement. Making the old game easier to play, prettier, more accessible, or available to a new audience does not turn an infringing derivative work into a lawful independent project. The path is new expressive authorship or specific permission.

## Cross-jurisdiction decision matrix

| Scenario | Original authorship | Hardware/console rights | Default project policy | Required evidence |
| --- | --- | --- | --- | --- |
| Entirely original homebrew, common mechanics, fresh characters/audio/art | New expression | Public documented interface, no bypass | Design allowed; release not certified | Authorship and build provenance, own rights packet |
| Independently authored *spiritual successor* featuring genre ideas but fresh distinctive identity | New expression | Same independent target rules | Design allowed; release not certified | Clean design log, expression comparison, marketing review |
| Original game explicitly targeted at an abandoned cartridge console using a legal open toolchain | New expression | Toolchain use and device access must be checked | Design allowed; target-specific release gate | Homebrew code, ROM layout knowledge, compiler/version/emulator/hardware receipt |
| Remaster or continuation of someone else's game, characters, story, soundtrack or distinctive audiovisual material | Reuses protected expression | Separate native target questions | Block absent authorization; review actual licence | Rights-holder permission, adaptations/territories/media/sublicensing |
| Third-party commercial game executable/ROM rehosted on a new console or PC | Copied code/asset | New device not relevant to content rights | Block unlicensed incorporation/distribution | Genuine game content rights; no default preservation exception |
| New game with very similar recognizable look-and-feel but no copied code | Independent code; expression may still be similar | Platform independent | Human review required | Substantial-similarity, artistic, trademark, trade-dress analysis |
| Game mechanic / interface behavior reconstructed from independently learned facts | Underlying ideas and principles | Use permitted documented public API | Usually design-admissible | No unauthorized code/assets, independent implementation record |
| Use third-party engine, stock art, music, libraries | Mixed | Target rules still apply | Hold if scope, attribution or sublicensing missing | Per-material allowed uses, license texts and provenance |
| Study lawfully obtained software to achieve limited independent interoperability | Independently authored interoperability target | Local legal scope and necessity | Legal review, never auto-approved | Lawful access, unavailable info, necessity, no unnecessary code copying |
| Original game needing console DRM/secure-boot bypass to launch | New expression | Protection measures may still be enforceable | Legal review; no bypass instructions/tools | Jurisdiction-specific TPM/contract assessment and lawful distribution alternative |
| Original game requiring platform-private keys/BIOS/firmware from third party | New expression | Proprietary materials separate from game | Block inclusion; pursue licensed or independently developed alternative | Permission and non-proprietary build path |
| Historical archival metadata (machine IDs, family names, display/input traits) | Facts/ideas | No game/firmware bundled | Inventory/analysis only | Per-record provenance; provenance is not hardware SDK verification |
| Museum/archive exception for discontinued commercial games | May contain copyrighted expression | Exception usually beneficiary/purpose-specific | Special counsel review, not commercial successor permission | Current applicable preservation exception/eligible institution |
| A name, logo or marketing presentation implying the original publisher endorsed this new game | Mixed | Trademark and consumer law separate | Block misleading affiliation; clear any marks | Distinct naming/trademark clearance |
| Modified commercial SDK without a licence | Source may be independent | Licence and contractual restrictions remain | Hold independent of game originality | Valid SDK entitlement or permitted replacement toolchain |
| First-party/third-party commercial console storefront release | Original or licensed | Platform distribution and signing requirements | Human and platform certification needed | Store agreement, certification, rights and content policy |

**None** of these labels is an objective legal determination for a specific game; project policy is conservative and declares no global blanket permission.

## Norway: specific statutory cross-reference

The current [Norwegian Copyright Act / åndsverkloven](https://lovdata.no/nav/lov/2018-06-15-40/kap3) § 41 generally addresses permitted use of computer programs and observing/studying program behavior by a person entitled to use the copy. § 42 contains a conditional interoperability reverse-engineering rule. The statute requires lawful use, information not readily available, and acts confined to what is necessary for independent interoperability; information obtained under that exception may not be used to create substantially similar expression or unrelated uses. The technical-measures provisions include §§ 99–101 in [chapter 7](https://lovdata.no/nav/lov/2018-06-15-40/kap7). The legal scope depends on exactly what hardware, program, and audiovisual content are involved.

**Implication:** Nintendo-style hardware binding does *not* make every independent game design copyright infringement, but it also does not automatically authorize decryption, console firmware distribution, circumventing protections or commercial storefront publication.

## EU/EEA: functionality and hardware protection are distinct

[Directive 2009/24/EC](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32009L0024) Art. 1(2) excludes software ideas/principles, including interface principles, from copyright in computer programs. Arts. 5 and 6 address lawful observations and strictly scoped interoperability decompilation, not general free copying. The CJEU's [SAS Institute v World Programming, C-406/10](https://infocuria.curia.europa.eu/tabs/redirect/juris/liste.jsf?language=en&num=C-406%2F10) helps distinguish functionality from expressive source code and manuals.

The CJEU's [Nintendo v PC Box, C-355/12 (2014)](https://curia.europa.eu/site/upload/docs/application/pdf/2014-01/cp140009en.pdf) held that the anti-circumvention treatment of console measures requires a fact-sensitive assessment, including proportionality and whether the measures prevent unauthorized copies versus lawful third-party uses. **It did not universally legalize modchips or console bypasses**. Directive 2001/29/EC and national measures remain relevant.

## United States: game rules vs visual expression

The [U.S. Copyright Office's game guidance](https://www.copyright.gov/register/tx-games.html) explains that game ideas and methods of play are not in themselves copyrighted; original text, pictorial, audio and other expression can be. The opinion in [Tetris Holding v Xio Interactive (2012)](https://law.justia.com/cases/federal/district-courts/new-jersey/njdce/3%3A2009cv06115/235418/61/) is a warning: independently coded games can still infringe by copying protectable artistic/visual expression.

[17 USC § 1201](https://www.govinfo.gov/content/pkg/USCODE-2024-title17/html/USCODE-2024-title17-chap12-sec1201.htm) separately regulates circumvention of technological measures. The [Copyright Office's 2024 exemptions](https://www.copyright.gov/1201/2024/) are narrow, with conditions including preservation activities. Do not treat an abandoned console or discontinued game as universally public-domain or unrestricted.

## Original work and third-party games: exact compliance boundary

The archive uses **independent original gameplay** rather than undocumented "legal avoidance."

- **Allowed for design review:** understand mechanical rules, genre conventions, frame pacing, controller mapping, screen style, tile size, system architecture and non-protectable historical hardware facts; create *new* source, graphics, levels, writing, music and characters.
- **Rights-dependent:** incorporate a licensed asset, adapt a franchise, work with source files released under open licences, distribute a ported third-party homebrew project with a licence covering that destination, or release under platform-specific SDK terms.
- **Blocked as unlicensed expressive reuse:** commercial ROM transfer, copied game source, ripped textures, character models, soundtrack samples, story scripts, levels, protected audiovisual scenes, proprietary keys or firmware.
- **Human/legal review:** near-identical trade dress, franchise marketing, platform restrictions, access-control circumvention, patent/design rights, reverse engineering beyond narrow interoperability conditions, or uncertain asset provenance.

A *fan-made* or *free* game does **not** gain a blanket exception by being noncommercial. Conversely, a commercially released spiritual successor can be independently lawful when it truly creates original expression and respects other applicable rights.

## Policy API and integration

    from skeleton.ai.game_builder.legal_paths import (
        CreativeMode, HardwareAccessFacts, HomebrewLegalRequest,
        Jurisdiction, MaterialKind, MaterialRecord, assess_homebrew,
    )
    from skeleton.ai.game_builder.legal_port_bridge import propose_rights_aware_port
    from skeleton.ai.game_builder.port_planner import HomebrewSource

    own_material = MaterialRecord(
        "new_tiles", "art", MaterialKind.ORIGINAL_EXPRESSION,
        evidence_sha256="b"*64,  # example only, not a rights certificate
    )
    facts = HomebrewLegalRequest(
        project_id="new-adventure", source_platform_id="nintendo_famicom",
        target_platform_id="windows_modern",
        mode=CreativeMode.SPIRITUAL_SUCCESSOR,
        jurisdictions=(Jurisdiction.NO, Jurisdiction.EU_EEA),
        materials=(own_material,), hardware=HardwareAccessFacts(),
        rights_packet_sha256="a"*64,
    )
    result = assess_homebrew(facts)
    # Even the favorable result is a DESIGN admission, never legal certification.
    assert result.design_admissible and not result.release_authorized

    authored = HomebrewSource(
        "new-adventure", "nintendo_famicom",
        "project_owned", "a"*64, ("new characters", "new levels"),
    )
    proposal = propose_rights_aware_port(authored, facts)
    assert proposal.design_stage_admitted
    assert not proposal.release_certified

## Gates before a commercial build

The project must supply independently verifiable material provenance and the applicable licence texts. Next, reviewer(s) must check jurisdiction, expression, characters, musical/audio rights, brands, trade dress, SDK, patents, technology measures and distribution terms. Only after a separate native export/build on the requested target, acceptance replay, malware/keys scan, actual game publication authorization and any platform approvals can that artifact be considered for a product release.

No automated scoring of "looks different enough" is proof of non-infringement. Artistically distinctive reimplementation can be lawful, but whether any particular game crosses an infringement threshold is not mechanically decidable. Unsupported rights or unverifiable licenses must never silently pass.

## Why hardware archives matter for evolutionary games

The archive is a map of design constraints and available *ideas*, not a library of someone else's executable games. An original game can learn from the Vectrex's vector display, the Game Boy's tiles, WonderSwan portrait layouts, Dreamcast VMU interaction, Commodore SID audio, arcade timing, and modern GPU pipelines. Each port can reinterpret those technical primitives with **new expressive creative content**, enhancing accessibility, animation, lighting and physics on more capable targets without implying that the old game itself has been licensed or converted.

This is also true when an old game was sold exclusively for a named machine: *hardware availability, software distribution rights, and independent game ideas are separate questions*. That distinction supports creative spiritual successors, while preserving legal boundaries.
