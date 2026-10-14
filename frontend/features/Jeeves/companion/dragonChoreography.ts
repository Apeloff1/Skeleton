/**
 * Dragon life director. Decorative beats are never crawler actions or evidence.
 *
 * Twelve hand-authored expressive beats for each of ten existing companion
 * phases (120 moments). All variation is deterministic in local UI time;
 * authoritative crawler state continues to own progress, approval and labels.
 */
import type {CompanionPhase, DragonCompanionState} from './dragonCompanion';
import type {CompanionMotion} from './dragonPreferences';

export type DragonGesture =
  | 'breathe'|'tilt'|'blink'|'peek'|'ear-wiggle'|'tail-wag'
  | 'wing-flutter'|'hop'|'stretch'|'nuzzle'|'purr'|'yawn'
  | 'sparkle'|'sneeze'|'ponder'|'glasses-tap'|'flame-puff'
  | 'stargaze'|'celebrate'|'curl'|'wave'|'scout'|'inspect'
  | 'munch'|'scribble'|'listen'|'hide'|'shiver'|'cheer'|'nestle';
export type DragonBeat = Readonly<{gesture:DragonGesture;thought:string}>;
const beat=(gesture:DragonGesture,thought:string):DragonBeat=>({gesture,thought});

/** These are lightweight visual scripts, not telemetry, actions or achievements. */
export const DRAGON_BEATS:Readonly<Record<CompanionPhase,readonly DragonBeat[]>>={
 snuggle:[
  beat('breathe','Tiny snores and a warm egg.'),beat('peek','Is it adventure time?'),
  beat('tail-wag','The tail has opinions.'),beat('nuzzle','A cozy little wiggle.'),
  beat('ear-wiggle','He heard you!'),beat('purr','A rumbling kettle of purrs.'),
  beat('blink','A very slow, very big blink.'),beat('curl','Making a perfect cinnamon roll.'),
  beat('stretch','Teeny tiny stretch.'),beat('sparkle','A secret happy sparkle.'),
  beat('yawn','A yawn too big for a dragon.'),beat('nestle','Snug as a dragon in an egg.')],
 listening:[
  beat('listen','Tell me everything!'),beat('ear-wiggle','Both ears are on duty.'),
  beat('tilt','Wait, tell me more.'),beat('blink','Eyes bright and listening.'),
  beat('ponder','Little gears turning.'),beat('tail-wag','A thoughtful tail swish.'),
  beat('peek','Curious about your idea.'),beat('purr','A supportive little purr.'),
  beat('wave','Hello, clever human.'),beat('stargaze','Imagining new worlds.'),
  beat('sparkle','A tiny lightbulb moment.'),beat('nuzzle','Happy to be here.')],
 curious:[
  beat('peek','What is that over there?'),beat('scout','Eyes on the horizon.'),
  beat('tilt','That looks intriguing.'),beat('ear-wiggle','Ears on high alert!'),
  beat('hop','One excited hop.'),beat('tail-wag','A curious little swish.'),
  beat('inspect','Taking a closer look.'),beat('blink','Double-checking the view.'),
  beat('sparkle','A trail of wonder.'),beat('stargaze','How big is this world?'),
  beat('listen','Listening for clues.'),beat('wing-flutter','Almost ready to fly.')],
 launching:[
  beat('wing-flutter','Wings warming up.'),beat('hop','Boing! Ready!'),
  beat('scout','Plotting a little flight.'),beat('tilt','Checking the compass.'),
  beat('tail-wag','Tail steering engaged.'),beat('sparkle','An adventure begins.'),
  beat('stretch','Stretching every wing.'),beat('blink','Goggles? Check.'),
  beat('wave','Be right back!'),beat('cheer','Tiny launch cheer.'),
  beat('peek','One last look at home.'),beat('wing-flutter','Off we flutter!')],
 crawling:[
  beat('scout','Searching the scenery.'),beat('inspect','Looking at the details.'),
  beat('blink','Careful eyes at work.'),beat('listen','Checking what is allowed.'),
  beat('ponder','That needs a closer look.'),beat('tilt','Examining the layout.'),
  beat('ear-wiggle','Picking up a clue.'),beat('tail-wag','A patient little swish.'),
  beat('peek','Peeking behind the corners.'),beat('scribble','Making a mental note.'),
  beat('stargaze','Connecting the dots.'),beat('breathe','Slow and careful breathing.')],
 acquiring:[
  beat('munch','Nibbling on context.'),beat('inspect','Checking the delivery.'),
  beat('blink','Reading carefully.'),beat('peek','Look what arrived!'),
  beat('tail-wag','Happy little tail.'),beat('ponder','What does it mean?'),
  beat('scribble','Marking an interesting bit.'),beat('ear-wiggle','Heard a useful clue.'),
  beat('purr','A satisfied hum.'),beat('hop','A tiny success hop.'),
  beat('sparkle','A small hopeful gleam.'),beat('listen','Still listening for more.')],
 burning:[
  beat('flame-puff','A careful little puff.'),beat('sparkle','Glowing embers swirl.'),
  beat('sneeze','Achoo! Tiny sparks.'),beat('tail-wag','Fanning the embers.'),
  beat('ponder','Keeping the flame steady.'),beat('blink','Eyes on the sparks.'),
  beat('wing-flutter','A breeze for the embers.'),beat('flame-puff','Another careful flame.'),
  beat('scribble','Shaping what we learned.'),beat('inspect','Watching the transformation.'),
  beat('breathe','A deep ember breath.'),beat('sparkle','Warm light, little stars.')],
 distilling:[
  beat('glasses-tap','Adjusting the taped glasses.'),beat('ponder','Thinking very hard.'),
  beat('scribble','Organizing the clues.'),beat('inspect','Inspecting the evidence.'),
  beat('blink','Squint. Read. Repeat.'),beat('glasses-tap','The bridge tape holds!'),
  beat('tail-wag','A very scholarly swish.'),beat('ear-wiggle','Listening for contradictions.'),
  beat('stargaze','Finding a pattern.'),beat('sparkle','A little connection clicks.'),
  beat('ponder','Still just a hypothesis.'),beat('breathe','Focused little breaths.')],
 celebrating:[
  beat('cheer','A little victory dance!'),beat('hop','Boing boing!'),
  beat('wing-flutter','A happy wing dance.'),beat('sparkle','Confetti of stars!'),
  beat('tail-wag','Maximum happy tail.'),beat('wave','A wave for you!'),
  beat('purr','Proud little happy purr.'),beat('nuzzle','A celebratory snuggle.'),
  beat('stargaze','Looking toward our next adventure.'),beat('blink','A sparkling wink.'),
  beat('stretch','Big stretch, tiny dragon.'),beat('nestle','Back to our cozy egg.')],
 sleeping:[
  beat('curl','Curled up and safe.'),beat('breathe','A tiny sleeping breath.'),
  beat('yawn','One last soft yawn.'),beat('nestle','The blanket is perfect.'),
  beat('purr','Sleepy little rumble.'),beat('blink','Eyelids are getting heavy.'),
  beat('tail-wag','Sleepy tail twitch.'),beat('stargaze','Dreaming of distant stars.'),
  beat('nuzzle','Nuzzling the blanket.'),beat('ear-wiggle','A dreamy ear twitch.'),
  beat('peek','Just one sleepy peek.'),beat('curl','Snoozing inside the shell.')],
};
export const DRAGON_CHOREOGRAPHY_COUNT=Object.values(DRAGON_BEATS).reduce((n,beats)=>n+beats.length,0);
export interface DragonDirection {
 beat:DragonBeat;
 tempoMs:number;
 particle:'hearts'|'stars'|'embers'|'thoughts'|'wind'|'none';
 tint:string;
 amplitude:number;
 animated:boolean;
 layers:number;
}
/** Bounded motion budget: at most four decorative particles, no render loops. */
export function directDragon(
 state:Pick<DragonCompanionState,'phase'|'fire'|'embers'|'glasses'|'snuggly'>,
 motion:CompanionMotion,
 tick=0,
 reducedMotion=false,
):DragonDirection{
 const scripts=DRAGON_BEATS[state.phase]??DRAGON_BEATS.snuggle;
 const index=Number.isFinite(tick)?Math.abs(Math.floor(tick))%scripts.length:0;
 const animated=!reducedMotion&&motion!=='off';
 const gentle=motion==='gentle';
 const phase=state.phase;
 return {
  beat:scripts[index],
  tempoMs:phase==='sleeping'||phase==='snuggle'?4800:phase==='burning'?2400:3300,
  particle:state.fire?'embers':phase==='celebrating'?'stars':state.snuggly?'hearts':
   phase==='launching'?'wind':state.glasses?'thoughts':phase==='curious'?'stars':'none',
  tint:state.fire?'#fb923c':state.glasses?'#a5b4fc':state.snuggly?'#f9a8d4':'#86efac',
  amplitude:animated?(gentle?.36:1):0,
  animated,
  layers:animated?(gentle?2:4):0,
 };
}
