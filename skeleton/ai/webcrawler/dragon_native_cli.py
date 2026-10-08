"""Local, offline creator for original retro/desktop practice games.

No server credentials, crawler memory promotion or XP; this is a tooling
demo that can be built with an installed platform toolchain.
Usage: python -m skeleton.ai.webcrawler.dragon_native_cli --target game_boy --out /tmp/dragon-gb
"""
from __future__ import annotations
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from .dragon_native_projects import render_native_project
from .dragon_native_targets import STYLES
from .dragon_game_mechanics import Mechanic

def emit_demo(target:str, output_dir:Path, *, title:str="Dragon Tiny Adventure",
              style:str="arcade_score_attack", overwrite:bool=False)->dict[str,str]:
    if style not in STYLES:
        raise ValueError("unknown original game style")
    output_dir=output_dir.expanduser().resolve()
    if output_dir.is_symlink():
        raise ValueError("refusing to write to symlinked project root")
    identity=sha256((title+"\0"+target+"\0"+style).encode()).hexdigest()
    project=render_native_project(
        title=title,target_id=target,style=style,candidate_id=identity,
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True,
    )
    # Prevent accidental replacement of existing user project files.
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError("destination is not empty; choose another folder")
    output_dir.mkdir(parents=True,exist_ok=True)
    created={}
    for name,content in sorted(project.files.items()):
        dest=output_dir/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        # Never follow symlinks, even in user-selected existing directories.
        if dest.is_symlink() or dest.parent.is_symlink():
            raise ValueError("refusing symlinked output paths")
        dest.write_text(content,encoding="utf-8")
        created[name]=sha256(content.encode()).hexdigest()
    return created

def main() -> None:
    parser=ArgumentParser(description="Original native game project generator")
    parser.add_argument("--target",default="game_boy")
    parser.add_argument("--style",default="arcade_score_attack")
    parser.add_argument("--title",default="Dragon Tiny Adventure")
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--overwrite",action="store_true")
    parser.add_argument("--compile",action="store_true",help="Run installed native ROM toolchain after writing original source")
    args=parser.parse_args()
    written=emit_demo(args.target,args.out,title=args.title,style=args.style,
                      overwrite=args.overwrite)
    print("Generated native project files:",len(written))
    for name in written:print(" +",name)
    if args.compile:
        from .dragon_native_projects import render_native_project
        from .dragon_native_compile import compile_local
        from .dragon_game_mechanics import Mechanic
        identity=sha256((args.title+"\0"+args.target+"\0"+args.style).encode()).hexdigest()
        project=render_native_project(
            title=args.title,target_id=args.target,style=args.style,
            candidate_id=identity,mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
            authorized=True,
        )
        result=compile_local(project,args.out,authorized=True)
        print("Native compiler:",result.state,result.message)
        if result.binary_path:print("Binary:",result.binary_path,result.binary_sha256)
        if result.state!="compiled_native":
            raise SystemExit(2)
    else:
        print("No ROM/executable has been built. Install the platform toolchain and build.")

if __name__=="__main__":
    main()
