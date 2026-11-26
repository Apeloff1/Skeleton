/** Stage rituals are decorative, never source events, requests or rewards. */
import type { DragonBeat } from './dragonChoreography';
import type { CompanionPhase } from './dragonCompanionState';
import type { DragonLevelProfile } from './dragonLevelProfile';

const make=(gesture:DragonBeat['gesture'],thought:string):DragonBeat=>({gesture,thought});
const DEN:ReadonlyArray<readonly DragonBeat[]>=[
 [make('peek','A little nose pokes out of the shell.'),make('nestle','Tucking into the eggshell.'),make('yawn','Sleepy squeak.'),make('nuzzle','A tiny hello cuddle.'),make('curl','A miniature cinnamon roll.'),make('purr','Warm little rumble.')],
 [make('tail-wag','My little map fits under the blanket.'),make('peek','A peek from the cozy satchel.'),make('nuzzle','Back home for a cuddle.'),make('stretch','Stretching tiny explorer paws.'),make('wave','A soft returning-home wave.'),make('nestle','Nest and map tucked together.')],
 [make('ponder','A book makes a very cozy pillow.'),make('scribble','Pretending to draw a star chart.'),make('blink','A thoughtful slow blink.'),make('nuzzle','Snuggling against the little codex.'),make('purr','Quiet library purr.'),make('curl','A round scholarly snooze.')],
 [make('wing-flutter','A little wing hug.'),make('stargaze','Watching stars from the nest.'),make('stretch','Folding the explorer wings gently.'),make('nuzzle','A safe little homecoming.'),make('tail-wag','Compass tail wiggle.'),make('nestle','Wrapped softly in a wing.')],
 [make('ponder','The scroll cushions are arranged just so.'),make('scribble','Pretending to label a little chest.'),make('nuzzle','A codex deserves a cuddle too.'),make('curl','Coiled around the archive pillows.'),make('purr','A warm library hum.'),make('nestle','Cozy among the scrolls.')],
 [make('curl','A golden tail wraps around two little chests.'),make('nuzzle','A sleepy hug for the favorite codex.'),make('blink','A proud, very soft golden-eyed blink.'),make('inspect','Pretending to polish a treasure crystal.'),make('scribble','Playfully sorting the tiny scroll pile.'),make('nestle','The mighty little Hoarder snuggles into gold.')],
];
const FIELD:ReadonlyArray<readonly DragonBeat[]>=[
 [make('peek','Tiny curious eyes.'),make('hop','A baby-sized hop.'),make('ear-wiggle','Both little ears perk up.'),make('tail-wag','A happy tiny swish.'),make('listen','Listening carefully.'),make('nuzzle','A little courage cuddle.')],
 [make('scout','Pretending to trace the map.'),make('hop','A little explorer hop.'),make('inspect','Curious eyes on the scenery.'),make('wave','A cheerful tiny wave.'),make('stargaze','Looking for imaginary constellations.'),make('nuzzle','A cozy explorer break.')],
 [make('ponder','A theatrical thinking pose.'),make('scribble','Little pretend notes.'),make('inspect','Reading pose, paws tucked.'),make('blink','Careful and curious.'),make('listen','A tiny scholarly ear twitch.'),make('nuzzle','Cuddle the book.')],
 [make('scout','Compass pose.'),make('wing-flutter','Stretching those explorer wings.'),make('stargaze','Pretending to chart a new path.'),make('inspect','A curious head tilt.'),make('wave','A soft wing greeting.'),make('nuzzle','Time for a wing hug.')],
 [make('inspect','Playfully arranging a scroll.'),make('scribble','Pretend archive labels.'),make('ponder','A thoughtful chest guardian.'),make('tail-wag','Proud little archive tail.'),make('stargaze','A golden glimmer.'),make('nuzzle','A warm archivist snuggle.')],
 [make('inspect','Tiny crystal-polishing pose.'),make('scribble','Playfully sorting two treasure chests.'),make('tail-wag','The hoard has a happy guardian.'),make('cheer','A soft, proud chest puff.'),make('wing-flutter','A golden wing hug.'),make('nuzzle','Even a great Hoarder loves a cuddle.')],
];

const REACTIONS:readonly (readonly string[])[]=[
 ['Mrrp! Tiny nose boop.','A tiny eggshell cuddle.','A happy little squeak!'],
 ['A cheerful explorer nuzzle.','His little satchel wiggles.','A tiny returning-home wave.'],
 ['A bookish little cuddle.','Sleepy scholar eyes sparkle.','A tiny pleased purr.'],
 ['A soft wing hug.','He curls his compass tail.','Warm explorer rumble.'],
 ['A cozy scroll-nest nuzzle.','One proud little archivist purr.','His codex becomes a pillow.'],
 ['The little Hoarder curls around your hand.','Mrrr! A golden wing hug.','A proud snuggly rumble from the treasure den.'],
];

export function evolutionRitual(profile:DragonLevelProfile,phase:CompanionPhase,tick:number,fallback:DragonBeat):DragonBeat {
  // Never suggest pretend capture, distillation or burn in a real burn phase.
  if(phase==='burning'||phase==='distilling')return fallback;
  const cozy=phase==='sleeping'||phase==='snuggle';
  const list=(cozy?DEN:FIELD)[profile.stage];
  const within=Math.max(0,Math.min(9,profile.level-profile.stage*10-1));
  const available=Math.min(list.length,2+Math.floor(within/2));
  const index=Math.abs(Math.floor(Number.isFinite(tick)?tick:0));
  if(!cozy&&index%3!==0)return fallback;
  return list[(cozy?index:Math.floor(index/3))%available];
}
export function evolutionPetReaction(profile:DragonLevelProfile,count:number):string {
  const list=REACTIONS[profile.stage];
  const index=Math.max(0,Math.floor(Number.isFinite(count)?count-1:0));
  return list[index%list.length];
}
