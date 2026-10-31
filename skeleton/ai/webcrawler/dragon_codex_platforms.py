"""Hardware-aware original world codex projection for every Dragon target.

This is a *content compiler* to a portable, bounded game-specification and
world mechanic slice, not an executable ROM compiler. The existing native
target registry is authoritative for CPU, dimensions, colors and toolchain
availability; no proprietary SDK, title, ROM, BIOS or asset import is used.

Representability is separate from release readiness. A 1977 cartridge can
host a tiny deterministic multi-era codex slice using authored time steps;
a modern desktop can page larger world chunks. No unsupported console
receives an imaginary verified executable.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass
from hashlib import sha256
import json

from .dragon_native_targets import CATALOG
from .dragon_world_codex import (
    CodexAddress,DOMAIN_AXIS,DOMAINS,EXTENSION_DOMAIN_AXIS,ALL_DOMAINS,validate,
)
from .dragon_world_codex_runtime import (
    SCHEMA as GAME_SCHEMA,gate_catalog,start,witness_to_gate,
)
from .dragon_living_world import _sha

SCHEMA="skeleton.ai.dragon.codex_platform_projection.v1"
# Conservative design-facing working budgets; NOT claimed measured RAM/ROM
# capacities of devices. Calibration uses actual catalog metadata and
# explicit cohort budgets, never fictional physical memory measurements.
COHORTS={
 "scanline_retro":(4,4,4,8,1,"single_screen_slice"),
 "tile_8_bit":(6,4,8,12,2,"banked_2d_levels"),
 "home_8_bit":(6,4,8,12,2,"disk_or_tape_scene_stream"),
 "tile_16_bit":(8,6,16,24,3,"banked_multi_scene_game"),
 "early_3d":(8,8,32,32,4,"bounded_sector_stream"),
 "handheld_3d":(8,7,32,32,4,"batched_handheld_sector"),
 "sixth_gen":(10,8,64,48,5,"sector_and_hub_stream"),
 "seventh_gen":(10,10,96,64,6,"hub_stream"),
 "modern_console":(12,12,128,96,8,"procedural_chunk_stream"),
 "desktop":(16,12,128,128,12,"continuous_chunk_stream"),
 "browser_mobile":(12,10,96,64,6,"demand_paged_world"),
 "experimental":(6,5,12,12,2,"constrained_adapter_review"),
}
# 1st: domains simultaneously loaded, 2nd: axis controls per domain,
# 3rd: represented level steps, 4th: content rooms per streamed chunk,
# 5th: route gates simultaneously active. Truncation is explicit.

SCANLINE={"atari_2600","intellivision","colecovision"}
TILE8={"nes","master_system","game_boy","game_boy_color",
       "game_gear","lynx","turbografx_16"}
HOME8={"commodore_64","zx_spectrum","apple_ii","dos_8086"}
TILE16={"genesis","snes","neo_geo","amiga_500","atari_st","dos_vga"}
EARLY3={"ps1","saturn","nintendo_64","dreamcast"}
HANDHELD={"game_boy_advance","nintendo_ds","psp","nintendo_3ds","ps_vita"}
SIXTH={"gamecube","ps2","xbox_original","wii"}
SEVENTH={"ps3","xbox_360","wii_u","switch"}
DESKTOP={"pc_linux","pc_windows","pc_macos","steam_deck","windows_95",
         "windows_xp"}
BROWSER={"web","web_browser","android","ios"}
MODERN={"ps4","ps5","xbox_one","xbox_series","switch_2"}

def cohort(target_id:str)->str:
    if target_id in SCANLINE:return "scanline_retro"
    if target_id in TILE8:return "tile_8_bit"
    if target_id in HOME8:return "home_8_bit"
    if target_id in TILE16:return "tile_16_bit"
    if target_id in EARLY3:return "early_3d"
    if target_id in HANDHELD:return "handheld_3d"
    if target_id in SIXTH:return "sixth_gen"
    if target_id in SEVENTH:return "seventh_gen"
    if target_id in DESKTOP:return "desktop"
    if target_id in BROWSER:return "browser_mobile"
    if target_id in MODERN:return "modern_console"
    return "experimental"


@dataclass(frozen=True)
class PlatformCodexPlan:
    schema:str
    target_id:str
    original_world_digest:str
    original_decimal_world_index:str
    cohort:str
    native_catalog_status:str
    toolchain:str
    output_format:str
    machine_width:int
    machine_height:int
    catalog_max_colors:int
    chosen_domain_names:tuple[str,...]
    chosen_axes:tuple[str,...]
    quantized_levels:tuple[int,...]
    source_levels:tuple[int,...]
    original_axis_count:int
    active_axes:int
    deferred_axes:tuple[str,...]
    source_route_gates:tuple[str,...]
    active_route_gates:tuple[str,...]
    deferred_route_gates:tuple[str,...]
    level_buckets:int
    rooms_per_chunk:int
    chunk_strategy:str
    generated_world_chunks:int
    final_platform_source_emitted:bool
    hardware_binary_compiled:bool
    real_hardware_playtested:bool
    design_digest:str
    scope:str


def _target(id:str):
    if type(id) is not str or id not in CATALOG:
        raise ValueError("unknown or unavailable Dragon native target")
    return CATALOG[id]


def _domain_sort(address:CodexAddress)->list[str]:
    # Deterministically select domains most expressive *for this source*.
    # Ties use canonical order, not nondeterministic hash iteration.
    extended=any(address.extension_values)
    levels=address.values+(address.extension_values if extended else ())
    scored=[]
    for n,domain in enumerate(ALL_DOMAINS if extended else DOMAINS):
        intensity=max(levels[n*8:n*8+8])
        diversity=len(set(levels[n*8:n*8+8]))
        scored.append((-intensity,-diversity,n,domain))
    return [row[-1] for row in sorted(scored)]


def compile_content(address:CodexAddress,target_id:str,
                    *,chunks:int=1)->PlatformCodexPlan:
    parent,genome=validate(address)
    target=_target(target_id)
    if type(chunks) is not int or not 1<=chunks<=64:
        raise ValueError("original world adapter supports only 1..64 bounded chunks")
    group=cohort(target_id)
    max_domains,axes_per_domain,levels,rooms,gates,strategy=COHORTS[group]
    extended=any(address.extension_values)
    domain_axes={**DOMAIN_AXIS,**EXTENSION_DOMAIN_AXIS} if extended else DOMAIN_AXIS
    domains=ALL_DOMAINS if extended else DOMAINS
    active_domains=_domain_sort(address)[:max_domains]
    axis_names=[]
    original_levels=[]
    for domain in active_domains:
        selected=sorted(domain_axes[domain],
                        key=lambda axis:(-genome.level(axis),axis))[:axes_per_domain]
        for axis in selected:
            axis_names.append(axis)
            original_levels.append(genome.level(axis))
    # Preserve relative level strength under target quantization, without
    # inventing impossible 256-step hardware abilities.
    quantized=tuple(
        min(levels-1,(level*levels)//256)
        for level in original_levels
    )
    # Wire real runtime gates for both versions; no phantom travel_* names.
    from .dragon_world_codex_runtime import GATE_MODES,ALL_GATE_MODES
    modes=ALL_GATE_MODES if extended else GATE_MODES
    real_routes=tuple(modes[domains.index(domain)] for domain in active_domains[:gates])
    all_routes=tuple(modes)
    missing=tuple(
        axis for domain in domains for axis in domain_axes[domain]
        if axis not in axis_names
    )
    content={
        "schema":SCHEMA,"source":address.codex_digest,"target":target_id,
        "cohort":group,"hardware":[target.max_width,target.max_height,
                                   target.max_colors],
        "domains":active_domains,"axes":axis_names,"levels":quantized,
        "routes":real_routes,"chunks":chunks,"rooms":rooms,
        "strategy":strategy,
    }
    return PlatformCodexPlan(
        schema=SCHEMA,target_id=target.id,
        original_world_digest=address.codex_digest,
        original_decimal_world_index=address.decimal_index,
        cohort=group,native_catalog_status=target.status,
        toolchain=target.toolchain,output_format=target.output,
        machine_width=target.max_width,machine_height=target.max_height,
        catalog_max_colors=target.max_colors,
        chosen_domain_names=tuple(active_domains),
        chosen_axes=tuple(axis_names),
        quantized_levels=quantized,
        source_levels=tuple(original_levels),
        original_axis_count=len(genome.values)+(len(genome.extension_values) if extended else 0),
        active_axes=len(axis_names),
        deferred_axes=missing,
        source_route_gates=all_routes,
        active_route_gates=real_routes,
        deferred_route_gates=tuple(k for k in all_routes if k not in real_routes),
        level_buckets=levels,rooms_per_chunk=rooms,
        chunk_strategy=strategy,generated_world_chunks=chunks,
        final_platform_source_emitted=False,
        hardware_binary_compiled=False,
        real_hardware_playtested=False,
        design_digest=_sha(content),
        scope="hardware-catalog-based bounded original *content projection*, "
              "not compiled executable, device test or SDK license",
    )


def content_pack(address:CodexAddress,target_id:str, *,
                 chunks:int=1)->dict:
    plan=compile_content(address,target_id,chunks=chunks)
    # Each chunk is genuinely different original compact authored data:
    # use deterministic room IDs, local elevation and biome variation.
    # Platform-native toolchains remain a later independently validated gate.
    source=[]
    for chunk in range(chunks):
        rooms=[]
        for index in range(plan.rooms_per_chunk):
            digest=_sha([plan.design_digest,"room",chunk,index])
            rules=tuple(
                (axis,plan.quantized_levels[n])
                for n,axis in enumerate(plan.chosen_axes)
                if (int(digest[n%16],16)+n+index)%7==0
            )[:8]
            # Sky-island geometry and routes are authored parameters, not
            # merely a label placed on the old ground-world projection.
            aerial="aerial_realms" in plan.chosen_domain_names
            sky_level=(address.extension_values[0] if aerial else 0)
            island=(aerial and int(digest[4:6],16)<sky_level)
            rooms.append({
                "sky_island":island,
                "altitude_layer":(
                    1+int(digest[6:8],16)//32 if island else 0
                ),
                "room":chunk*plan.rooms_per_chunk+index,
                "original_local_seed":digest[:16],
                "biome_class":int(digest[:2],16)%12,
                "elevation_band":int(digest[2:4],16)%plan.level_buckets,
                "active_features":rules,
                "entrances":(
                    "previous","next","explore" if index%3==0 else "return",
                    * (("skybridge","glide") if island else ()),
                ),
            })
        source.append({
            "chunk":chunk,"rooms":rooms,
            "load_order":chunk,"identity":_sha([
                plan.design_digest,chunk,rooms,
            ]),
        })
    receipt={
        "schema":SCHEMA,"target":target_id,
        "source_address":address.decimal_index,
        "source_codex_digest":address.codex_digest,
        "projection":asdict(plan),
        "chunks":source,
        "provenance":"original generated data, no third-party assets",
        "ready_for_hardware_build":False,
        "native_binary":None,
    }
    receipt["content_sha256"]=_sha(receipt)
    return receipt


def verify_content_pack(address:CodexAddress,pack:dict)->dict:
    if (not isinstance(pack,dict) or pack.get("schema")!=SCHEMA or
            "projection" not in pack):
        raise ValueError("original platform projection receipt missing")
    target=pack["target"]
    chunks=pack["projection"]["generated_world_chunks"]
    fresh=content_pack(address,target,chunks=chunks)
    if fresh!=pack:
        raise ValueError("platform world content was changed or not regenerated")
    return {
        "verified":True,"target":target,"room_count":sum(
            len(chunk["rooms"]) for chunk in pack["chunks"]),
        "hardware_binary_verified":False,
        "projected_original_axes":len(fresh["projection"]["chosen_axes"]),
        "deferred_axes":len(fresh["projection"]["deferred_axes"]),
        "source_sha256":fresh["content_sha256"],
    }


def target_preview(address:CodexAddress, *,limit:int=60)->dict:
    if type(limit) is not int or not 1<=limit<=60:
        raise ValueError("unsupported platform projection index limit")
    keys=sorted(CATALOG)[:limit]
    return {
        "schema":SCHEMA,"available_catalog_targets":len(CATALOG),
        "sampled":len(keys),
        "platforms":[{
            "target":key,"cohort":cohort(key),
            "status":CATALOG[key].status,
            "capability":compile_content(address,key).__dict__,
        } for key in keys],
        "unverified_executable_count":0,
        "claim":"platform-aware original content compilation only, not "
                "hardware execution certification",
    }
