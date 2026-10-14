"""Actual SDL2 original game HUD: visible progress and earned grades.

Renders a stage progression strip, actual crate occupancy meter, par/effort
gauge, 0–3 original gold stars and a solved-state border. Reads exactly the
same C99 game-state fields as keyboard/gamepad physics. No fake level
complete, timed animation reward or ChatGPT learning XP is ever awarded.
"""
from __future__ import annotations

SCHEMA="skeleton.ai.dragon.original_native_game_hud.v1"
ANCHOR=" char title[180];"

HUD_C=r''' /* Original-game status strip: real state and verified par data.
    No separate gameplay simulator or target-specific forgery. */
 SDL_Color slate={26,48,58,255},active={118,195,149,255};
 SDL_Color completed={227,190,91,255},missing={59,76,88,255};
 for(int i=0;i<LEVEL_COUNT;i++){
  int width=(450/LEVEL_COUNT)-5;
  SDL_Color chosen=(i<chapter)?completed:(i==chapter?active:missing);
  box(r,80+i*(450/LEVEL_COUNT),9,width,12,chosen);
 }
 int placed=0;
 for(int i=0;i<state.count;i++)
  if(goals[state.boxes[i]])placed++;
 int filled=state.count?placed*450/state.count:0;
 box(r,80,454,450,10,slate);
 if(filled)box(r,80,454,filled,10,active);
 /* Effort meter shows actual moves compared with optimal path, not
    an invented estimate of play quality. Fully reached par fills meter. */
 int minimum=dragon_solution_length[chapter];
 int effective=state.moves>minimum?state.moves:minimum;
 int ratio=effective?450*minimum/effective:0;
 if(ratio<0)ratio=0;
 if(ratio>450)ratio=450;
 box(r,80,470,450,5,slate);
 if(ratio)box(r,80,470,ratio,5,completed);
 int stars=native_puzzle_stars();
 for(int n=0;n<3;n++){
  SDL_Color paint=n<stars?completed:missing;
  int base=553+n*24;
  box(r,base,9,16,4,paint);
  box(r,base+6,3,4,18,paint);
  box(r,base+3,7,10,10,paint);
 }
 if(level_done()){
  /* Winning is based solely on actual crate placement. */
  box(r,70,37,8,406,completed);
  box(r,561,37,8,406,completed);
 }
'''
def enable_original_native_hud(source:str)->str:
    if not isinstance(source,str) or source.count(ANCHOR)!=1 or HUD_C in source:
        raise ValueError("SDL2 original game frame renderer changed")
    if "native_puzzle_stars()" not in source or "render_original_game" not in source:
        raise ValueError("HUD requires native original game score and physics")
    return source.replace(ANCHOR,HUD_C+"\n"+ANCHOR,1)
