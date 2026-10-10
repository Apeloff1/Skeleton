"""Original native TinyCircuits Thumby mono handheld game with testable rules.

MicroPython 72x40 direct-display source, Thumby D-pad/A/B and piezo audio.
Deterministic 32-bit RNG; fixed memory state; no downloaded assets,
network, commercial character/ROM, import-time actions, or host dependencies.
Device-specific rendering is distinct from gameplay simulation.
"""
from __future__ import annotations

GAME=r'''# Original Dragon Micro Quest for the 72x40 TinyCircuits Thumby.
# Keyboard mapping: D-pad moves, A shield, B dashes; A starts/restarts.
# No external game assets, serial/network APIs or proprietary ROMs.
WIDTH=72
HEIGHT=40
HX=0
HY=1
GX=2
GY=3
EX=4
EY=5
HP=6
SCORE=7
STAGE=8
TICK=9
RNG=10
GUARD=11
COOLDOWN=12
MODE=13
DIRX=14
DIRY=15
READY=0
PLAYING=1
DEFEAT=2
VICTORY=3
UP=1
DOWN=2
LEFT=4
RIGHT=8
ACTION_A=16
ACTION_B=32
DRAGON=bytes((24,60,126,223,255,126,36,36))
CRYSTAL=bytes((0,24,60,126,60,24,0,0))
FOE=bytes((60,126,255,219,255,126,60,0))
MAX_CRYSTALS=16
START_SEED=__SEED__

def fresh(seed=START_SEED):
    # Small fixed-size mutable state; repeatable for host and microcontroller.
    seed=(int(seed)&0xffffffff) or 1
    return [9,20,49,20,62,29,3,0,1,0,seed,0,0,READY,1,0]

def _rand(s,limit):
    x=s[RNG]&0xffffffff
    x^=(x<<13)&0xffffffff
    x^=(x>>17)
    x^=(x<<5)&0xffffffff
    s[RNG]=x&0xffffffff
    return s[RNG]%limit

def _bound(x,a,b):
    return a if x<a else b if x>b else x

def step(s,held,pressed):
    # Event: 0 none, 1 crystal, 2 hit, 3 shield, 4 victory, 5 reset.
    if s[MODE]!=PLAYING:
        if pressed&ACTION_A:
            new=fresh(s[RNG])
            for i in range(16):
                s[i]=new[i]
            s[MODE]=PLAYING
            return 5
        return 0
    dx=int(bool(held&RIGHT))-int(bool(held&LEFT))
    dy=int(bool(held&DOWN))-int(bool(held&UP))
    if dx or dy:
        s[DIRX]=dx
        s[DIRY]=dy
    if s[GUARD]>0:s[GUARD]-=1
    if s[COOLDOWN]>0:s[COOLDOWN]-=1
    event=0
    if pressed&ACTION_A and s[COOLDOWN]==0:
        s[GUARD]=18
        s[COOLDOWN]=38
        event=3
    dash=2 if (pressed&ACTION_B and s[COOLDOWN]==0) else 1
    if dash==2:s[COOLDOWN]=22
    s[HX]=_bound(s[HX]+dx*dash,1,WIDTH-9)
    s[HY]=_bound(s[HY]+dy*dash,10,HEIGHT-9)
    s[TICK]+=1
    if abs(s[HX]-s[GX])<7 and abs(s[HY]-s[GY])<7:
        s[SCORE]+=1
        s[STAGE]=1+s[SCORE]//4
        s[GX]=3+_rand(s,WIDTH-13)
        s[GY]=11+_rand(s,HEIGHT-21)
        event=1
        if s[SCORE]%6==0 and s[HP]<3:s[HP]+=1
        if s[SCORE]>=MAX_CRYSTALS:
            s[MODE]=VICTORY
            return 4
    # Every 3–8 ticks the enemy advances one pixel on each axis.
    # The cooldown persists through frame rendering and controller updates.
    enemy_interval=max(3,9-s[STAGE])
    if s[TICK]%enemy_interval==0:
        s[EX]+=(1 if s[HX]>s[EX] else -1 if s[HX]<s[EX] else 0)
        s[EY]+=(1 if s[HY]>s[EY] else -1 if s[HY]<s[EY] else 0)
    if abs(s[HX]-s[EX])<7 and abs(s[HY]-s[EY])<7 and not s[GUARD]:
        s[HP]-=1
        s[GUARD]=32
        s[EX]=WIDTH-11
        s[EY]=HEIGHT-10
        event=2
        if s[HP]<=0:
            s[HP]=0
            s[MODE]=DEFEAT
    return event

def render(s,thumby):
    d=thumby.display
    d.fill(0)
    if s[MODE]==READY:
        d.drawText("DRAGON",17,5,1)
        d.drawText("MICRO QUEST",1,16,1)
        d.drawText("A START",13,30,1)
    else:
        d.drawText("S:"+str(s[SCORE]),0,0,1)
        d.drawText("HP:"+str(s[HP]),38,0,1)
        d.drawRectangle(0,9,72,31,1)
        d.blit(CRYSTAL,s[GX],s[GY],8,8,0,False,False)
        d.blit(FOE,s[EX],s[EY],8,8,0,False,False)
        if not s[GUARD] or s[TICK]%6<3:
            d.blit(DRAGON,s[HX],s[HY],8,8,0,False,False)
        if s[MODE]==DEFEAT:
            d.drawFilledRectangle(2,14,68,20,0)
            d.drawText("DRAGON DOWN",2,15,1)
            d.drawText("A RETRY",11,25,1)
        if s[MODE]==VICTORY:
            d.drawFilledRectangle(2,14,68,20,0)
            d.drawText("QUEST CLEAR",2,15,1)
            d.drawText("A AGAIN",12,25,1)
    d.update()

def device_buttons(thumby):
    held=0
    if thumby.buttonU.pressed():held|=UP
    if thumby.buttonD.pressed():held|=DOWN
    if thumby.buttonL.pressed():held|=LEFT
    if thumby.buttonR.pressed():held|=RIGHT
    pressed=0
    if thumby.buttonA.justPressed():pressed|=ACTION_A
    if thumby.buttonB.justPressed():pressed|=ACTION_B
    return held,pressed

def run(max_frames=-1,read_buttons=None,device=None):
    # Strict dependency boundary: importing this source never opens a device.
    if device is None:
        import thumby
        device=thumby
    device.display.setFPS(30)
    state=fresh()
    frames=0
    while max_frames<0 or frames<max_frames:
        held,pressed=(read_buttons() if read_buttons is not None
                      else device_buttons(device))
        event=step(state,held,pressed)
        if event==1:device.audio.play(659,55)
        elif event==2:device.audio.play(196,160)
        elif event==3:device.audio.play(440,55)
        elif event==4:device.audio.play(988,220)
        render(state,device)
        frames+=1
    return state

if __name__=="__main__":
    run()
'''

def thumby_source(seed:int)->dict[str,str]:
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError("Thumby source generator requires uint32 seed")
    script=GAME.replace("__SEED__",str(seed or 1))
    # Official Thumby launcher looks for Games/<Folder>/<Folder>.py.
    # The controller and frame pacing use the built-in Thumby MicroPython SDK,
    # rather than PC SDL or an HTML emulator.
    make=(
        "PYTHON ?= python3\n"
        "MPREMOTE ?= mpremote\n"
        "all: check\n"
        "check:\n"
        "\t$(PYTHON) -m py_compile Games/DragonMicroQuest/DragonMicroQuest.py\n"
        "deploy: check\n"
        "\t@echo 'Use the Thumby Code Editor to copy Games/DragonMicroQuest/"
        "DragonMicroQuest.py to your own device; no unattended flashing.'\n"
    )
    return {
      "Games/DragonMicroQuest/DragonMicroQuest.py":script,
      "Makefile":make,
      "README.port.md":(
          "# Dragon Micro Quest: real original Thumby game\n\n"
          "Copy Games/DragonMicroQuest/DragonMicroQuest.py to the same "
          "folder on a Thumby through the official Code Editor. "
          "This is genuine on-device MicroPython for the Thumby 72x40 "
          "monochrome LCD, piezo, four-way input, A/B shield and dash, "
          "16-crystal campaign, health and replay. Never claims Thumby "
          "Color API compatibility. Its Python core can be host-simulated. "
          "Generated SOURCE is not a flashed, hardware-verified game. "
          "Makefile check only syntax-compiles on the host; deploy is a "
          "non-mutating instruction. No USB device access without consent.\n"
      ),
      "dragon-micro-hardware.json":(
          '{"schema":"skeleton.ai.dragon.thumby.v1",'
          '"screen":{"width":72,"height":40,"bits_per_pixel":1},'
          '"frame_rate_cap":30,"gameplay_crystals":16,'
          '"runtime":"on_device_micropython",'
          '"device_tested":false,"usb_flash_performed":false}\n'
      ),
    }
