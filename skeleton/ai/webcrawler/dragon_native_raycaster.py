"""Actual C99/SDL2 first-person raycaster for native 1990s-style PC games.

Separate world-projection renderer from the 2D engine: real DDA wall traversal,
perspective column depth, camera rotation, depth-tested billboards, key/door
collision, enemy encounters, stage transitions and simulated headless run.
No HTML, JS, third-party images, emulator ROMs or SDK credentials.
"""
from __future__ import annotations
from .dragon_game_blueprints import Campaign,W,H

ENGINE=r'''/* Original native Dragon DDA dungeon, SDL2/C99. */
#include <SDL.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "dragon_campaign.h"
#define WIDTH 640
#define HEIGHT 400
#define RAYS 320
#define MAX_MOBS 40
#define CLAMP(v,lo,hi) ((v)<(lo)?(lo):((v)>(hi)?(hi):(v)))
typedef struct {float x,y;int hp,boss,active;}Mob;
static SDL_Renderer*renderer;
static SDL_Window*window;
static SDL_GameController*controller;
static char tiles[MAP_H][MAP_W+1];
static Mob mobs[MAX_MOBS];
static float depths[RAYS];
static float px,py,angle;
static int stage,health,score,keys,has_key,required_key,guardians,won,lost,cooldown;
static uint32_t rng=GAME_SEED;
static char at(int x,int y){
 if(x<0||x>=MAP_W||y<0||y>=MAP_H)return '#';
 return tiles[y][x];
}
static int blocked(float x,float y){
 char t=at((int)x,(int)y);
 return t=='#'||(t=='D'&&!keys);
}
static int free_point(float x,float y){
 const float r=.15f;
 return !blocked(x-r,y-r)&&!blocked(x+r,y-r)&&
        !blocked(x-r,y+r)&&!blocked(x+r,y+r);
}
static void rect(int x,int y,int w,int h,int red,int green,int blue){
 SDL_Rect a={x,y,w,h};
 SDL_SetRenderDrawColor(renderer,red,green,blue,255);
 SDL_RenderFillRect(renderer,&a);
}
static void new_stage(int id){
 if(id>=STAGE_COUNT){won=1;return;}
 stage=id;keys=has_key=required_key=guardians=0;
 memset(mobs,0,sizeof(mobs));
 for(int y=0;y<MAP_H;y++){
  memcpy(tiles[y],campaign_stage[id][y],MAP_W+1);
  for(int x=0;x<MAP_W;x++){
   char t=tiles[y][x];
   if(t=='S'){px=x+.5f;py=y+.5f;angle=.35f;tiles[y][x]='.';}
   else if(t=='K')required_key=1;
   else if(t=='E'||t=='B'){
    for(int n=0;n<MAX_MOBS;n++)if(!mobs[n].active){
     mobs[n]=(Mob){x+.5f,y+.5f,
       t=='B'?5+id+DESIGN_DIFFICULTY/3:
       1+(DESIGN_DIFFICULTY-1)/3,t=='B',1};
     if(t=='B')guardians++;
     tiles[y][x]='.';break;
    }
   }
  }
 }
 health=CLAMP(health+1,1,6);
}
static void restart(void){
 rng=GAME_SEED;health=4;score=0;won=lost=cooldown=0;
 new_stage(0);
}
static void attack(void){
 float dx=cosf(angle),dy=sinf(angle),best=6.f;
 int hit=-1;
 for(int i=0;i<MAX_MOBS;i++)if(mobs[i].active){
  float vx=mobs[i].x-px,vy=mobs[i].y-py;
  float forward=vx*dx+vy*dy;
  if(forward<=0||forward>=best||fabsf(vx*dy-vy*dx)>forward*.22f)continue;
  float distance=sqrtf(vx*vx+vy*vy);
  int visible=1;
  for(float t=.08f;t<distance;t+=.08f)
   if(blocked(px+vx*t/distance,py+vy*t/distance)){visible=0;break;}
  if(visible){best=forward;hit=i;}
 }
 if(hit>=0){
  Mob*m=&mobs[hit];m->hp--;
  if(m->hp<=0){
   m->active=0;score+=m->boss?400:100;
   if(m->boss&&guardians>0)guardians--;
  }
 }
}
static void step(int ahead,int strafe,int turn,int shoot,int interact){
 if(won||lost){if(interact)restart();return;}
 if(cooldown>0)cooldown--;
 angle+=turn*.047f;
 if(angle>6.2831853f)angle-=6.2831853f;
 if(angle<0)angle+=6.2831853f;
 float dx=cosf(angle),dy=sinf(angle);
 float mx=(ahead*dx-strafe*dy)*.062f;
 float my=(ahead*dy+strafe*dx)*.062f;
 if(free_point(px+mx,py))px+=mx;
 if(free_point(px,py+my))py+=my;
 if(shoot)attack();
 if(interact){
  int x=(int)(px+dx*.7f),y=(int)(py+dy*.7f);
  if(at(x,y)=='D'&&keys){tiles[y][x]='.';keys--;score+=20;}
 }
 int x=(int)px,y=(int)py;
 char t=at(x,y);
 if(t=='K'){tiles[y][x]='.';has_key=1;keys++;score+=40;}
 if(t=='C'||t=='N'){tiles[y][x]='.';health=CLAMP(health+1,0,6);}
 if(t=='*'){tiles[y][x]='.';score+=25;}
 if(t=='G'&&!guardians&&(!required_key||has_key)){
  new_stage(stage+1);return;
 }
 if((t=='^'||t=='~')&&!cooldown){health--;cooldown=40;}
 for(int i=0;i<MAX_MOBS;i++)if(mobs[i].active){
  Mob*m=&mobs[i];
  float vx=px-m->x,vy=py-m->y,dist=sqrtf(vx*vx+vy*vy);
  if(dist<7.f&&dist>.65f){
   float speed=(m->boss?.009f:.006f)+DESIGN_DIFFICULTY*.0008f;
   float nx=m->x+vx/dist*speed,ny=m->y+vy/dist*speed;
   if(free_point(nx,m->y))m->x=nx;
   if(free_point(m->x,ny))m->y=ny;
  }
  if(dist<.65f&&!cooldown){health--;cooldown=40;}
 }
 if(health<=0){health=0;lost=1;}
}
static void render_view(void){
 rect(0,0,WIDTH,HEIGHT/2,38,50,85);
 rect(0,HEIGHT/2,WIDTH,HEIGHT/2,52,43,58);
 const float dirx=cosf(angle),diry=sinf(angle);
 const float planeX=-diry*.67f,planeY=dirx*.67f;
 for(int c=0;c<RAYS;c++){
  float camera=2.f*(float)c/(float)RAYS-1.f;
  float rx=dirx+planeX*camera,ry=diry+planeY*camera;
  int mapx=(int)px,mapy=(int)py,side=0,hit=0;
  float deltaX=fabsf(rx)<1.e-7f?1.e6f:fabsf(1.f/rx);
  float deltaY=fabsf(ry)<1.e-7f?1.e6f:fabsf(1.f/ry);
  int sx=rx<0?-1:1,sy=ry<0?-1:1;
  float distanceX=rx<0?(px-mapx)*deltaX:(mapx+1.f-px)*deltaX;
  float distanceY=ry<0?(py-mapy)*deltaY:(mapy+1.f-py)*deltaY;
  for(int i=0;i<64;i++){
   if(distanceX<distanceY){distanceX+=deltaX;mapx+=sx;side=0;}
   else{distanceY+=deltaY;mapy+=sy;side=1;}
   if(at(mapx,mapy)=='#'||(at(mapx,mapy)=='D'&&!keys)){
    hit=1;break;
   }
  }
  float depth=hit?(side?distanceY-deltaY:distanceX-deltaX):99.f;
  depth=CLAMP(depth,.04f,99.f);
  depths[c]=depth;
  int tall=CLAMP((int)(HEIGHT/depth),1,HEIGHT*3);
  int top=CLAMP((HEIGHT-tall)/2,0,HEIGHT);
  int bottom=CLAMP((HEIGHT+tall)/2,0,HEIGHT);
  int light=CLAMP((int)(130.f/(1.f+depth*.13f)),20,140);
  int r=(at(mapx,mapy)=='D'?166:THEME_ACCENT[0])*light/110;
  int g=(side?92:136)*light/110;
  int b=(side?112:169)*light/110;
  rect(c*2,top,2,bottom-top,r,g,b);
 }
 for(int i=0;i<MAX_MOBS;i++)if(mobs[i].active){
  Mob*m=&mobs[i];
  float x=m->x-px,y=m->y-py;
  float inv=1.f/(planeX*diry-dirx*planeY);
  float tx=inv*(diry*x-dirx*y);
  float ty=inv*(-planeY*x+planeX*y);
  if(ty<=.05f||ty>20.f)continue;
  int center=(int)(WIDTH/2*(1.f+tx/ty));
  int height=CLAMP((int)(HEIGHT/ty),1,HEIGHT*2);
  int width=height/2;
  int top=CLAMP((HEIGHT-height)/2,0,HEIGHT);
  int bottom=CLAMP((HEIGHT+height)/2,0,HEIGHT);
  for(int col=CLAMP(center-width/2,0,WIDTH-1);
      col<CLAMP(center+width/2,0,WIDTH);col+=2)
   if(ty<depths[col/2])
    rect(col,top,2,bottom-top,m->boss?177:233,m->boss?60:98,119);
 }
 rect(WIDTH/2-10,HEIGHT/2,20,1,250,224,124);
 rect(WIDTH/2,HEIGHT/2-10,1,20,250,224,124);
 rect(0,0,WIDTH,35,18,25,39);
 for(int i=0;i<health;i++)rect(9+i*21,10,15,12,246,89,111);
 for(int i=0;i<keys;i++)rect(160+i*14,10,9,11,241,201,81);
 for(int i=0;i<guardians;i++)rect(285+i*13,10,9,11,208,65,103);
 for(int y=0;y<MAP_H;y++)for(int x=0;x<MAP_W;x++)
  rect(WIDTH-MAP_W*3+x*3,HEIGHT-MAP_H*3+y*3,3,3,
       at(x,y)=='#'?62:27,at(x,y)=='#'?69:47,82);
 rect(WIDTH-MAP_W*3+(int)px*3,HEIGHT-MAP_H*3+(int)py*3,5,5,255,224,118);
 if(won||lost)rect(220,120,200,140,won?30:150,won?155:38,80);
 SDL_RenderPresent(renderer);
}
static int key(SDL_GameControllerButton b){
 return controller&&SDL_GameControllerGetButton(controller,b);
}
int main(int argc,char**argv){
 if(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_GAMECONTROLLER|SDL_INIT_EVENTS)!=0)return 1;
 window=SDL_CreateWindow("Dragon DDA Native",SDL_WINDOWPOS_CENTERED,
   SDL_WINDOWPOS_CENTERED,WIDTH,HEIGHT,SDL_WINDOW_RESIZABLE|SDL_WINDOW_SHOWN);
 if(!window){SDL_Quit();return 2;}
 renderer=SDL_CreateRenderer(window,-1,SDL_RENDERER_ACCELERATED|SDL_RENDERER_PRESENTVSYNC);
 if(!renderer)renderer=SDL_CreateRenderer(window,-1,SDL_RENDERER_SOFTWARE);
 if(!renderer){SDL_DestroyWindow(window);SDL_Quit();return 3;}
 SDL_RenderSetLogicalSize(renderer,WIDTH,HEIGHT);
 for(int i=0;i<SDL_NumJoysticks();i++)
  if(SDL_IsGameController(i)){controller=SDL_GameControllerOpen(i);break;}
 restart();
 if(argc==2&&strcmp(argv[1],"--smoke")==0){
  for(int tick=0;tick<480;tick++){
   step(tick%85<60,0,tick%50<25?1:-1,tick%20==0,tick%31==0);
   if(tick%12==0)render_view();
  }
  int finite=1;
  for(int i=0;i<RAYS;i++)if(!isfinite(depths[i])||depths[i]<=0.f)finite=0;
  printf("DRAGON_RAYCAST_SMOKE %s stage=%d score=%d hp=%d\n",
         finite?"PASS":"FAIL",stage,score,health);
  if(controller)SDL_GameControllerClose(controller);
  SDL_DestroyRenderer(renderer);SDL_DestroyWindow(window);SDL_Quit();
  return finite?0:9;
 }
 Uint32 last=SDL_GetTicks(),accum=0;int alive=1;
 while(alive){
  SDL_Event event;int fire=0,act=0;
  while(SDL_PollEvent(&event)){
   if(event.type==SDL_QUIT)alive=0;
   if(event.type==SDL_KEYDOWN&&!event.key.repeat){
    if(event.key.keysym.sym==SDLK_ESCAPE)alive=0;
    if(event.key.keysym.sym==SDLK_SPACE)fire=1;
    if(event.key.keysym.sym==SDLK_e)act=1;
    if(event.key.keysym.sym==SDLK_r)restart();
   }
  }
  Uint32 now=SDL_GetTicks();accum+=CLAMP(now-last,0u,250u);last=now;
  const Uint8*k=SDL_GetKeyboardState(NULL);
  int forward=(k[SDL_SCANCODE_W]||k[SDL_SCANCODE_UP]||
     key(SDL_CONTROLLER_BUTTON_DPAD_UP))-
     (k[SDL_SCANCODE_S]||key(SDL_CONTROLLER_BUTTON_DPAD_DOWN));
  int strafe=(k[SDL_SCANCODE_D]||key(SDL_CONTROLLER_BUTTON_DPAD_RIGHT))-
     (k[SDL_SCANCODE_A]||key(SDL_CONTROLLER_BUTTON_DPAD_LEFT));
  int rotate=(k[SDL_SCANCODE_RIGHT]||
     key(SDL_CONTROLLER_BUTTON_RIGHTSHOULDER))-
     (k[SDL_SCANCODE_LEFT]||
     key(SDL_CONTROLLER_BUTTON_LEFTSHOULDER));
  int count=0;
  while(accum>=16&&count++<6){
   step(CLAMP(forward,-1,1),CLAMP(strafe,-1,1),
        CLAMP(rotate,-1,1),fire,act);
   fire=act=0;accum-=16;
  }
  render_view();SDL_Delay(1);
 }
 if(controller)SDL_GameControllerClose(controller);
 SDL_DestroyRenderer(renderer);SDL_DestroyWindow(window);SDL_Quit();
 return 0;
}
'''
def render_raycaster(campaign:Campaign,*,difficulty:int=4,
                     theme:str="ancient_ruins")->dict[str,str]:
    themes={"crystals":(110,221,200),"ancient_ruins":(124,140,96),
            "forest":(81,157,92),"ice":(110,204,232),
            "space":(125,110,220),"volcano":(229,93,65),
            "clockwork":(211,162,92)}
    if theme not in themes or isinstance(difficulty,bool) or not isinstance(
        difficulty,int) or not 1<=difficulty<=10:
        raise ValueError("invalid 3D game theme or difficulty")
    if campaign.mode!="dungeon" or not 1<=len(campaign.stages)<=8:
        raise ValueError("3D game requires bounded dungeon campaign")
    if any(len(s.terrain)!=H or any(len(row)!=W for row in s.terrain)
           for s in campaign.stages):
        raise ValueError("invalid 3D map")
    if any(any(c not in ".#^*EGKDCNBS~=+" for c in row)
           for stage in campaign.stages for row in stage.terrain):
        raise ValueError("unsupported 3D tile")
    blocks=[" {\n"+",\n".join('  "'+r+'"' for r in stage.terrain)+"\n }"
            for stage in campaign.stages]
    header=(
      "#ifndef DRAGON_CAMPAIGN_H\n#define DRAGON_CAMPAIGN_H\n"
      f"#define MAP_W {W}\n#define MAP_H {H}\n"
      f"#define STAGE_COUNT {len(campaign.stages)}\n"
      f"#define GAME_SEED {campaign.seed or 1}u\n"
      f"#define DESIGN_DIFFICULTY {difficulty}\n"
      "static const unsigned char THEME_ACCENT[3]={"+
      ",".join(str(x) for x in themes[theme])+"};\n"
      "static const char campaign_stage[STAGE_COUNT][MAP_H][MAP_W+1]={\n"+
      ",\n".join(blocks)+"\n};\n#endif\n"
    )
    cmake="""\
cmake_minimum_required(VERSION 3.16)
project(DragonNative3D C)
set(CMAKE_C_STANDARD 99)
find_package(SDL2 REQUIRED)
add_executable(dragon_game src/main.c)
target_include_directories(dragon_game PRIVATE include)
target_link_libraries(dragon_game PRIVATE SDL2::SDL2)
if(NOT MSVC)
  target_link_libraries(dragon_game PRIVATE m)
endif()
"""
    readme=(
      "# Dragon original native raycasting game\n\n"
      "Real software DDA raycasting, perspective walls, depth-tested enemies, "
      "fixed-step native gamepad and keyboard control, locked-door encounters "
      "and multi-stage health/combat progression. "
      "Build with cmake -S . -B build && cmake --build build. "
      "Run with arrows to rotate, WASD to move, Space to shoot, E to use key. "
      "This is source-only until actual SDL compiler and gameplay checks pass.\n"
    )
    return {"src/main.c":ENGINE,"include/dragon_campaign.h":header,
            "CMakeLists.txt":cmake,"README.engine.md":readme}
