"""Real combat, shop, consumables, quest and tactical NPC play loop.

Enriches the existing Canvas physics game with concrete runtime state and
commands. Projectiles collide with solid tiles and live enemies. Consumables
spend actual stock. Purchases spend earned coins at the home-base shop.
"""
from __future__ import annotations

_ADVANCED_JS=r"""
const combatRuntime={
  bullets:[], facing:1, potions:1, ammo:12, shotCooldown:0,
  collected:0, defeated:0, questGoal:0, questKills:0,
  shopX:0, firstFrame:true
};
function resetExtendedGame(){
 combatRuntime.bullets.length=0;
 combatRuntime.potions=1;
 combatRuntime.ammo=12;
 combatRuntime.collected=0;
 combatRuntime.defeated=0;
 combatRuntime.shotCooldown=0;
 combatRuntime.questGoal=Math.min(4,state.pickups.length);
 combatRuntime.questKills=Math.min(2,state.enemies.length);
 combatRuntime.shopX=scene.entities.find(e=>e.type==="player")?.x||0;
}
function nearHomeShop(){
 const p=state.player;
 return Math.abs(p.x-combatRuntime.shopX)<TILE*2 &&
        p.grounded && p.alive&&!state.won;
}
function combatShopPurchase(){
 if(!nearHomeShop()||state.coins<5)return;
 state.coins-=5;
 combatRuntime.potions=Math.min(20,combatRuntime.potions+1);
}
function drinkHealingPotion(){
 if(combatRuntime.potions<1||state.lives>=scene.physics.max_lives||
    !state.player.alive)return;
 combatRuntime.potions--;
 state.lives=Math.min(scene.physics.max_lives,state.lives+1);
 state.player.invincible=Math.max(state.player.invincible,.4);
}
function fireGameProjectile(){
 if(!state.player.alive||state.won||combatRuntime.ammo<1||
    combatRuntime.shotCooldown>0)return;
 const p=state.player,dir=combatRuntime.facing;
 combatRuntime.ammo--;
 combatRuntime.shotCooldown=.3;
 combatRuntime.bullets.push({
   x:p.x+p.w/2+dir*12,y:p.y+p.h*.43,
   vx:dir*TILE*13,vy:0,w:8,h:5,ttl:1.5
 });
}
addEventListener("keydown",event=>{
 if(event.repeat||state.paused||!state.player?.alive||state.won)return;
 if(event.code==="KeyF")fireGameProjectile();
 if(event.code==="KeyH")drinkHealingPotion();
 if(event.code==="KeyB")combatShopPurchase();
});
function updateAdvancedCombat(dt){
 const p=state.player;
 if(!p.alive||state.won)return;
 combatRuntime.shotCooldown=Math.max(0,combatRuntime.shotCooldown-dt);
 if(Math.abs(p.vx)>10)combatRuntime.facing=Math.sign(p.vx);
 for(let i=combatRuntime.bullets.length-1;i>=0;i--){
   const bullet=combatRuntime.bullets[i];
   const distance=bullet.vx*dt;
   const steps=Math.max(1,Math.ceil(Math.abs(distance)/(TILE*.25)));
   let removed=false;
   for(let step=0;step<steps&&!removed;step++){
     bullet.x+=distance/steps;
     if(hitsSolid(bullet)){removed=true;break}
     for(const enemy of state.enemies){
       if(!enemy.active||!intersects(bullet,enemy))continue;
       enemy.active=false;state.score+=75;
       combatRuntime.defeated++;
       if(typeof awardCurrency==="function")awardCurrency(2);
       if(typeof gainExperience==="function")gainExperience(20);
       if(typeof playAudio==="function")playAudio("hit");
       removed=true;break;
     }
   }
   bullet.ttl-=dt;
   if(removed||bullet.ttl<=0)combatRuntime.bullets.splice(i,1);
 }
}
function updateGameQuests(){
 const collected=state.pickups.filter(x=>!x.active).length;
 const defeated=state.enemies.filter(x=>!x.active).length;
 if(collected>combatRuntime.collected){
   combatRuntime.collected=collected;
   // Every third collected token converts into ammunition; no artificial
   // currency mutation on redraw or idle frames.
   if(collected%3===0)combatRuntime.ammo=Math.min(30,combatRuntime.ammo+4);
 }
 combatRuntime.defeated=Math.max(combatRuntime.defeated,defeated);
}
function drawAdvancedGameplay(){
 for(const p of combatRuntime.bullets){
   ctx.fillStyle="#fbe6a0";ctx.fillRect(p.x,p.y,p.w,p.h);
 }
}
function drawAdvancedHud(){
 ctx.fillStyle="#daf2ff";ctx.font="14px system-ui";
 ctx.fillText("F: shoot ("+combatRuntime.ammo+")   H: potion ("+
   combatRuntime.potions+")   B: buy potion at spawn (5 gold)",20,117);
 ctx.fillText("Quest: collect "+Math.min(combatRuntime.questGoal,combatRuntime.collected)+
   "/"+combatRuntime.questGoal+"  defeat "+
   Math.min(combatRuntime.questKills,combatRuntime.defeated)+
   "/"+combatRuntime.questKills,20,137);
 if(nearHomeShop()){
   ctx.fillText("SHOP at starting point: press B for health potion",20,157);
 }
}
function advancedQuestReady(){
 return combatRuntime.collected>=combatRuntime.questGoal &&
        combatRuntime.defeated>=combatRuntime.questKills;
}
"""

def integrate_advanced_gameplay(html: str, *, require_quests: bool = False) -> str:
    """Compile actual projectiles, ammo, healing, gold sink and NPC chase."""
    required=(
        "function draw(){",
        "function updateEnemies(dt){",
        "function physicsStep(dt){",
        "function updateGameState(){",
        "function restart(){",
        "function frame(timestamp){",
        "state.score=0;state.lives=scene.physics.max_lives|0;",
        "for(const item of state.pickups) if(item.active){",
        "if(state.player.alive&&intersects(state.player,state.goal)){",
    )
    if any(anchor not in html for anchor in required):
        raise ValueError("gameplay integration requires working Canvas engine")
    html=html.replace("function draw(){",_ADVANCED_JS+"function draw(){",1)
    html=html.replace(
        "  for(const item of state.pickups) if(item.active){",
        "  drawAdvancedGameplay();\n  for(const item of state.pickups) if(item.active){",1
    )
    html=html.replace(
        '  if(state.won||!state.player.alive||state.paused){',
        '  drawAdvancedHud();\n  if(state.won||!state.player.alive||state.paused){',1
    )
    html=html.replace(
        '  if(!p.alive||state.won) return;\n  const desired',
        '  if(!p.alive||state.won) return;\n  const desired'
    ) # Preserve the already working player controller.
    # Call supplemental behavior from the existing fixed-timestep loop,
    # instead of introducing a second variable-delta simulation.
    timing="      updateEnemies(1/60);\n      updateGameState();"
    if timing not in html:
        raise ValueError("cannot locate fixed-step combat update")
    html=html.replace(timing,
        "      updateEnemies(1/60);\n      updateAdvancedCombat(1/60);\n"
        "      updateGameState();\n      updateGameQuests();",1)
    # Enemies now react to the player along the same walkable platform,
    # rather than being permanently confined to predetermined patrol paths.
    patrol="    const next=e.x+e.direction*scene.physics.enemy_speed*TILE*dt;"
    if patrol not in html:
        raise ValueError("missing original enemy movement")
    html=html.replace(patrol,
        """    const p=state.player;
    const horizontal=Math.abs(p.x-e.x);
    const visible=(horizontal<TILE*7 && Math.abs(p.y-e.y)<TILE*1.6);
    if(visible && p.alive){
      e.direction=Math.sign(p.x-e.x)||e.direction;
    }
    const next=e.x+e.direction*scene.physics.enemy_speed*TILE*dt;""",1)
    # Spawn initialization happens before the JS body starts the first frame.
    start="requestAnimationFrame(frame);"
    at=html.rfind(start)
    if at<0:raise ValueError("missing animation startup")
    html=html[:at]+"resetExtendedGame();\n"+html[at:]
    if require_quests:
        old='    if(!locked){state.won=true;'
        if old not in html:raise ValueError("missing original goal lock")
        html=html.replace(old,
            '    if(!locked&&advancedQuestReady()){state.won=true;',1)
    return html
