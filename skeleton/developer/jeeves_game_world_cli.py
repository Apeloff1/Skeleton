"""Strict workbench CLI transport for multidomain upscale; no alternative runtime."""
from __future__ import annotations

from pathlib import Path
from typing import Any

ACTIONS = (
    "upscale-world", "upscale-stage", "upscale-environment", "upscale-clutter",
    "upscale-foliage", "upscale-animation", "upscale-shadow", "upscale-parallax",
    "upscale-music", "asset-inventory", "upscale-review", "vividness-review",
    "queue-upscaled-training", "camera-plan",
)

COMMON = {"target","source","output","dry_run"}
REQUIRED = {
    "upscale-world": {"target","source","output"},
    "upscale-stage": {"target","source","output"},
    "upscale-environment": {"target","source","output"},
    "upscale-clutter": {"target","source","output"},
    "upscale-foliage": {"target","source","output"},
    "upscale-animation": {"target","source","output"},
    "upscale-shadow": {"target","source","output"},
    "upscale-parallax": {"target","source","output"},
    "upscale-music": {"target","source","output"},
    "asset-inventory": set(),
    "upscale-review": set(),
    "vividness-review": set(),
    "queue-upscaled-training": set(),
    "camera-plan": {"depth"},
}
ALLOWED = {
    "upscale-world":COMMON | {"richness","focus"},
    "upscale-stage":COMMON | {"richness","focus"},
    "upscale-environment":COMMON | {"richness"},
    "upscale-clutter":COMMON | {"richness"},
    "upscale-foliage":COMMON | {"pattern","frames","frame_height"},
    "upscale-animation":COMMON | {"pattern","frames","frame_height"},
    "upscale-shadow":COMMON | {"distance"},
    "upscale-parallax":COMMON | {"pan"},
    "upscale-music":COMMON | {"mode","ambience"},
    "asset-inventory":{"page","page_size"},
    "upscale-review":{"passes"},
    "vividness-review":{"passes","source"},
    "queue-upscaled-training":{"page","page_size"},
    "camera-plan":{"depth","yaw","pitch","parallax_planes"},
}
DEFAULTS = {
    "page":0,"page_size":64,"passes":3,"richness":3,"pattern":"wind",
    "frames":8,"mode":"remaster","distance":2,"pan":8,
    "yaw":0,"pitch":0,"parallax_planes":3,
}


def dispatch(args: Any, root: Path) -> dict[str,Any]:
    name=args.action
    if name not in ACTIONS:
        raise ValueError("unsupported upscale studio action")
    # Fail closed on irrelevant options, preventing hidden cross-domain flags.
    for key,value in vars(args).items():
        if key == "action":
            continue
        if key not in ALLOWED[name] and value is not None and value is not False:
            raise ValueError(f"--{key.replace('_','-')} is not valid for {name}")
    for key in REQUIRED[name]:
        if getattr(args,key,None) in (None,""):
            raise ValueError(f"{name} needs --{key.replace('_','-')}")
    def arg(key):
        value=getattr(args,key,None)
        return DEFAULTS.get(key) if value is None else value
    if name=="camera-plan":
        from skeleton.developer.game_cli import _load
        from skeleton.developer.jeeves_game_world_upscale import camera_profile
        _load(root)
        return camera_profile(args.depth,yaw=arg("yaw"),pitch=arg("pitch"),
                              parallax_planes=arg("parallax_planes"))
    if name=="asset-inventory":
        from skeleton.developer.jeeves_game_world_upscale import inventory
        return inventory(root,page=arg("page"),page_size=arg("page_size"))
    if name=="upscale-review":
        from skeleton.developer.jeeves_game_world_upscale import scrutiny
        return scrutiny(root,passes=arg("passes"))
    if name=="vividness-review":
        from skeleton.developer.jeeves_game_world_upscale import vividness
        if not args.source:
            raise ValueError("vividness-review requires --source design/enhanced-stage.json")
        return vividness(root,source=args.source,passes=arg("passes"))
    if name=="queue-upscaled-training":
        from skeleton.developer.jeeves_game_upscale_queue import training_queue
        return training_queue(root,page=arg("page"),page_size=arg("page_size"))
    if name in ("upscale-animation","upscale-foliage"):
        from skeleton.developer.jeeves_game_world_upscale import animate
        return animate(root,source=args.source,output=args.output,target=args.target,
                       pattern=arg("pattern"),frames=arg("frames"),
                       frame_height=args.frame_height,dry_run=args.dry_run)
    if name=="upscale-shadow":
        from skeleton.developer.jeeves_game_world_upscale import shadow
        return shadow(root,source=args.source,output=args.output,target=args.target,
                      distance=arg("distance"),dry_run=args.dry_run)
    if name=="upscale-parallax":
        from skeleton.developer.jeeves_game_world_upscale import parallax
        return parallax(root,source=args.source,output=args.output,target=args.target,
                        pan=arg("pan"),dry_run=args.dry_run)
    if name=="upscale-music":
        from skeleton.developer.jeeves_game_music_upscale import remaster
        return remaster(root,source=args.source,output=args.output,target=args.target,
                        mode=arg("mode"),ambience=args.ambience,dry_run=args.dry_run)
    from skeleton.developer.jeeves_game_world_upscale import stage
    focus={"upscale-environment":"environment","upscale-clutter":"clutter",
           "upscale-stage":"world"}.get(name,args.focus or "world")
    return stage(root,source=args.source,output=args.output,target=args.target,
                 richness=arg("richness"),focus=focus,dry_run=args.dry_run)
