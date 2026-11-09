"""Compile an original game's SDL2 start/mid/finish screenshot trail.

Exports only pixels from Dragon's locally generated original game, never a
user desktop/camera feed or arbitrary website. The standalone native C
renderer captures actual SDL surfaces while executing actual solver actions.
The operator wrapper chooses a fresh controlled output directory.
"""
from __future__ import annotations

C_CAPTURE=r'''
/* Original game-only SDL2 pixel captures. Frames are saved from the
   genuine native renderer; a successful digest is not a GPU certification. */
static int capture_frame(SDL_Renderer*r,SDL_Window*w,
                         const char*folder,int level,int phase){
 if(strlen(folder)>800)return 0;
 char path[1024];
 int chars=snprintf(path,sizeof(path),"%s/level-%02d-frame-%02d.bmp",
                    folder,level,phase);
 if(chars<=0||chars>=(int)sizeof(path))return 0;
 render_original_game(r,w);
 SDL_Surface*image=SDL_CreateRGBSurfaceWithFormat(
  0,WINDOW_W,WINDOW_H,32,SDL_PIXELFORMAT_RGBA8888);
 if(!image)return 0;
 int ok=SDL_RenderReadPixels(
  r,NULL,SDL_PIXELFORMAT_RGBA8888,image->pixels,image->pitch)==0;
 if(ok)ok=SDL_SaveBMP(image,path)==0;
 SDL_FreeSurface(image);
 if(ok)printf("DRAGON_SDL_FRAME level=%d phase=%d moves=%d digest=%08x\n",
              level,phase,state.moves,(unsigned)state_hash(level));
 return ok;
}
static int capture_solver_frames(SDL_Renderer*r,SDL_Window*w,const char*folder){
 for(int level=0;level<LEVEL_COUNT;level++){
  if(!load_level(level)||!capture_frame(r,w,folder,level+1,0))return 70;
  const char*path=dragon_solutions[level];
  int steps=dragon_solution_length[level];
  int mid=steps/2;
  int saved_mid=0;
  for(int n=0;n<steps;n++){
   if(!perform(path[n]))return 71;
   if(!saved_mid&&n+1>=mid){
    if(!capture_frame(r,w,folder,level+1,1))return 72;
    saved_mid=1;
   }
  }
  if(!saved_mid||!level_done()||native_puzzle_stars()!=3||
     !capture_frame(r,w,folder,level+1,2))return 73;
 }
 printf("DRAGON_SDL_CAPTURE_PASS stages=%d frames=%d\n",
        LEVEL_COUNT,LEVEL_COUNT*3);
 return 0;
}
'''


def enable_sdl_original_game_capture(source:str)->str:
    if not isinstance(source,str):
        raise ValueError("original SDL renderer source must be text")
    place="int main(int argc,char**argv){"
    if source.count(place)!=1 or "render_original_game" not in source:
        raise ValueError("SDL gameplay renderer insertion boundary missing")
    result=source.replace(place,C_CAPTURE+"\n"+place,1)
    marker=' int testing=argc==2&&!strcmp(argv[1],"--render-selftest");'
    if result.count(marker)!=1:
        raise ValueError("SDL game selftest flag anchor changed")
    result=result.replace(marker,
        ' int capturing=argc==3&&!strcmp(argv[1],"--capture-frames");\n'
        ' int testing=capturing||(argc==2&&!strcmp(argv[1],"--render-selftest"));',1)
    marker=' if(testing)result=graphics_selftest(r,w);'
    if result.count(marker)!=1:
        raise ValueError("SDL real gameplay selftest path changed")
    result=result.replace(marker,
        ' if(capturing)result=capture_solver_frames(r,w,argv[2]);\n'
        ' else if(testing)result=graphics_selftest(r,w);',1)
    return result
