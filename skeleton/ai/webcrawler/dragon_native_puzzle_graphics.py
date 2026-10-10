"""Real original SDL2 puzzle window sharing the canonical C99 gameplay state.

No duplicated physics: the graphical executable includes the exact native
terminal game's C module and calls its load_level, perform, undo, hint and
star functions directly. Native SDL2 must be independently installed; the
terminal executable remains SDL-free and always buildable with a C99 compiler.
"""
from __future__ import annotations
from .dragon_retro_assets import BITMAPS
PIXELS=("dragon","dragon_blink","dragon_walk","star")
SCHEMA="skeleton.ai.dragon.original_native_sdl_puzzle.v1"

C_GRAPHICS=r'''/* Original Dragon SDL2 graphical native game, no WebView/HTML layer.
   All movement and goals use the same real game engine as main.c. */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef main
#undef main
#endif
#define main dragon_terminal_entry
#include "main.c"
#undef main
#include "dragon_puzzle_pixels.h"
#define WINDOW_W 640
#define WINDOW_H 480
#define CELL 40
static const SDL_Color palette[4]={
 {13,24,32,255},{51,103,88,255},{116,187,153,255},{230,237,184,255}
};
static void box(SDL_Renderer*r,int x,int y,int w,int h,SDL_Color color){
 SDL_Rect rectangle={x,y,w,h};
 SDL_SetRenderDrawColor(r,color.r,color.g,color.b,255);
 SDL_RenderFillRect(r,&rectangle);
}
static void sprite(SDL_Renderer*r,const uint8_t*picture,int x,int y){
 for(int row=0;row<8;row++)for(int col=0;col<8;col++){
  uint8_t index=picture[row*8+col]&3;
  if(index)box(r,x+col*5,y+row*5,5,5,palette[index]);
 }
}
static void render_original_game(SDL_Renderer*r,SDL_Window*w){
 SDL_Color floor={20,41,54,255},wall={74,94,108,255};
 SDL_Color goal={47,115,166,255},crate={180,116,58,255};
 box(r,0,0,WINDOW_W,WINDOW_H,palette[0]);
 for(int row=0;row<LEVEL_H;row++)for(int col=0;col<LEVEL_W;col++){
  int cell=row*LEVEL_W+col,x=80+col*CELL,y=40+row*CELL;
  box(r,x,y,CELL-1,CELL-1,world[cell]=='#'?wall:floor);
  if(world[cell]=='#')continue;
  if(goals[cell]){
   box(r,x+9,y+9,CELL-19,CELL-19,goal);
   sprite(r,dragon_pixel_star,x,y);
  }
  if(crate_at(cell)>=0){
   box(r,x+4,y+4,CELL-9,CELL-9,crate);
   box(r,x+10,y+10,CELL-21,CELL-21,palette[2]);
  }
  if(cell==state.player){
   const uint8_t*actor=level_done()?dragon_pixel_dragon_blink:
     ((state.moves&1)?dragon_pixel_dragon_walk:dragon_pixel_dragon);
   sprite(r,actor,x,y);
  }
 }
 char title[180];
 snprintf(title,sizeof(title),
  "Original Dragon Game | stage %d/%d | moves %d | stars %d",
  chapter+1,LEVEL_COUNT,state.moves,native_puzzle_stars());
 SDL_SetWindowTitle(w,title);
}
static void keyboard(SDL_Keycode k){
 if(k==SDLK_LEFT||k==SDLK_a)perform('a');
 else if(k==SDLK_RIGHT||k==SDLK_d)perform('d');
 else if(k==SDLK_UP||k==SDLK_w)perform('w');
 else if(k==SDLK_DOWN||k==SDLK_s)perform('s');
 else if(k==SDLK_u||k==SDLK_BACKSPACE)rollback();
 else if(k==SDLK_r)load_level(chapter);
 else if(level_done()&&(k==SDLK_n||k==SDLK_1||k==SDLK_2)){
  int route=k==SDLK_2?1:0;
  if(route<dragon_branch_count[chapter])
   load_level(dragon_branch_next[chapter][route]);
 }
 else if(k==SDLK_F5||k==SDLK_k)write_local_original_save();
 else if(k==SDLK_F9||k==SDLK_l)read_local_original_save();
 else if(k==SDLK_h){
  char move=shortest_hint();
  if(move)printf("DRAGON_SDL_HINT move=%c\n",move);
 }
}
static void gamepad(uint8_t button){
 if(button==SDL_CONTROLLER_BUTTON_DPAD_LEFT)perform('a');
 else if(button==SDL_CONTROLLER_BUTTON_DPAD_RIGHT)perform('d');
 else if(button==SDL_CONTROLLER_BUTTON_DPAD_UP)perform('w');
 else if(button==SDL_CONTROLLER_BUTTON_DPAD_DOWN)perform('s');
 else if(button==SDL_CONTROLLER_BUTTON_B)rollback();
 else if(button==SDL_CONTROLLER_BUTTON_X)load_level(chapter);
 else if(button==SDL_CONTROLLER_BUTTON_START)write_local_original_save();
 else if(button==SDL_CONTROLLER_BUTTON_BACK)read_local_original_save();
 else if(level_done()&&
         (button==SDL_CONTROLLER_BUTTON_A||button==SDL_CONTROLLER_BUTTON_Y)){
  int option=button==SDL_CONTROLLER_BUTTON_Y?1:0;
  if(option<dragon_branch_count[chapter])
   load_level(dragon_branch_next[chapter][option]);
 }
}
static int frame_checked(SDL_Renderer*r,SDL_Window*w){
 uint32_t*pixels=(uint32_t*)malloc(WINDOW_W*WINDOW_H*4);
 if(!pixels)return 0;
 render_original_game(r,w);
 int valid=SDL_RenderReadPixels(r,NULL,SDL_PIXELFORMAT_RGBA8888,
                               pixels,WINDOW_W*4)==0;
 uint32_t checksum=2166136261u;
 if(valid)for(int i=0;i<WINDOW_W*WINDOW_H;i++)
  checksum=(checksum^pixels[i])*16777619u;
 free(pixels);
 return valid&&checksum!=0;
}
static int graphics_selftest(SDL_Renderer*r,SDL_Window*w){
 for(int level=0;level<LEVEL_COUNT;level++){
  if(!load_level(level)||!frame_checked(r,w))return 41;
  const char*solution=dragon_solutions[level];
  for(int i=0;i<dragon_solution_length[level];i++)
   if(!perform(solution[i]))return 42;
  if(!level_done()||native_puzzle_stars()!=3||!frame_checked(r,w))
   return 43;
  printf("DRAGON_SDL_STAGE_PASS level=%d\n",level+1);
 }
 printf("DRAGON_SDL_RENDER_GAMEPLAY_PASS stages=%d\n",LEVEL_COUNT);
 return 0;
}
int main(int argc,char**argv){
 int testing=argc==2&&!strcmp(argv[1],"--render-selftest");
 SDL_SetMainReady();
 if(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_GAMECONTROLLER)!=0)return 31;
 SDL_Window*w=SDL_CreateWindow("Original Dragon Game",
  SDL_WINDOWPOS_CENTERED,SDL_WINDOWPOS_CENTERED,WINDOW_W,WINDOW_H,
  testing?SDL_WINDOW_HIDDEN:SDL_WINDOW_SHOWN);
 if(!w){SDL_Quit();return 32;}
 SDL_Renderer*r=SDL_CreateRenderer(w,-1,
  testing?SDL_RENDERER_SOFTWARE:SDL_RENDERER_ACCELERATED|SDL_RENDERER_PRESENTVSYNC);
 if(!r)r=SDL_CreateRenderer(w,-1,SDL_RENDERER_SOFTWARE);
 if(!r){SDL_DestroyWindow(w);SDL_Quit();return 33;}
 SDL_GameController*controller=NULL;
 for(int n=0;n<SDL_NumJoysticks();n++)if(SDL_IsGameController(n)){
  controller=SDL_GameControllerOpen(n);
  if(controller)break;
 }
 if(!load_level(0))return 34;
 int result=0;
 if(testing)result=graphics_selftest(r,w);
 else {
  int running=1;
  while(running){
   SDL_Event e;
   while(SDL_PollEvent(&e)){
    if(e.type==SDL_QUIT)running=0;
    else if(e.type==SDL_KEYDOWN&&!e.key.repeat){
     if(e.key.keysym.sym==SDLK_ESCAPE)running=0;
     else keyboard(e.key.keysym.sym);
    }else if(e.type==SDL_CONTROLLERBUTTONDOWN)gamepad(e.cbutton.button);
   }
   render_original_game(r,w);
   SDL_RenderPresent(r);
   SDL_Delay(16);
  }
 }
 if(controller)SDL_GameControllerClose(controller);
 SDL_DestroyRenderer(r);
 SDL_DestroyWindow(w);
 SDL_Quit();
 return result;
}
'''


def pixel_header(*,hero:str="hatchling",theme:str="ancient_ruins",
                 palette:str="dmg_green",seed:int=1)->str:
    from .dragon_native_artforge import original_tiles
    sprites=original_tiles(hero=hero,theme=theme,palette=palette,seed=seed)
    rows=["#ifndef DRAGON_ORIGINAL_PIXELS_H",
          "#define DRAGON_ORIGINAL_PIXELS_H","#include <stdint.h>"]
    for name in PIXELS:
        data=[int(p) for line in sprites[name] for p in line]
        if len(data)!=64 or any(pixel not in (0,1,2,3) for pixel in data):
            raise ValueError("original native pixel source malformed")
        rows.append("static const uint8_t dragon_pixel_"+name+"[64]={")
        for start in range(0,64,8):
            rows.append(" "+",".join(str(x) for x in data[start:start+8])+",")
        rows.append("};")
    rows.append("#endif")
    return "\n".join(rows)+"\n"


def enable_puzzle_graphics(
    files:dict[str,str],*,hero:str="hatchling",
    theme:str="ancient_ruins",palette:str="dmg_green",seed:int=1,
)->dict[str,str]:
    if not isinstance(files,dict) or "src/main.c" not in files or "Makefile" not in files:
        raise ValueError("original native C99 puzzle source incomplete")
    if "static int perform(char key)" not in files["src/main.c"]:
        raise ValueError("graphical C99 source cannot find original engine state")
    result=dict(files)
    from .dragon_native_puzzle_capture import enable_sdl_original_game_capture
    from .dragon_native_puzzle_hud import enable_original_native_hud
    result["src/graphics.c"]=enable_sdl_original_game_capture(
        enable_original_native_hud(C_GRAPHICS)
    )
    result["include/dragon_puzzle_pixels.h"]=pixel_header(
        hero=hero,theme=theme,palette=palette,seed=seed,
    )
    result["README.graphics.md"]=(
        "# Original SDL2 Dragon Puzzle\n\n"
        "Native pixel-art 640x480 window with D-pad controller, WASD/arrow "
        "controls, undo, restart, hint and earned stars. True C99 puzzle "
        "physics are reused from main.c, not rewritten. "
        "Build with make graphics when SDL2 and pkg-config are installed. "
        "Run ./dragon_game_sdl, or --render-selftest with SDL_VIDEODRIVER=dummy "
        "for real renderer frame generation and solved campaign state."
    )
    result["Makefile"]+=(
        "\ngraphics: src/graphics.c src/main.c include/dragon_puzzle_pixels.h\n"
        "\t$(CC) $(CFLAGS) -Iinclude $(shell pkg-config --cflags sdl2) "
        "src/graphics.c -o dragon_game_sdl $(shell pkg-config --libs sdl2)\n"
    )
    result["CMakeLists.txt"]+=(
        "\nfind_package(PkgConfig QUIET)\n"
        "if(PkgConfig_FOUND)\n"
        "  pkg_check_modules(DRAGON_SDL2 QUIET sdl2)\n"
        "  if(DRAGON_SDL2_FOUND)\n"
        "    add_executable(dragon_game_sdl src/graphics.c)\n"
        "    target_include_directories(dragon_game_sdl PRIVATE include ${DRAGON_SDL2_INCLUDE_DIRS})\n"
        "    target_compile_options(dragon_game_sdl PRIVATE ${DRAGON_SDL2_CFLAGS_OTHER})\n"
        "    target_link_directories(dragon_game_sdl PRIVATE ${DRAGON_SDL2_LIBRARY_DIRS})\n"
        "    target_link_libraries(dragon_game_sdl ${DRAGON_SDL2_LIBRARIES})\n"
        "  endif()\n"
        "endif()\n"
    )
    return result
