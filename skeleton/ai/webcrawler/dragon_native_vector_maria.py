"""Original Vectrex 6809 and Atari 7800 MARIA homebrew source producers.

Physical hardware and emulator quality are *not* claimed. Original assets
and independent toolchain source only; no commercial SDK/firmware included.
"""
from __future__ import annotations

def _seed(value:int)->int:
    if type(value) is not int or not 0<=value<2**32:
        raise ValueError("native homebrew seed must be uint32")
    return value or 1

VECTREX_SOURCE=r'''/* Original Dragon Vector Quest for Vectrex: real analog vector CRT. */
#include <vectrex/bios.h>
#include <vectrex/types.h>
static int8_t x=0,y=0,starx=45,stary=34,foex=-45,foey=-20;
static uint8_t hp=5,score=0,stage=1,guard=0,frame=0;
static uint16_t rng=__SEED__;
static const int8_t dragon[8]={16,0,0,16,-16,0,0,-16};
static const int8_t crystal[8]={12,0,-12,12,-12,-12,12,-12};
static const int8_t enemy[8]={12,12,-12,12,-12,-12,12,-12};
static uint16_t rnd(void){
 rng^=rng<<7;rng^=rng>>9;rng^=rng<<8;return rng;
}
static int8_t clip(int n){return n<-64?-64:n>64?64:(int8_t)n;}
static void reset_game(void){
 rng=__SEED__;x=0;y=0;starx=45;stary=34;foex=-45;foey=-20;
 hp=5;score=0;stage=1;guard=0;frame=0;
}
static void polygon(int8_t py,int8_t px,const int8_t*shape){
 reset0ref();set_scale(93);moveto_d(py,px);
 draw_vl_a(4,(int8_t*)shape);
}
static void step(void){
 controller_check_joysticks();
 controller_check_buttons();
 if(controller_button_1_1_pressed()){reset_game();return;}
 if(!hp)return;
 if(controller_joystick_1_left())x=clip((int)x-2);
 if(controller_joystick_1_right())x=clip((int)x+2);
 if(controller_joystick_1_up())y=clip((int)y+2);
 if(controller_joystick_1_down())y=clip((int)y-2);
 frame++;if(guard)guard--;
 if(x>starx-10&&x<starx+10&&y>stary-10&&y<stary+10){
  score++;stage=1+score/5;starx=(int8_t)(-50+rnd()%100);
  stary=(int8_t)(-50+rnd()%100);
  if(score%5==0&&hp<5)hp++;
  sound_byte(0,43);sound_byte(1,0);sound_byte(8,12);
 }
 if(frame%(13-(stage<9?stage:9))==0){
  if(foex<x)foex++;else if(foex>x)foex--;
  if(foey<y)foey++;else if(foey>y)foey--;
 }
 if(!guard&&foex>x-12&&foex<x+12&&foey>y-12&&foey<y+12){
  hp--;guard=32;foex=-55;foey=-55;
  sound_byte(0,113);sound_byte(1,0);sound_byte(8,9);
 }
 if(frame%12==0)sound_byte(8,0);
}
int main(void){
 controller_enable_1_x();controller_enable_1_y();
 reset_game();
 for(;;){
  wait_recal();intensity_a(0x60);
  step();
  polygon(stary,starx,crystal);
  polygon(foey,foex,enemy);
  if(!guard||(frame&7)<4)polygon(y,x,dragon);
  for(uint8_t i=0;i<hp;i++){
   reset0ref();set_scale(70);
   moveto_d(84,(int8_t)(-65+i*14));draw_line_d(6,0);
  }
  if(!hp)print_str_c(14,-60,(char*)"DRAGON DOWN");
  update_audio();
 }
 return 0;
}
'''
VECTREX_MAKE='''CMOC ?= cmoc
VECTREC ?= /opt/vectreC
all: build/dragon.bin
build/dragon.bin: src/main.c
\tmkdir -p build
\t$(CMOC) --vectrex -I$(VECTREC)/stdlib -L$(VECTREC)/stdlib -o $@ $<
clean:
\trm -rf build
'''
# 7800basic is not the same as 2600 batari Basic: MARIA DMA and indexed
# PNG 160A sprite assets are required by the real 7800 native compiler.
ATARI7800_SOURCE=r'''rem Dragon Original 7800: MARIA 160A sprite collector and enemy chase.
set zoneheight 16
displaymode 160A
set romsize 32k
BACKGRND = $00
P0C1 = $34
P0C2 = $48
P0C3 = $7A
P1C1 = $0F
P1C2 = $1C
P1C3 = $2C
P2C1 = $32
P2C2 = $42
P2C3 = $52

incgraphic images/dragon.png 160A 0 1 2 3
incgraphic images/crystal.png 160A 0 1 2 3
incgraphic images/foe.png 160A 0 1 2 3

dim playerX = var0
dim playerY = var1
dim starX = var2
dim starY = var3
dim enemyX = var4
dim enemyY = var5
dim hp = var6
dim level = var7
dim points = var8
dim randomState = var9
dim ticks = var10
dim guardFrames = var11

_initGame
 playerX = 18
 playerY = 20
 starX = __STARX__
 starY = __STARY__
 enemyX = 130
 enemyY = 150
 hp = 5
 level = 1
 points = 0
 randomState = __SEED8__
 ticks = 0
 guardFrames = 0

_mainLoop
 clearscreen
 if hp > 0 then gosub _updateGame
 plotsprite dragon 0 playerX playerY
 plotsprite crystal 1 starX starY
 plotsprite foe 2 enemyX enemyY
 drawscreen
 if hp = 0 then if joy0fire0 then goto _initGame
 goto _mainLoop

_updateGame
 ticks = ticks + 1
 if guardFrames > 0 then guardFrames = guardFrames - 1
 if joy0left then if playerX > 3 then playerX = playerX - 1
 if joy0right then if playerX < 144 then playerX = playerX + 1
 if joy0up then if playerY > 3 then playerY = playerY - 1
 if joy0down then if playerY < 175 then playerY = playerY + 1
 if boxcollision(playerX,playerY,8,16,starX,starY,8,16) then gosub _collect
 if ticks > 6 then gosub _enemyMove
 if guardFrames = 0 then if boxcollision(playerX,playerY,8,16,enemyX,enemyY,8,16) then gosub _hit
 return

_collect
 points = points + 1
 level = points / 5
 level = level + 1
 randomState = randomState + 29
 starX = randomState
 if starX > 140 then starX = 18
 randomState = randomState + 37
 starY = randomState
 if starY > 169 then starY = 32
 if points = 5 then hp = 5
 if points = 10 then hp = 5
 return

_enemyMove
 ticks = 0
 if enemyX < playerX then enemyX = enemyX + 1
 if enemyX > playerX then enemyX = enemyX - 1
 if enemyY < playerY then enemyY = enemyY + 1
 if enemyY > playerY then enemyY = enemyY - 1
 return

_hit
 if hp > 0 then hp = hp - 1
 guardFrames = 40
 enemyX = 130
 enemyY = 150
 return
'''
SPRITE_ASSETS=r'''"""Original 7800 three-color 8x16 indexed 160A MARIA sprites."""
from pathlib import Path
from struct import pack
import zlib
PALETTE=bytes((0,0,0,75,178,132,194,237,172,244,205,113))
IMAGES={
"dragon":("00011000","00122100","01222210","12233321",
"12322111","12222210","01222210","00122100","01122100","12222210",
"12333210","01222210","00122100","00221100","01100110","11000011"),
"crystal":("00011000","00122100","01233210","12333321",
"12333321","12333321","01233210","00122100","00011000","00011000",
"00000000","00000000","00000000","00000000","00000000","00000000"),
"foe":("11111111","12222221","12322321","12222221","11222211",
"01222210","01111110","00111100","01111110","11222211","12222221",
"12322321","12222221","12222221","11222211","01100110"),
}
def chunk(name,body):
 return pack(">I",len(body))+name+body+pack(">I",zlib.crc32(name+body)&0xffffffff)
def render(rows):
 if len(rows)!=16 or any(len(row)!=8 or any(c not in "0123" for c in row) for row in rows):
  raise ValueError("invalid native MARIA sprite geometry")
 image=b"".join(b"\0"+bytes(int(c) for c in row) for row in rows)
 return (b"\x89PNG\r\n\x1a\n"+
   chunk(b"IHDR",pack(">IIBBBBB",8,16,8,3,0,0,0))+
   chunk(b"PLTE",PALETTE)+
   chunk(b"IDAT",zlib.compress(image,9))+
   chunk(b"IEND",b""))
def main():
 output=Path("images")
 output.mkdir(exist_ok=True)
 for name,rows in sorted(IMAGES.items()):
  dst=output/(name+".png")
  if dst.is_symlink():raise ValueError("refuse symlink output")
  dst.write_bytes(render(rows))
if __name__=="__main__":
 main()
'''
ATARI_MAKE='''PYTHON ?= python3
BASIC7800 ?= 7800bas
all: build/dragon.a78
images/dragon.png images/crystal.png images/foe.png: tools/create_assets.py
\t$(PYTHON) tools/create_assets.py
build/dragon.a78: src/main.bas images/dragon.png images/crystal.png images/foe.png
\tmkdir -p build
\t$(BASIC7800) src/main.bas
\tcp src/main.bas.a78 build/dragon.a78
clean:
\trm -rf build images/*.png src/main.bas.a78
'''
def native_vector_maria_source(target_id:str,seed:int)->dict[str,str]:
    n=_seed(seed)
    if target_id=="vectrex":
        return {"src/main.c":VECTREX_SOURCE.replace("__SEED__",str(n&65535 or 1)),
                "Makefile":VECTREX_MAKE,
                "README.port.md":"Original vectreC/CMOC 6809 BIOS vector CRT + digital joystick / AY PSG game. Install SDK externally. No compiled/emulator/device certification.\n"}
    if target_id=="atari_7800":
        return {"src/main.bas":ATARI7800_SOURCE.replace("__SEED8__",str(n%211+1))
                 .replace("__STARX__",str(35+n%80))
                 .replace("__STARY__",str(30+(n//37)%95)),
                "tools/create_assets.py":SPRITE_ASSETS,
                "Makefile":ATARI_MAKE,
                "README.port.md":"Original 7800basic MARIA 160A indexed-sprite game. SDK must be installed separately. Game source and original PNG generation only; no compiled/emulator/device evidence. Check 7800basic tool redistribution license.\n"}
    raise ValueError("unknown native Vectrex/Atari 7800 target")
