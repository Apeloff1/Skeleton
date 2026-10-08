"""Connect progression/economy/quest systems to the real HTML5 game loop.

This upgrades an already compiled original game; no downloaded scripting is
executed. The injected state mutates only the client-side play session.
"""
from __future__ import annotations

_PROGRESS=r"""
function gainExperience(amount){
  state.xp+=amount;
  const threshold=100*state.level;
  while(state.xp>=100*state.level && state.level<25){
    state.xp-=100*state.level;state.level++;
    state.skillPoints++;
    state.player.invincible=Math.max(state.player.invincible,.3);
  }
}
function awardCurrency(amount){state.coins+=amount}
function remainingObjectives(){
  return state.pickups.filter(p=>p.active).length+
         state.enemies.filter(e=>e.active).length;
}
function canUpgrade(){
  return state.skillPoints>0 && state.coins>=5;
}
addEventListener("keydown",event=>{
  if(state.paused||!state.player?.alive)return;
  if(event.code==="KeyL"&&!event.repeat&&canUpgrade()){
    state.skillPoints--;state.coins-=5;
    scene.physics.move_speed=Math.min(10,scene.physics.move_speed+.5);
  }
  if(event.code==="KeyI"&&!event.repeat){
    state.showInventory=!state.showInventory;
  }
});
"""
def integrate_live_progression(html:str)->str:
    """Make quests, coins, experience and upgrade choices actually playable."""
    required=(
        "function draw(){",
        "state.score=0;state.lives=scene.physics.max_lives|0;",
        'item.active=false;state.score+=10;playAudio("pickup");',
        'e.active=false;state.score+=50;playAudio("hit");',
        "state.won=true;state.score+=250",
    )
    for anchor in required:
        if anchor not in html:
            raise ValueError("unrecognized original Canvas game runtime: "+anchor)
    html=html.replace("function draw(){",_PROGRESS+"function draw(){",1)
    html=html.replace(
        "state.score=0;state.lives=scene.physics.max_lives|0;",
        "state.score=0;state.lives=scene.physics.max_lives|0;"
        "state.coins=0;state.xp=0;state.level=1;state.skillPoints=0;"
        "state.showInventory=false;",
        1,
    )
    html=html.replace(
        'item.active=false;state.score+=10;playAudio("pickup");',
        'item.active=false;state.score+=10;playAudio("pickup");'
        'awardCurrency(1);gainExperience(5);',
    )
    html=html.replace(
        'e.active=false;state.score+=50;playAudio("hit");',
        'e.active=false;state.score+=50;playAudio("hit");'
        'awardCurrency(2);gainExperience(25);',
    )
    html=html.replace(
        'e.active=false; state.score+=100;',
        'e.active=false; state.score+=100;awardCurrency(3);gainExperience(30);',
    )
    html=html.replace(
        'state.won=true;state.score+=250',
        'state.won=true;state.score+=250;gainExperience(75)',
    )
    html=html.replace(
        'ctx.fillText("Score: "+state.score+"    Lives: "+state.lives,20,32);',
        'ctx.fillText("Score: "+state.score+"  Lives: "+state.lives+'
        '"  Gold: "+state.coins+"  Level: "+state.level+"  XP: "+state.xp,20,32);'
        'ctx.font="13px system-ui";'
        'ctx.fillText("Quest: clear threats and collect tokens ("+remainingObjectives()+'
        '" objectives)  |  L: upgrade  I: inventory",20,96);',
    )
    html=html.replace(
        '  if(state.won||!state.player.alive||state.paused){',
        '  if(state.showInventory){'
        '    ctx.fillStyle="rgba(9,20,38,.92)";ctx.fillRect(20,112,355,120);'
        '    ctx.fillStyle="#fff";ctx.font="16px system-ui";'
        '    ctx.fillText("Inventory / Upgrades",36,143);'
        '    ctx.fillText("Gold: "+state.coins+"    Available skill points: "+'
        'state.skillPoints,36,170);'
        '    ctx.fillText("Press L: +move speed, costs 5 gold +1 skill point",36,195);'
        '  }'
        '  if(state.won||!state.player.alive||state.paused){',
    )
    return html
