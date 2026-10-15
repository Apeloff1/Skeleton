"""Console-aware below-screen controller panels for the 169-target study catalog.

Libretro RetroPad masks are the execution ABI, while physical legends are only
display labels. Specific layouts cover documented major families; all remaining
canonical targets get a *visibly generic* RetroPad panel, never invented
physical-hardware fidelity. Real inputs require the separate native host.
"""
from __future__ import annotations

from typing import Any

from .game_comparison_schema import digest
from .game_emulator_catalog import canonical_targets
from .game_emulator_host import _ACTIONS, _KEY_ACTIONS, _controller_ports

SCHEMA = "skeleton.game.comparison_controller_layout.v1"

# Hardware legend only; numerical buttons retain exact RetroPad bitmasks.
# Position is percentage of a 100x56 controller deck, always BELOW screen.
_PROFILE = {
    "nes": ("NES-style", ("b", "a"), ("select","start")),
    "snes": ("SNES-style", ("b","a","y","x","l","r"), ("select","start")),
    "genesis": ("Mega Drive-style", ("b","a","y","x","l","r"), ("start",)),
    "master_system": ("Master System-style", ("b","a"), ("start",)),
    "game_gear": ("Game Gear-style", ("b","a"), ("start",)),
    "game_boy": ("Game Boy-style", ("b","a"), ("select","start")),
    "game_boy_color": ("Game Boy Color-style", ("b","a"), ("select","start")),
    "game_boy_advance": ("Game Boy Advance-style", ("b","a","l","r"), ("select","start")),
    "nintendo_64": ("N64 RetroPad approximation", ("b","a","y","x","l","r","l2","r2"), ("start",)),
    "ps1": ("PlayStation-style", ("b","a","y","x","l","r","l2","r2"), ("select","start")),
    "ps2": ("PlayStation-style", ("b","a","y","x","l","r","l2","r2"), ("select","start")),
    "psp": ("PSP-style", ("b","a","y","x","l","r"), ("select","start")),
    "gamecube": ("GameCube RetroPad approximation", ("b","a","y","x","l","r","l2","r2"), ("start",)),
    "wii": ("Wii RetroPad approximation", ("b","a","x","y","l","r"), ("start",)),
    "dreamcast": ("Dreamcast-style", ("b","a","y","x","l","r"), ("start",)),
    "saturn": ("Saturn-style", ("b","a","y","x","l","r"), ("start",)),
    "nintendo_ds": ("Nintendo DS-style", ("b","a","y","x","l","r"), ("select","start")),
    "nintendo_dsi": ("Nintendo DSi-style", ("b","a","y","x","l","r"), ("select","start")),
    "nintendo_3ds": ("3DS RetroPad approximation", ("b","a","y","x","l","r"), ("select","start")),
    "atari_2600": ("Atari 2600 joystick-style", ("b",), ("select","start")),
    "atari_7800": ("Atari 7800 joystick-style", ("b","a"), ("select","start")),
    "atari_5200": ("Atari 5200 joystick approximation", ("b","a"), ("start",)),
    "lynx": ("Atari Lynx-style", ("b","a"), ("start",)),
    "turbografx_16": ("PC Engine-style", ("b","a"), ("select","start")),
    "neo_geo": ("Neo Geo-style", ("b","a","y","x"), ("select","start")),
    "wonderswan": ("WonderSwan RetroPad approximation", ("b","a","y","x"), ("start",)),
}
_ALIASES = {
    "famicom_disk_system":"nes", "game_boy_pocket":"game_boy", "game_boy_light":"game_boy",
    "game_boy_micro":"game_boy_advance", "game_boy_player":"game_boy_advance",
    "sega_mark_iii":"master_system", "sega_cd":"genesis", "sega_32x":"genesis",
    "psp_go":"psp", "psp_street":"psp",
    "nintendo_2ds":"nintendo_3ds", "new_nintendo_3ds":"nintendo_3ds",
    "pc_engine_cd":"turbografx_16","neo_geo_cd":"neo_geo",
}
_FACE_POS = ((78,31),(88,23),(68,23),(78,15),(68,6),(88,6),(57,6),(98,6))
_DPAD = (("up",18,17),("left",9,28),("down",18,39),("right",27,28))


def controller_layout_for_target(
    target_id: str,
    controller_devices: object = None,
    *,
    core_input_descriptors: object = None,
) -> dict[str, Any]:
    targets = canonical_targets()
    if target_id not in targets:
        raise ValueError("Controller layout requires a canonical hardware identity")
    devices = _controller_ports(controller_devices)
    key = _ALIASES.get(target_id,target_id)
    profile = _PROFILE.get(key)
    if profile is None:
        profile = ("Generic Libretro RetroPad", ("b","a","y","x","l","r","l2","r2"), ("select","start"))
    exact = key in _PROFILE and "approximation" not in profile[0].lower()
    buttons = []
    for action,x,y in _DPAD:
        buttons.append({
            "id":action,"legend":action.upper(),
            "x":x,"y":y,"mask":_ACTIONS[action],
            "device":"joypad","input_kind":"bitmask",
        })
    for index, action in enumerate(profile[1]):
        x,y = _FACE_POS[index]
        buttons.append({
            "id":action,"legend":action.upper(),"x":x,"y":y,
            "mask":_ACTIONS[action],"device":"joypad","input_kind":"bitmask",
        })
    for index,action in enumerate(profile[2]):
        buttons.append({
            "id":action,"legend":action.upper(),
            "x":42+index*13,"y":43,"mask":_ACTIONS[action],
            "device":"joypad","input_kind":"bitmask",
        })
    by_port: dict[int, dict[int, str]] = {}
    if core_input_descriptors is not None:
        if not isinstance(core_input_descriptors,list) or len(core_input_descriptors)>128:
            raise ValueError("Core input descriptions exceed the bounded ABI reporting contract")
        for entry in core_input_descriptors:
            if not isinstance(entry,dict) or set(entry)!={"port","device","index","id","description"}:
                raise ValueError("Core input metadata requires exact libretro descriptor shape")
            port,dev,idx,bit=(
                entry["port"],entry["device"],entry["index"],entry["id"]
            )
            name=entry["description"]
            if (type(port) is not int or not 0<=port<4
                or type(dev) is not int or dev not in (1,2,3,5,6)
                or type(idx) is not int or not 0<=idx<=3
                or type(bit) is not int or not 0<=bit<=511
                or type(name) is not str or not 1<=len(name)<=95
                or any(ord(ch)<32 for ch in name)):
                raise ValueError("Actual native core input label is malformed or out of range")
            if dev==1 and idx==0 and bit<=15:
                controls=by_port.setdefault(port,{})
                if bit in controls:
                    raise ValueError("Actual core reported duplicate RetroPad labels")
                controls[bit]=name
    slots=[]
    core_labeled_count=0
    for port,device in enumerate(devices):
        slot={
            "port":port,
            "device":device,
            "live_core_peripheral_validated":False,
            "controls":[],
        }
        if device in ("joypad","analog"):
            labels=by_port.get(port,{})
            slot["controls"]=[]
            for control in buttons:
                copied=dict(control)
                idx=int(control["mask"]).bit_length()-1
                if idx in labels:
                    copied["legend"]=labels[idx]
                    copied["legend_source"]="actual_native_libretro_core_descriptor"
                    core_labeled_count+=1
                else:
                    copied["legend_source"]="generic_or_hardware_style_label"
                slot["controls"].append(copied)
            if device == "analog":
                slot["analog_axes"]=["left_x","left_y","right_x","right_y"]
        elif device == "keyboard":
            slot["controls"]=[
                {"id":name,"legend":name.removeprefix("key_").upper(),
                 "key_code":code,"input_kind":"keycode","device":"keyboard",
                 "x":8+(n%5)*19,"y":14+(n//5)*20}
                for n,(name,code) in enumerate(_KEY_ACTIONS.items())
            ]
        elif device == "mouse":
            slot["controls"]=[
                {"id":"mouse_left","legend":"Left click","device":"mouse","input_kind":"mouse_button","mouse_index":2,"x":35,"y":26},
                {"id":"mouse_right","legend":"Right click","device":"mouse","input_kind":"mouse_button","mouse_index":3,"x":68,"y":26},
            ]
            slot["coordinate_system"]="signed relative delta x/y, clamped to -32768..32767"
        elif device == "pointer":
            slot["controls"]=[
                {"id":"pointer_touch","legend":"Touch","device":"pointer","input_kind":"pointer_button","pointer_index":2,"x":50,"y":25}
            ]
            slot["coordinate_system"]="normalized libretro pointer x/y, not a physical touchscreen calibration"
        slots.append(slot)
    payload={
        "schema_version":SCHEMA,
        "target_id":target_id,
        "profile_name":profile[0],
        "physical_layout_certified":False,
        "core_reported_input_legend_count":core_labeled_count,
        "core_labels_independently_qualified":False,
        "physical_legend_profile":key if exact else None,
        "generic_fallback":not exact,
        "mapping_kind":"libretro_retropad_semantic_overlay_below_game_screen",
        "input_space":"native host supported bitmask/keycode/analog/mouse/pointer only",
        "ports":slots,
        "notes":"Labels reported by an actual installed libretro core are core declarations, not verified physical-controller fidelity. Panels are displayed below game video.",
    }
    payload["layout_sha256"]=digest(payload)
    return payload


def supported_controller_layout_catalog() -> dict[str, Any]:
    rows=[]
    for target_id in sorted(canonical_targets()):
        profile=controller_layout_for_target(target_id, ["joypad"])
        rows.append({
            "target_id":target_id,
            "profile_name":profile["profile_name"],
            "generic_fallback":profile["generic_fallback"],
            "layout_sha256":profile["layout_sha256"],
            "native_core_input_verified":False,
        })
    return {
        "schema_version":"skeleton.game.comparison_controller_catalog.v1",
        "targets":rows,
        "target_count":len(rows),
        "real_controller_compatibility_verified":0,
        "retro_input_device_coverage":["joypad","analog","keyboard","mouse","pointer","none"],
    }
