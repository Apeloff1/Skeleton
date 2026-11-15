"""Original procedural tile data and source-bound asset requests.

No asset downloads, copyrighted game assets or external generation are used.
A palette is a design proposal; a tile buffer is actual generated pixel data.
"""
from skeleton.prood.design_contract import digest
from skeleton.prood.world_design import seeded

_PALETTES={
    "moss":("#18271E","#496A49","#8AAF73","#D7C69A"),
    "neon":("#15152B","#603C91","#29C8D0","#F5EBB9"),
    "ember":("#281B23","#863B31","#E37B36","#F4D58B"),
    "frost":("#1C3244","#456D88","#A2D5E4","#F3FAFD"),
}


def build_tiles(ctx,seat,maze):
    palette=list(_PALETTES[ctx["theme"]])
    rng=seeded(ctx["seed"],"tileset",seat)
    tiles=[]
    for kind in ("floor","wall","entry","exit"):
        pixels=[]
        for y in range(8):
            row=[]
            for x in range(8):
                edge=x in (0,7) or y in (0,7)
                if kind=="wall":
                    index=0 if edge else 1+rng.randrange(2)
                elif kind=="floor":
                    index=1 if rng.randrange(5)==0 else 2
                else:
                    index=3 if abs(x-3)+abs(y-3)<=3 else 1
                row.append(index)
            pixels.append(row)
        tiles.append({"id":kind,"pixels":pixels})
    return {"palette":palette,"tiles":tiles,"maze_digest":digest(maze),"tile_size":8}


def validate_tiles(tiles,maze):
    if tiles["maze_digest"]!=digest(maze) or tiles["tile_size"]!=8:
        raise ValueError("tiles are bound to a different layout")
    if not any(tiles["palette"]==list(p) for p in _PALETTES.values()):
        raise ValueError("unsupported palette")
    if [t["id"] for t in tiles["tiles"]]!=["floor","wall","entry","exit"]:
        raise ValueError("tile inventory mismatch")
    for tile in tiles["tiles"]:
        if len(tile["pixels"])!=8 or any(len(row)!=8 or any(type(p) is not int or not 0<=p<4 for p in row) for row in tile["pixels"]):
            raise ValueError("invalid pixel buffer")


def build_assets(tiles):
    # Actual portable PPM image content, not external asset references.
    files={}
    palette=[tuple(int(col[i:i+2],16) for i in (1,3,5)) for col in tiles["palette"]]
    for tile in tiles["tiles"]:
        body="P3\n8 8\n255\n"+"\n".join(
            " ".join(str(channel) for p in row for channel in palette[p]) for row in tile["pixels"]
        )+"\n"
        files["tiles/"+tile["id"]+".ppm"]=body
    from hashlib import sha256
    hashes={name:sha256(body.encode("ascii")).hexdigest() for name,body in sorted(files.items())}
    # This is an asset-only pack, not a complete Godot project. Do not use
    # the project manifest validator, which requires project.godot.
    return {"tile_digest":digest(tiles),"files":files,
            "source_manifest":{"schema":"prood.asset-manifest.v1","file_count":len(files),
                               "files":hashes,"sha256":digest(hashes)},
            "external_assets_used":False}
