"""Original Arduboy2 ATmega32u4 arcade game: bounded SRAM, real OLED."""
from __future__ import annotations
GAME=r'''#include <Arduboy2.h>
#include <stdint.h>
/* One-bit 128x64 Dragon Micro Quest, no heap or external ROMs. */
Arduboy2 arduboy;
static uint16_t rng=__SEED__;
static uint8_t x,y,gx,gy,ex,ey,hp,score,level,frame,shield;
static uint16_t rnd(void){
 rng^=(uint16_t)(rng<<7);rng^=(uint16_t)(rng>>9);
 rng^=(uint16_t)(rng<<8);return rng;
}
static void restart(){
 rng=__SEED__;x=13;y=22;gx=104;gy=40;ex=92;ey=21;
 hp=3;score=0;level=1;frame=0;shield=0;
}
static bool hit(uint8_t a,uint8_t b,uint8_t c,uint8_t d){
 return (int)a<c+7&&(int)a+7>c&&(int)b<d+7&&(int)b+7>d;
}
void setup(){
 arduboy.begin();arduboy.setFrameRate(30);restart();
}
void loop(){
 if(!arduboy.nextFrame())return;
 arduboy.pollButtons();
 if(arduboy.justPressed(B_BUTTON))restart();
 if(hp){
  if(arduboy.pressed(LEFT_BUTTON)&&x>2)x--;
  if(arduboy.pressed(RIGHT_BUTTON)&&x<119)x++;
  if(arduboy.pressed(UP_BUTTON)&&y>11)y--;
  if(arduboy.pressed(DOWN_BUTTON)&&y<55)y++;
  if(arduboy.justPressed(A_BUTTON)&&!shield)shield=9;
  if(hit(x,y,gx,gy)){
   score++;level=1+score/3;
   gx=9+(uint8_t)(rnd()%110);gy=14+(uint8_t)(rnd()%40);
   if(score%7==0&&hp<3)hp++;
  }
  if(shield)shield--;
  if(frame%(14-(level>7?7:level))==0){
   if(ex<x)ex++;else if(ex>x)ex--;
   if(ey<y)ey++;else if(ey>y)ey--;
  }
  if(!shield&&hit(x,y,ex,ey)){
   hp--;shield=20;ex=94;ey=23;
  }
 }
 frame++;
 arduboy.clear();
 arduboy.setCursor(0,0);arduboy.print(F("DRAGON"));
 arduboy.setCursor(48,0);arduboy.print(score);
 arduboy.setCursor(80,0);arduboy.print(F("HP"));arduboy.print(hp);
 arduboy.drawRect(0,10,128,54,WHITE);
 arduboy.fillRect(gx,gy,6,6,WHITE);
 arduboy.drawRect(gx+1,gy+1,4,4,BLACK);
 arduboy.fillRect(ex,ey,7,7,WHITE);
 arduboy.drawPixel(ex+2,ey+2,BLACK);
 if(!shield||(frame&2)){
  arduboy.fillRect(x,y,7,7,WHITE);
  arduboy.drawPixel(x+5,y+2,BLACK);
 }
 if(!hp){
  arduboy.drawRect(5,26,118,17,WHITE);
  arduboy.setCursor(11,31);
  arduboy.print(F("B: RESTART"));
 }
 arduboy.display();
}
'''
PLATFORMIO="""[env:arduboy]
platform = atmelavr
board = arduboy
framework = arduino
lib_deps = MLXXXp/Arduboy2
build_flags = -std=gnu++11 -Os
"""
def arduboy_source(seed:int)->dict[str,str]:
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError("Arduboy seed must be uint32")
    return {
        "src/main.cpp":GAME.replace("__SEED__",str(seed&0xffff or 1)),
        "platformio.ini":PLATFORMIO,
        "README.port.md":"Original Arduboy2 AVR game: monochrome OLED, "
            "real 6 buttons, collision, collectibles, escalating enemies. "
            "Requires external PlatformIO and Arduboy2; build with "
            "pio run -e arduboy. No native HEX compiled or device tested.\n",
    }
