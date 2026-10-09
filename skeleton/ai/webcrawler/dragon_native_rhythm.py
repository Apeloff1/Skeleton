"""Original native rhythm-game engine backed by procedural chiptune notation.

Beatmap is native compiled C data. Notes are judged against fixed 60-Hz
simulation frames, with distinct four-lane scoring, hit windows, combos,
health, automatic misses, difficulty and four stage songs. Audio output uses
the SDL2 device with original generated pitches, no sampled copyrighted songs.
"""
from __future__ import annotations
from .dragon_chip_music import compose

ENGINE=r'''/* Original Dragon Beat Forge, SDL2 C99 rhythm game. */
#include <SDL.h>
#include <stdint.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "dragon_rhythm.h"
#define SW 720
#define SH 480
#define LANES 4
#define MAX_LIFE 100
#define CLAMP(x,a,b) ((x)<(a)?(a):((x)>(b)?(b):(x)))
typedef struct{int index,frame,combo,max_combo,score,hp,perfect,good,miss;
               int stage,finished,failed;unsigned int play_ticks;}BeatGame;
static BeatGame g;
static SDL_Window*win;
static SDL_Renderer*renderer;
static SDL_GameController*controller;
static SDL_AudioDeviceID audio;
static uint8_t wave[3000];
static void rect(int x,int y,int w,int h,int r,int green,int b){
 SDL_Rect box={x,y,w,h};
 SDL_SetRenderDrawColor(renderer,r,green,b,255);
 SDL_RenderFillRect(renderer,&box);
}
static void synth(int frequency,int duration){
 if(!audio||frequency<=0)return;
 int length=CLAMP((duration*22050)/1000,0,(int)sizeof(wave));
 int period=CLAMP(22050/frequency,2,2000);
 for(int i=0;i<length;i++){
  int volume=(length-i)*31/(length?length:1);
  wave[i]=(uint8_t)(128+((i/period)&1?volume:-volume));
 }
 SDL_QueueAudio(audio,wave,(uint32_t)length);
}
static void reset_game(void){
 memset(&g,0,sizeof(g));g.hp=MAX_LIFE;
}
static const Note*current_notes(void){
 return rhythm_charts[g.stage];
}
static void next_stage(void){
 if(g.stage+1>=SONG_COUNT){g.finished=1;return;}
 g.stage++;g.frame=0;g.index=0;g.hp=CLAMP(g.hp+15,0,100);
}
static void miss(void){
 g.miss++;g.combo=0;g.hp-=7;
 if(g.hp<=0){g.hp=0;g.failed=1;}
}
static void hit(int lane){
 if(g.finished||g.failed)return;
 const Note *notes=current_notes();
 if(g.index>=NOTES_PER_SONG)return;
 const Note target=notes[g.index];
 int delta=g.frame-target.frame;
 if(target.lane==lane && abs(delta)<=GOOD_WINDOW){
  if(abs(delta)<=PERFECT_WINDOW){
   g.perfect++;g.score+=300+(g.combo>20?100:0);
  }else{
   g.good++;g.score+=100;
  }
  g.combo++;
  if(g.combo>g.max_combo)g.max_combo=g.combo;
  g.index++;g.hp=CLAMP(g.hp+2,0,MAX_LIFE);
  synth(target.frequency,95);
 }else if(abs(delta)<=GOOD_WINDOW){
  /* Striking the wrong lane near a beat is a real miss, not decorative UI. */
  miss();g.index++;
 }else if(delta< -GOOD_WINDOW){
  g.score=CLAMP(g.score-10,0,9999999);
 }
}
static void tick(void){
 if(g.finished||g.failed)return;
 const Note *notes=current_notes();
 g.frame++;g.play_ticks++;
 while(g.index<NOTES_PER_SONG&&g.frame>notes[g.index].frame+GOOD_WINDOW){
  miss();g.index++;
  if(g.failed)return;
 }
 if(g.index>=NOTES_PER_SONG&&g.frame>notes[NOTES_PER_SONG-1].frame+GOOD_WINDOW+15)
  next_stage();
}
static void draw_counter(int x,int y,int num){
 static const unsigned char font[10][5]={
  {7,5,5,5,7},{2,6,2,2,7},{7,1,7,4,7},{7,1,3,1,7},
  {5,5,7,1,1},{7,4,7,5,7},{7,1,1,1,1},{7,1,1,1,1},
  {7,5,7,5,7},{7,5,7,1,7}};
 char str[24];snprintf(str,sizeof(str),"%d",CLAMP(num,0,9999999));
 for(int i=0;str[i];i++)for(int y0=0;y0<5;y0++)
  for(int x0=0;x0<3;x0++)if(font[str[i]-'0'][y0]&(1<<(2-x0)))
   rect(x+i*16+x0*4,y+y0*4,4,4,246,218,147);
}
static void draw(void){
 rect(0,0,SW,SH,16,22,43);
 const int left=145,top=34,bottom=410;
 for(int n=0;n<LANES;n++){
  rect(left+n*110,top,102,bottom-top,n%2?39:31,41,67);
  rect(left+n*110+3,bottom-9,94,9,87,205,164);
 }
 if(!g.finished&&!g.failed){
  const Note *notes=current_notes();
  for(int k=g.index;k<NOTES_PER_SONG;k++){
   Note n=notes[k];int until=n.frame-g.frame;
   if(until>120)break;
   if(until< -GOOD_WINDOW)continue;
   int y=bottom-until*3;
   if(y<top-20||y>SH)continue;
   int col=n.lane%LANES;
   rect(left+col*110+10,y-12,82,22,
        col==0?99:col==1?121:col==2?236:165,
        col==0?209:col==1?148:col==2?129:129,200);
   rect(left+col*110+20,y-6,62,5,247,230,193);
  }
 }
 rect(0,0,SW,29,28,36,58);
 rect(12,9,CLAMP(g.hp*2,0,200),11,g.hp>30?97:218,
      g.hp>30?205:75,114);
 draw_counter(240,5,g.score);
 draw_counter(480,5,g.combo);
 draw_counter(590,5,g.stage+1);
 if(g.failed||g.finished){
  rect(195,170,330,130,g.finished?52:162,g.finished?166:56,92);
  draw_counter(260,205,g.score);
 }
 SDL_RenderPresent(renderer);
}
static void smoke(void){
 reset_game();
 for(int stage=0;stage<SONG_COUNT;stage++){
  const Note*notes=current_notes();
  for(int i=0;i<NOTES_PER_SONG;i++){
   while(g.frame<notes[i].frame)tick();
   hit(notes[i].lane);
  }
  while(!g.finished&&!g.failed&&g.stage==stage)tick();
 }
 int ok=g.finished&&g.perfect==NOTES_PER_SONG*SONG_COUNT&&
        g.good==0&&g.miss==0&&g.hp>0;
 printf("DRAGON_RHYTHM_SMOKE %s perfect=%d good=%d missed=%d maxcombo=%d\n",
       ok?"PASS":"FAIL",g.perfect,g.good,g.miss,g.max_combo);
 if(controller)SDL_GameControllerClose(controller);
 if(audio)SDL_CloseAudioDevice(audio);
 SDL_DestroyRenderer(renderer);SDL_DestroyWindow(win);SDL_Quit();
}
int main(int argc,char**argv){
 if(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_AUDIO|SDL_INIT_GAMECONTROLLER)!=0)return 1;
 win=SDL_CreateWindow("Dragon Beat Forge",SDL_WINDOWPOS_CENTERED,
  SDL_WINDOWPOS_CENTERED,SW,SH,SDL_WINDOW_SHOWN|SDL_WINDOW_RESIZABLE);
 if(!win){SDL_Quit();return 2;}
 renderer=SDL_CreateRenderer(win,-1,SDL_RENDERER_ACCELERATED|SDL_RENDERER_PRESENTVSYNC);
 if(!renderer)renderer=SDL_CreateRenderer(win,-1,SDL_RENDERER_SOFTWARE);
 if(!renderer){SDL_DestroyWindow(win);SDL_Quit();return 3;}
 SDL_RenderSetLogicalSize(renderer,SW,SH);
 SDL_AudioSpec format={0};
 format.freq=22050;format.format=AUDIO_U8;format.channels=1;format.samples=1024;
 audio=SDL_OpenAudioDevice(NULL,0,&format,NULL,0);
 if(audio)SDL_PauseAudioDevice(audio,0);
 for(int i=0;i<SDL_NumJoysticks();i++)
  if(SDL_IsGameController(i)){controller=SDL_GameControllerOpen(i);break;}
 reset_game();
 if(argc==2&&strcmp(argv[1],"--smoke")==0){
  smoke();
  return g.finished&&g.miss==0?0:8;
 }
 Uint32 previous=SDL_GetTicks(),accum=0;int run=1;
 while(run){
  SDL_Event event;
  while(SDL_PollEvent(&event)){
   if(event.type==SDL_QUIT)run=0;
   if(event.type==SDL_KEYDOWN&&!event.key.repeat){
    SDL_Keycode k=event.key.keysym.sym;
    if(k==SDLK_ESCAPE)run=0;
    if(k==SDLK_j)hit(0);
    if(k==SDLK_k)hit(1);
    if(k==SDLK_l)hit(2);
    if(k==SDLK_SEMICOLON)hit(3);
    if(k==SDLK_r&&(g.failed||g.finished))reset_game();
   }
   if(event.type==SDL_CONTROLLERBUTTONDOWN){
    int k=event.cbutton.button;
    if(k==SDL_CONTROLLER_BUTTON_A)hit(0);
    if(k==SDL_CONTROLLER_BUTTON_B)hit(1);
    if(k==SDL_CONTROLLER_BUTTON_X)hit(2);
    if(k==SDL_CONTROLLER_BUTTON_Y)hit(3);
   }
  }
  Uint32 now=SDL_GetTicks(),elapsed=now-previous;previous=now;
  accum+=(elapsed>250?250:elapsed);
  int updates=0;
  while(accum>=16&&updates++<6){tick();accum-=16;}
  draw();SDL_Delay(1);
 }
 if(controller)SDL_GameControllerClose(controller);
 if(audio)SDL_CloseAudioDevice(audio);
 SDL_DestroyRenderer(renderer);SDL_DestroyWindow(win);SDL_Quit();
 return 0;
}
'''

def render_rhythm(*,seed:int,songs:int=4,difficulty:int=4)->dict[str,str]:
    if isinstance(seed,bool) or not isinstance(seed,int) or not 0<=seed<2**32:
        raise ValueError("native rhythm composer seed must be uint32")
    if isinstance(songs,bool) or not isinstance(songs,int) or not 1<=songs<=8:
        raise ValueError("native rhythm chapter count must be 1..8")
    if not isinstance(difficulty,int) or isinstance(difficulty,bool) or not 1<=difficulty<=10:
        raise ValueError("invalid native rhythm difficulty")
    charts=[]
    for stage in range(songs):
        score=compose("arena",(seed+stage*7919)&0xffffffff,64)
        notes=[]
        spacing=max(16,28-difficulty)
        for i,hz in enumerate(score.melody_hz):
            pitch=hz or 262
            lane=(pitch//45+stage+i//16)%4
            notes.append((90+i*spacing,lane,pitch))
        charts.append("  {\n"+",\n".join(
            "    {%d,%d,%d}" % row for row in notes)+"\n  }")
    header=(
      "#ifndef DRAGON_RHYTHM_H\n#define DRAGON_RHYTHM_H\n"
      f"#define SONG_COUNT {songs}\n"
      "#define NOTES_PER_SONG 64\n"
      f"#define PERFECT_WINDOW {max(2,6-difficulty//2)}\n"
      f"#define GOOD_WINDOW {max(6,11-difficulty//2)}\n"
      "typedef struct{int frame,lane,frequency;}Note;\n"
      "static const Note rhythm_charts[SONG_COUNT][NOTES_PER_SONG]={\n"+
      ",\n".join(charts)+"\n};\n#endif\n"
    )
    cmake="""\
cmake_minimum_required(VERSION 3.16)
project(DragonNativeRhythm C)
set(CMAKE_C_STANDARD 99)
find_package(SDL2 REQUIRED)
add_executable(dragon_game src/main.c)
target_include_directories(dragon_game PRIVATE include)
target_link_libraries(dragon_game PRIVATE SDL2::SDL2)
"""
    readme=(
      "# Dragon Original Native Rhythm Game\n\n"
      "True four-lane beat timing engine at 60Hz, native SDL audio synthesis, "
      "difficulty-specific hit windows, judgement, combo, life and ranked score. "
      "Play J/K/L/semicolon or gamepad A/B/X/Y. Bounded original 64-note songs "
      "can be built with cmake -S . -B build && cmake --build build. "
      "Run --smoke for native perfect-play timing verification. "
      "Source generation does not validate how fun the music or play feels.\n"
    )
    return {"src/main.c":ENGINE,"include/dragon_rhythm.h":header,
            "CMakeLists.txt":cmake,"README.engine.md":readme}
