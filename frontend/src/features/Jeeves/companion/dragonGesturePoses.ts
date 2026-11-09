/** Authored physical signatures for each expressive Dragon beat.
 * Pose deltas are cosmetic offsets; never write them into crawler state.
 */
import type {DragonGesture} from './dragonChoreography';
export type DragonPose=Readonly<{
 lift:number;nod:number;wing:number;tail:number;hat:number;gaze:number;aura:number;
}>;
const pose=(lift=0,nod=0,wing=0,tail=0,hat=0,gaze=0,aura=0):DragonPose=>
 ({lift,nod,wing,tail,hat,gaze,aura});
/** Thirty different physical gesture signatures, reused across 120 phase beats. */
export const DRAGON_POSES:Readonly<Record<DragonGesture,DragonPose>>={
 breathe:pose(-2,0,0,0,0,0,.2),
 tilt:pose(0,14,0,-3,2,4,.1),
 blink:pose(0,-3,0,0,0,0,0),
 peek:pose(-10,-12,0,7,4,6,.3),
 'ear-wiggle':pose(2,-9,0,3,6,-2,.2),
 'tail-wag':pose(1,2,0,14,0,3,.25),
 'wing-flutter':pose(-6,2,16,6,0,0,.55),
 hop:pose(-18,-4,5,8,5,0,.4),
 stretch:pose(-9,-8,11,6,3,2,.2),
 nuzzle:pose(5,12,-3,10,7,-6,.45),
 purr:pose(3,-2,0,8,0,1,.2),
 yawn:pose(-6,8,2,-2,-5,-3,.1),
 sparkle:pose(-4,-6,4,7,3,0,1),
 sneeze:pose(-12,20,11,-9,14,-5,1),
 ponder:pose(1,9,1,0,-2,6,.35),
 'glasses-tap':pose(-1,-6,3,2,7,3,.55),
 'flame-puff':pose(-10,11,9,7,-3,-2,1),
 stargaze:pose(-4,-14,2,2,4,9,.6),
 celebrate:pose(-20,-8,16,18,12,3,1),
 curl:pose(8,3,-7,-10,-3,-4,.05),
 wave:pose(-4,7,12,5,2,2,.5),
 scout:pose(-4,-10,8,5,1,10,.35),
 inspect:pose(3,11,-1,-2,3,-8,.3),
 munch:pose(4,6,0,11,2,1,.45),
 scribble:pose(-1,4,3,-5,3,6,.6),
 listen:pose(-3,-13,1,2,3,-3,.15),
 hide:pose(9,12,-5,-11,-8,-7,.15),
 shiver:pose(4,-12,5,9,-10,2,.7),
 cheer:pose(-16,-10,18,17,11,4,1),
 nestle:pose(9,8,-4,-8,-4,-3,.2),
};
