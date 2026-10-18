"""Improve — "like Elden Ring" raises the house, not a copy of the game.

Aspects that move: neo/rms ppl, steps, genos G, era dialect, mix heads.
Aspects that must not move: third-party prose, secrets, assets.
Order-of-magnitude is the trajectory target. Laws gate every write.
"""
from __future__ import annotations

from typing import Any, Dict, List

from skeleton.cortex.antiplag import distill_dialect, guard
from skeleton.cortex.laws import LawError, check
from skeleton.cortex.refs import lookup, record_provenance

MAX_IMPROVE_ROUNDS = 256
MAX_IMPROVE_STIMULUS_CHARS = 32_768

ASPECTS = {
    "soulslike": (
        "soulslike ttk elite dread bonfire rest extraction heat",
        "plan tensor hp dps stagger posture",
        "walk fog gate elite pack trash mix",
    ),
    "roguelike": (
        "roguelike lattice mix trash elite boss seed",
        "plan tensor ttk heat run reset",
        "shop relic floor climb",
    ),
    "metroidvania": (
        "metroidvania backtrack map lock key",
        "plan tensor exploration pack ability gate",
        "room graph traversal",
    ),
    "extraction_now": (
        "extraction_now ttk elite dread extract extract",
        "plan tensor loot heat zone timer",
        "squad wipe extract window",
    ),
    "cozy": (
        "cozy harvest era crop season",
        "plan tensor day cycle gift",
        "town route rest",
    ),
    "cozy_wholesome": (
        "cozy harvest era crop season",
        "plan tensor day cycle gift",
        "town route rest",
    ),
    "boomer_shooter": (
        "boomer_shooter movement gun poetry ttk trash speed",
        "plan tensor arena strafe rocket armor pickup",
        "mix trash=6 elite=1 boss=0 slack=0.82",
    ),
    "arcade_golden_age": (
        "arcade_golden_age score attack ttk trash wave",
        "plan tensor coin multiplier high score",
        "mix trash=2 elite=0 boss=0 slack=0.88",
    ),
    "horror_survival": (
        "horror_survival dread scarcity heat vent ammo",
        "plan tensor safe room stalker elite tension",
        "walk collapse extract late lock door bound",
    ),
    "immersive_sim": (
        "immersive_sim systemic emergent vent hack stealth",
        "plan tensor physics simulation stackable verbs",
        "room graph traversal multi solution",
    ),
    "crpg": (
        "crpg party initiative turn tactical dice check",
        "plan tensor build dialogue branch companion",
        "mix trash=4 elite=2 boss=0 slack=0.74",
    ),
    "tactics_grid": (
        "tactics_grid elevation flanking cover action points",
        "plan tensor squad turn order overwatch",
        "mix trash=5 elite=2 boss=0 slack=0.76",
    ),
    "fighting_game": (
        "fighting_game frame data hitconfirm neutral rollback",
        "plan tensorspacing punish cancel meter",
        "HP = DPS x TTK mix trash=0 elite=1 boss=1",
    ),
    "bullet_heaven": (
        "bullet_heaven swarm synergy evolutionxp magnet",
        "plan tensor horde density cooldown scaling",
        "mix trash=8 elite=2 boss=0 slack=0.79",
    ),
    "deckbuilder": (
        "deckbuilder draw mana exhaust relic synergy",
        "plan tensor turn energy curve boss act",
        "shop relic floor climb",
    ),
    "city_builder": (
        "city_builder logistics road zoning throughput grid",
        "plan tensor supply chain bottleneck happiness",
        "era feel spatial gestalt layout",
    ),
    "grand_strategy": (
        "grand_strategy diplomacy attrition supply front",
        "plan tensor map theatre economy tick",
        "era feel spatial gestalt layout",
    ),
}

GAME_ADJACENT_ASPECTS = {
    "netcode_rollback": (
        "rollback netcode determinism input delay state snapshot",
        "plan tensor tick prediction reconciliation",
    ),
    "procedural_generation": (
        "wave function collapse room graph seed biome lattice",
        "plan tensor constraint solver dungeon layout",
    ),
    "shader_pipeline": (
        "shader framegraph pbr lighting roughness shadow cascade",
        "plan tensor gpu drawcall batch occlusion",
    ),
    "physics_simulation": (
        "rigidbody ragdoll collision broadphase solver constraint",
        "plan tensor impulse velocity verlet tick",
    ),
    "ai_director_pacing": (
        "ai director stress peak relax horde pacing curve",
        "plan tensor ttk heat vent spawn budget",
    ),
    "spatial_audio": (
        "spatial audio occlusion reverb footstep threat cue",
        "plan tensor attenuation doppler mix bus",
    ),
    "economy_telemetry": (
        "economy sink faucet drop rate retention telemetry",
        "plan tensor loot bias progression curve",
    ),
}

CONSOLE_ROM_ASSET_ASPECTS = {
    "nes_rom": (
        "nes rom 2bpp planar chr tile 16 bytes oam 64 sprites scanline 8",
        "plan tensor ines header prg chr bank switch pulse triangle noise dpcm",
        "palette 4 color subpalette attribute table 256x240 pixel snap",
    ),
    "gb_dmg_rom": (
        "game boy dmg rom 2bpp tile 16 bytes 96 bytes six tiles bank0 00:0200",
        "plan tensor header checksum 0x0134 0x014d oam 40 sprites 10 scanline",
        "monochrome 4 shade ramp 160x144 square wave noise apu vram 8kb",
    ),
    "gbc_rom": (
        "game boy color cgb rom dual vram bank 15bit rgb555 56 colors hdma",
        "plan tensor bg attribute flip priority bank0 2bpp tile 16 bytes",
        "palette swatch hblank dma transfer 160x144 cartridge checksum",
    ),
    "sms_rom": (
        "sega master system sms rom 4bpp bitplane interleaved 32 bytes tile",
        "plan tensor tmr sega header 0x7ff0 vdp 64 sprites sn76489 ym2413 fm",
    ),
    "snes_rom": (
        "snes sfc lorom hirom 4bpp 8bpp planar tile 32 bytes mode7 affine matrix",
        "plan tensor vram 64kb 128 oam sprites bgr555 256 color palette",
        "spc700 8 channel brr adpcm 16 sample loop block dma vblank budget",
    ),
    "genesis_rom": (
        "sega genesis megadrive md rom 68000 vector header 4bpp linear nybble tile",
        "plan tensor cram 64 colors 80 sprites 320x224 hscroll vscroll plane",
        "ym2612 6 channel fm synth sn76489 psg z80 pcm sample bank",
    ),
    "gba_rom": (
        "game boy advance gba rom arm7tdmi 0x08000000 4bpp 8bpp linear obj bg tile",
        "plan tensor vram 96kb 128 affine sprites 240x160 directsound dma fifo",
    ),
    "ps1_iso": (
        "ps1 psx cdrom xa 2048 sector 4bit 8bit clut tim texture 1mb vram",
        "plan tensor gte fixed point vertex snap affine uv subdivision 3000 poly",
        "spu 24 channel vag adpcm 28 sample block streaming seek table",
    ),
    "n64_z64": (
        "n64 z64 big endian rom 4kb tmem 4096 byte micro texture ci4 ci8 rgba16",
        "plan tensor rsp rdp display list 64 byte dma alignment cic crc",
        "vadpcm audio microcode 3000 poly vertex cache 320x240",
    ),
    "saturn_iso": (
        "sega saturn iso vdp1 deformed quad sprite vdp2 dual scroll plane",
        "plan tensor sh2 dual cpu scsp 32 channel pcm fm 2048 byte sector",
    ),
    "ps2_iso": (
        "ps2 dvd iso vu1 gif dma packet strip 4mb gs edram swizzled texture",
        "plan tensor 10000 poly psmct32 psmt8 spu2 48 channel adpcm",
    ),
    "gamecube_gcm": (
        "gamecube gcm boot.bin main.dol gx 4x4 tiled cmpr s3tc texture tev stage",
        "plan tensor 32 byte cache line dma alignment dsp 64 channel adpcm",
    ),
    "dreamcast_gdi": (
        "dreamcast gdi powervr2 clx2 morton twiddled vq codebook argb1555 rgb565",
        "plan tensor sh4 store queue tile accelerator aica 64 channel adpcm",
    ),
    "modern_console_pkg": (
        "modern console pkg bc1 bc7 block compressed pbr normal roughness mipmap",
        "plan tensor scale ladder divisor halving 65536 no full bitmap allocation",
        "meshlet lod gpu drawcall batch spatial 3d audio bus",
    ),
}


def console_rom_asset_corpus(consoles=None) -> List[str]:
    """Curated console and ROM asset engineering corpus across 8-bit to modern targets."""
    keys = [str(c).lower() for c in consoles] if consoles else list(CONSOLE_ROM_ASSET_ASPECTS.keys())
    out: List[str] = []
    for k in keys:
        rows = CONSOLE_ROM_ASSET_ASPECTS.get(k)
        if rows is None:
            for cand_k, cand_rows in CONSOLE_ROM_ASSET_ASPECTS.items():
                if k in cand_k:
                    rows = cand_rows
                    break
        if rows:
            out.extend(rows)
    seen = set()
    dedup: List[str] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            dedup.append(item)
    return dedup


def train_console_rom_assets(
    neo,
    *,
    consoles=None,
    rounds: int = 2,
) -> Dict[str, Any]:
    """Train cortex mouths, slot tracts, OwnSystem, and MoE heads on console & ROM asset creation."""
    from skeleton.cortex.curriculum import CORE_PAIRS
    from skeleton.cortex.distill import Ability
    from skeleton.cortex.laws import check
    from skeleton.cortex.port import fingerprint, tokens
    from skeleton.forge.hardware import CONSOLE_ROM_PROFILES, get_console_rom_profile

    rounds = _bounded_rounds(rounds)
    if consoles:
        resolved_keys = []
        for c in consoles:
            prof = get_console_rom_profile(str(c))
            if prof["key"] not in resolved_keys:
                resolved_keys.append(prof["key"])
    else:
        resolved_keys = list(CONSOLE_ROM_PROFILES.keys())

    corpus = console_rom_asset_corpus(resolved_keys)
    holdout_texts = [a for a, _ in list(CORE_PAIRS)]
    train_texts = holdout_texts[:4] + corpus

    xf = getattr(neo, "transformer", None)
    rms = getattr(neo, "neo_rms", None)
    backup = getattr(neo, "backup_transformer", None)
    before_steps = int(getattr(xf, "steps", 0) or 0)

    if xf is not None and hasattr(xf, "specialized_calibrate"):
        xf.specialized_calibrate(train_texts, epochs=rounds, lr=0.04, weight_decay=1e-4, holdout=holdout_texts)
    elif xf is not None and hasattr(xf, "fit"):
        for _ in range(rounds):
            xf.fit(train_texts, lr=0.04, schedule="cosine")

    if rms is not None and hasattr(rms, "specialized_calibrate"):
        rms.specialized_calibrate(train_texts, epochs=max(1, rounds // 2), lr=0.035, weight_decay=1e-4, holdout=holdout_texts)
    elif rms is not None and hasattr(rms, "fit"):
        rms.fit(train_texts, lr=0.035, schedule="cosine")

    if backup is not None and hasattr(backup, "specialized_calibrate"):
        backup.specialized_calibrate(train_texts, epochs=1, lr=0.03, weight_decay=1e-4, holdout=holdout_texts)

    for slot, port in (getattr(neo, "slots", {}) or {}).items():
        if port is not None and hasattr(port, "fit"):
            for text in corpus[:8]:
                port.fit(text)

    own = getattr(neo, "own", None)
    moe = getattr(neo, "moe", None)
    ingested_exemplars = 0
    moe_updates = 0

    for key in resolved_keys:
        prof = CONSOLE_ROM_PROFILES[key]
        gen = str(prof["generation"])
        bpp = int(prof["tile_bpp"])
        bpt = int(prof["bytes_per_8x8_tile"])
        sprites = int(prof["max_sprites_total"])
        colors = int(prof["colors_on_screen"])
        exemplar_text = (
            f"ROM[{key}] gen={gen} bpp={bpp} tile_bytes={bpt} "
            f"oam={sprites} colors={colors} ext={prof['rom_extension']}"
        )
        stim = f"{key} {prof['console']} {gen} rom asset tile sprite palette"
        if own is not None:
            ab = Ability(
                slot="right",
                stimulus_fp=fingerprint(stim),
                signature=f"rom:{key}:{gen}:{bpp}bpp",
                kind="rom-asset",
                text=exemplar_text,
                tags=("right", "rom", "console", "asset", key, gen, "acquired", "observed"),
                numbers=(float(bpp), float(bpt), float(sprites), 0.88),
                confidence=0.92,
                seen=rounds,
                tokens=tokens(stim + " " + " ".join(CONSOLE_ROM_ASSET_ASPECTS.get(key, ()))),
            )
            own.ingest(ab, stim)
            ingested_exemplars += 1

        if moe is not None and hasattr(neo, "_stream"):
            h = neo._stream(stim)
            mix_target = (2.0, 0.0, 0.0) if gen in {"8bit", "16bit"} else (4.0, 1.0, 0.0)
            bias_target = "combat" if gen in {"8bit", "16bit"} else "balanced"
            pacing_target = (0.35, 0.92, 0.84, 0.75) if gen in {"8bit", "16bit"} else (0.55, 0.85, 0.82, 0.78)
            if "left" in moe.experts:
                moe.experts["left"].head.step(h, mix_target, lr=0.12)
                if getattr(moe.experts["left"], "aux", None) is not None:
                    moe.experts["left"].aux.step(h, pacing_target, lr=0.10)
            if "right" in moe.experts:
                moe.experts["right"].head.step(h, bias_target, lr=0.12)
            moe_updates += 1

    if hasattr(neo, "sync_backup_transformer"):
        neo.sync_backup_transformer()

    after_steps = int(getattr(xf, "steps", 0) or 0)
    return check({
        "kind": "console-rom-asset-training",
        "trained": 1,
        "consoles_trained": resolved_keys,
        "console_count": len(resolved_keys),
        "corpus_size": len(corpus),
        "ingested_exemplars": ingested_exemplars,
        "moe_updates": moe_updates,
        "neo_steps_delta": after_steps - before_steps,
        "stored_prose": 0,
        "law": "ok",
    })


def gaming_and_adjacent_corpus() -> List[str]:
    """Curated gaming, game-adjacent, and console/ROM asset dialect corpus for beneficial weight priors."""
    out: List[str] = []
    for rows in ASPECTS.values():
        out.extend(rows)
    for rows in GAME_ADJACENT_ASPECTS.values():
        out.extend(rows)
    for rows in CONSOLE_ROM_ASSET_ASPECTS.values():
        out.extend(rows)
    seen = set()
    dedup: List[str] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            dedup.append(item)
    return dedup


def apply_gaming_priors(neo, *, rounds: int = 2) -> Dict[str, Any]:
    """Find and apply beneficial gaming & game-adjacent weights across cortex & MoE."""
    from skeleton.cortex.curriculum import CORE_PAIRS, WALK_PAIRS

    rounds = max(1, min(16, int(rounds)))
    corpus = gaming_and_adjacent_corpus()
    core_texts = [a for a, _ in CORE_PAIRS] + [a for a, _ in WALK_PAIRS]
    focus_texts = core_texts + corpus[:12]

    xf = getattr(neo, "transformer", None)
    rms = getattr(neo, "neo_rms", None)
    before_steps = int(getattr(xf, "steps", 0) or 0)

    if xf is not None and hasattr(xf, "specialized_calibrate"):
        xf.specialized_calibrate(
            focus_texts,
            epochs=rounds,
            lr=0.04,
            weight_decay=1e-4,
            holdout=core_texts,
        )
    elif xf is not None and hasattr(xf, "fit"):
        for _ in range(rounds):
            xf.fit(focus_texts, lr=0.04, schedule="cosine")

    if rms is not None and hasattr(rms, "specialized_calibrate"):
        rms.specialized_calibrate(
            focus_texts,
            epochs=max(1, rounds // 2),
            lr=0.035,
            weight_decay=1e-4,
            holdout=core_texts,
        )
    elif rms is not None and hasattr(rms, "fit"):
        rms.fit(focus_texts, lr=0.035, schedule="cosine")

    for slot, port in (getattr(neo, "slots", {}) or {}).items():
        if port is not None and hasattr(port, "fit"):
            for text in core_texts[:6]:
                port.fit(text)

    moe = getattr(neo, "moe", None)
    moe_updates = 0
    if moe is not None and hasattr(neo, "_stream"):
        gaming_mix_priors = [
            (
                "HP = DPS x TTK ; observed mix trash=6 elite=2 boss=0 slack=0.70 soulslike",
                (6.0, 2.0, 0.0),
                "heat",
                (0.75, 0.65, 0.85, 0.80),
            ),
            (
                "HP = DPS x TTK ; observed mix trash=4 elite=1 boss=0 slack=0.80 extraction now",
                (4.0, 1.0, 0.0),
                "loot",
                (0.55, 0.78, 0.82, 0.72),
            ),
            (
                "HP = DPS x TTK ; observed mix trash=2 elite=0 boss=0 slack=0.88 arcade golden age",
                (2.0, 0.0, 0.0),
                "combat",
                (0.25, 0.90, 0.78, 0.60),
            ),
            ("soulslike extraction ttk elite dread", (6.0, 2.0, 0.0), "heat", (0.75, 0.65, 0.85, 0.80)),
            ("cozy wholesome intimacy grind farm", (1.0, 0.0, 0.0), "balanced", (0.90, 0.95, 0.88, 0.90)),
            ("boomer shooter movement gun poetry ttk", (6.0, 1.0, 0.0), "combat", (0.30, 0.82, 0.80, 0.65)),
            ("horror survival dread heat scarcity", (3.0, 2.0, 0.0), "heat", (0.80, 0.60, 0.86, 0.85)),
        ]
        for _ in range(max(4, rounds * 4)):
            for stim, mix_target, bias_target, pacing_target in gaming_mix_priors:
                h = neo._stream(stim)
                if "left" in moe.experts:
                    moe.experts["left"].head.step(h, mix_target, lr=0.14)
                    if getattr(moe.experts["left"], "aux", None) is not None:
                        moe.experts["left"].aux.step(h, pacing_target, lr=0.12)
                if "right" in moe.experts:
                    moe.experts["right"].head.step(h, bias_target, lr=0.10)
                if "midbrain" in moe.experts:
                    moe.experts["midbrain"].head.step(h, (0.65, 0.55, 0.55), lr=0.08)
                if "pfc" in moe.experts:
                    moe.experts["pfc"].head.step(h, 0.0, lr=0.08)
                    if getattr(moe.experts["pfc"], "aux", None) is not None:
                        moe.experts["pfc"].aux.step(h, (1.0, 1.0 if bias_target in {"heat", "loot"} else 0.0), lr=0.10)
                moe_updates += 1

    after_steps = int(getattr(xf, "steps", 0) or 0)
    return {
        "applied": 1,
        "gaming_domains": len(ASPECTS),
        "adjacent_domains": len(GAME_ADJACENT_ASPECTS),
        "corpus_size": len(corpus),
        "neo_steps_delta": after_steps - before_steps,
        "moe_updates": moe_updates,
    }


def _bounded_rounds(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError("rounds must be an integer")
    try:
        rounds = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("rounds must be an integer") from exc
    rounds = max(1, rounds)
    if rounds > MAX_IMPROVE_ROUNDS:
        raise ValueError(f"rounds exceeds safety budget ({MAX_IMPROVE_ROUNDS})")
    return rounds


def _aspects(era: str, title: str) -> List[str]:
    pack = list(ASPECTS.get(era, ASPECTS["soulslike"]))
    pack.append(distill_dialect(title, era))
    return pack


def improve(neo, stimulus: str, *, rounds: int = 16) -> Dict[str, Any]:
    if not isinstance(stimulus, str):
        raise ValueError("stimulus must be a string")
    if len(stimulus) > MAX_IMPROVE_STIMULUS_CHARS:
        raise ValueError(f"stimulus exceeds safety budget ({MAX_IMPROVE_STIMULUS_CHARS} chars)")
    rounds = _bounded_rounds(rounds)

    stim = stimulus or ""
    ref = lookup(stim)
    if ref is None:
        parts = stim.split(None, 1)
        if len(parts) == 2 and parts[0].casefold() == "like":
            ref = lookup(parts[1].strip())
    if ref is None:
        return {"improved": 0, "reason": "no-reference", "law": "cite-do-not-copy"}

    era = str(ref.get("era") or "soulslike")
    title = str(ref.get("title") or "")
    texts = _aspects(era, title)
    for t in texts:
        try:
            guard(t, title)
        except LawError as exc:
            return {"improved": 0, "reason": "law-violation", "law": exc.law}

    check({"kind": "improve", "dialect": texts[0], "title": title, "era": era})

    xf = getattr(neo, "transformer", None)
    rms = getattr(neo, "neo_rms", None)
    before = {
        "G": float(getattr(getattr(neo, "genos_engine", None), "G", 1.0) or 1.0),
        "neo_steps": int(getattr(xf, "steps", 0) or 0),
        "rms_steps": int(getattr(rms, "steps", 0) or 0),
    }
    if xf is not None:
        for _ in range(max(4, rounds)):
            xf.fit(texts, lr=0.05, schedule="cosine")
    if rms is not None:
        for _ in range(max(2, rounds // 2)):
            rms.fit(texts, lr=0.05, schedule="cosine")
    for slot, port in (getattr(neo, "slots", {}) or {}).items():
        xf_s = getattr(port, "transformer", None)
        if xf_s is not None and hasattr(xf_s, "fit"):
            xf_s.fit(texts[:2], lr=0.04, schedule="cosine")

    pulses = []
    if hasattr(neo, "genos"):
        for _ in range(8):
            pulses.append(neo.genos(" ".join(texts)[:180]))

    record_provenance({**ref, "dialect": texts[-1]}, action="improve")
    after_g = float(getattr(getattr(neo, "genos_engine", None), "G", before["G"]) or before["G"])
    ratio = after_g / max(before["G"], 1e-9)
    card = check({
        "kind": "improve",
        "improved": 1,
        "title": title,
        "era": era,
        "url": ref.get("url"),
        "citation": ref.get("citation"),
        "stored_prose": 0,
        "law": "ok",
        "rounds": rounds,
        "G0": round(before["G"], 6),
        "G": round(after_g, 6),
        "ratio": round(ratio, 4),
        "target": 10.0,
        "neo_steps": int(getattr(xf, "steps", 0) or 0) - before["neo_steps"],
        "rms_steps": int(getattr(rms, "steps", 0) or 0) - before["rms_steps"],
        "epsilon": float(getattr(getattr(neo, "genos_engine", None), "epsilon", 0) or 0),
        "dialect": texts[-1],
    })
    return card
