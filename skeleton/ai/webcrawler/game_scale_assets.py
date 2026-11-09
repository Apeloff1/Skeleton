"""Original procedural art and audio production: capabilities 051–060.

All assets are synthesized from parameter seeds, not downloaded or copied from
third-party games. Exporters can embed these sprites/SVG/WAV into game archives.
"""
from __future__ import annotations
from dataclasses import dataclass
from io import BytesIO
from math import cos,pi,sin
from hashlib import sha256
import random
import struct
import wave
import html

@dataclass(frozen=True)
class Sprite:
    width:int
    height:int
    pixels:tuple[tuple[int,...],...]
    palette:tuple[str,...]

# 051 Create consistent accessible procedural environment palettes.
def generate_game_palette(seed:int,*,theme:str="fantasy")->tuple[str,...]:
    roots={
        "fantasy":(90,150,205),
        "cyber":(45,220,190),
        "desert":(221,166,89),
        "ice":(162,213,242),
        "forest":(76,163,103),
        "space":(125,105,223),
    }
    if theme not in roots:raise ValueError("unknown palette theme")
    r,g,b=roots[theme];rng=random.Random(seed)
    colors=["#0b1423"]
    for intensity in (.4,.6,.85,1.,1.2,1.4,1.65):
        n=rng.randrange(-10,11)
        colors.append("#"+"".join(f"{max(0,min(255,round(c*intensity)+n)):02x}"
                  for c in (r,g,b)))
    return tuple(colors)

# 052 Generate seeded tileable multi-octave value-noise heightmaps.
def procedural_heightmap(width:int,height:int,*,seed:int,
                         octaves:int=4)->tuple[tuple[float,...],...]:
    if not 2<=width<=256 or not 2<=height<=256 or not 1<=octaves<=7:
        raise ValueError("invalid noise map geometry")
    rng=random.Random(seed)
    result=[[0.]*width for _ in range(height)];total=0.
    for octave in range(octaves):
        scale=2**octave;amp=1/scale;total+=amp
        samples=[[rng.random() for _ in range(scale+1)]
                 for _ in range(scale+1)]
        for y in range(height):
            fy=y*scale/max(1,height-1);iy=min(scale-1,int(fy));ty=fy-iy
            sy=ty*ty*(3-2*ty)
            for x in range(width):
                fx=x*scale/max(1,width-1);ix=min(scale-1,int(fx));tx=fx-ix
                sx=tx*tx*(3-2*tx)
                up=samples[iy][ix]*(1-sx)+samples[iy][ix+1]*sx
                down=samples[iy+1][ix]*(1-sx)+samples[iy+1][ix+1]*sx
                result[y][x]+=(up*(1-sy)+down*sy)*amp
    return tuple(tuple(round(v/total,5) for v in row) for row in result)

# 053 Classify height and moisture maps into actual biome tiles.
def classify_terrain_biomes(heights:tuple[tuple[float,...],...],
                            moisture:tuple[tuple[float,...],...]
                            )->tuple[str,...]:
    if not heights or len(heights)!=len(moisture):
        raise ValueError("incompatible biome maps")
    out=[]
    for heights_row,moist_row in zip(heights,moisture):
        if len(heights_row)!=len(moist_row):
            raise ValueError("biome maps differ in width")
        symbols=[]
        for h,m in zip(heights_row,moist_row):
            if not 0<=h<=1 or not 0<=m<=1:raise ValueError("bad biome value")
            symbols.append("~" if h<.3 else "." if h<.43
                           else "T" if m>.62 else "^" if h>.8 else ",")
        out.append("".join(symbols))
    return tuple(out)

# 054 Create an original 16x16 sprite silhouette from a source seed.
def procedural_sprite(seed:int,*,kind:str="hero",size:int=16,
                      palette:tuple[str,...]|None=None)->Sprite:
    if not 8<=size<=64 or kind not in (
        "hero","enemy","collectible","plant","rock","portal","chest"
    ):
        raise ValueError("invalid original sprite")
    palette=palette or generate_game_palette(seed)
    rng=random.Random(seed)
    rows=[]
    for y in range(size):
        row=[]
        for x in range(size):
            mid=abs((x+.5)-size/2)/(size/2)
            vertical=y/size
            base={
                "hero":.62, "enemy":.72, "collectible":.48,
                "plant":.5, "rock":.84, "portal":.65,"chest":.8,
            }[kind]
            inside=(mid < base * (1-abs(vertical-.5)*.6))
            if kind=="collectible":
                inside=(mid*mid+(vertical-.5)**2*4)<.6
            if kind=="portal":
                inside=inside and (mid>.3 or vertical<.2 or vertical>.8)
            if not inside:row.append(0)
            else:row.append(1+rng.randrange(1,len(palette)-1))
        rows.append(tuple(row))
    return Sprite(size,size,tuple(rows),tuple(palette))

# 055 Convert generated indexed sprites to standalone SVG assets.
def sprite_to_svg(sprite:Sprite,*,pixel_size:int=4)->str:
    if not 1<=pixel_size<=32:raise ValueError("invalid sprite scale")
    result=[f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{sprite.width*pixel_size}" height="{sprite.height*pixel_size}" '
            f'viewBox="0 0 {sprite.width} {sprite.height}" shape-rendering="crispEdges">']
    for y,row in enumerate(sprite.pixels):
        for x,index in enumerate(row):
            if index:
                result.append(f'<rect x="{x}" y="{y}" width="1" height="1" '
                              f'fill="{html.escape(sprite.palette[index],quote=True)}"/>')
    return "".join(result)+"</svg>"

# 056 Create actual multi-frame walk/spark animation with deterministic offsets.
def animate_sprite(sprite:Sprite,*,frames:int=6,shift:int=2
                   )->tuple[Sprite,...]:
    if not 2<=frames<=64 or not 0<=shift<=8:
        raise ValueError("invalid animation request")
    output=[]
    for frame in range(frames):
        xshift=round(sin(2*pi*frame/frames)*shift)
        moved=[]
        for row in sprite.pixels:
            result=[0]*sprite.width
            for x,index in enumerate(row):
                target=x+xshift
                if 0<=target<sprite.width:result[target]=index
            moved.append(tuple(result))
        output.append(Sprite(sprite.width,sprite.height,tuple(moved),
                             sprite.palette))
    return tuple(output)

# 057 Generate an actual multi-sprite SVG atlas and UV placement table.
def pack_sprite_atlas(sprites:tuple[Sprite,...],*,columns:int=4
                      )->tuple[str,tuple[tuple[int,int,int,int],...]]:
    if not sprites or len(sprites)>64 or not 1<=columns<=16:
        raise ValueError("invalid sprite atlas")
    cell=max(max(s.width,s.height) for s in sprites)
    rows=(len(sprites)+columns-1)//columns
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'width="{columns*cell}" height="{rows*cell}" '
           f'viewBox="0 0 {columns*cell} {rows*cell}" '
           f'shape-rendering="crispEdges">']
    coords=[]
    for index,sprite in enumerate(sprites):
        ox=index%columns*cell;oy=index//columns*cell
        coords.append((ox,oy,sprite.width,sprite.height))
        for y,row in enumerate(sprite.pixels):
            for x,color in enumerate(row):
                if color:parts.append(
                    f'<rect x="{ox+x}" y="{oy+y}" width="1" height="1" '
                    f'fill="{sprite.palette[color]}"/>'
                )
    return "".join(parts)+"</svg>",tuple(coords)

# 058 Generate original synthesized WAV effects (pickup/hit/jump/win).
def synthesize_game_effect(kind:str,*,sample_rate:int=22050
                           )->bytes:
    presets={"pickup":(880.,.14,.5),"hit":(165.,.2,.65),
             "jump":(440.,.16,.45),"win":(660.,.6,.5),
             "dash":(240.,.11,.35)}
    if kind not in presets or not 8000<=sample_rate<=48000:
        raise ValueError("invalid original sound effect")
    freq,seconds,gain=presets[kind];samples=[]
    length=round(seconds*sample_rate)
    for i in range(length):
        t=i/sample_rate;envelope=(1-t/seconds)**2
        sweep=freq*(1+t/seconds*(.5 if kind in ("pickup","win") else -.35))
        signal=sin(2*pi*sweep*t)+.3*sin(2*pi*2*sweep*t)
        samples.append(max(-32767,min(32767,round(
            signal*envelope*gain*20000
        ))))
    sink=BytesIO()
    with wave.open(sink,"wb") as output:
        output.setnchannels(1);output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(struct.pack("<"+"h"*len(samples),*samples))
    return sink.getvalue()

# 059 Compose a seeded, original eight-bar melodic note progression.
def compose_game_melody(seed:int,*,bars:int=8,tempo:int=120
                        )->tuple[tuple[int,float,float],...]:
    if not 1<=bars<=64 or not 40<=tempo<=240:
        raise ValueError("invalid music composition")
    rng=random.Random(seed)
    minor=(0,2,3,5,7,8,10)
    notes=[]
    quarter=60/tempo
    for bar in range(bars):
        tonic=rng.choice((48,53,55,60))
        for beat in range(4):
            pitch=tonic+rng.choice(minor)+(12 if beat==0 else 0)
            notes.append((pitch,round((bar*4+beat)*quarter,5),
                          round(quarter*.85,5)))
    return tuple(notes)

# 060 Render sequenced notes into an original mono PCM waveform.
def render_game_melody(notes:tuple[tuple[int,float,float],...],*,
                       rate:int=16000,max_seconds:int=120)->bytes:
    if not notes or len(notes)>10000 or not 8000<=rate<=48000:
        raise ValueError("invalid music rendering")
    duration=max(start+length for _,start,length in notes)
    if duration>max_seconds or duration<=0:raise ValueError("song too long")
    samples=[0.]*int((duration+.1)*rate)
    for pitch,start,length in notes:
        if not 0<=pitch<=127 or not 0<=start or not 0<length<=10:
            raise ValueError("invalid MIDI note")
        frequency=440*2**((pitch-69)/12)
        beginning=int(start*rate);end=min(len(samples),int((start+length)*rate))
        for sample in range(beginning,end):
            t=(sample-beginning)/rate
            sustain=min(1.,t*20)*min(1.,(end-sample)/(rate*.07))
            samples[sample]+=.12*sustain*sin(2*pi*frequency*t)
    pcm=[max(-32767,min(32767,round(v*32767))) for v in samples]
    sink=BytesIO()
    with wave.open(sink,"wb") as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(rate)
        output.writeframes(struct.pack("<"+"h"*len(pcm),*pcm))
    return sink.getvalue()
