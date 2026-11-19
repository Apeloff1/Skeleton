import {watchPose,type WatchSignal} from '../features/Jeeves/companion/dragonWatch';
describe('dragon watch-along animation choreography',()=>{
 const signal=(kind:WatchSignal['kind']):WatchSignal=>({kind,positionMs:5000,durationMs:10000});
 it('maps play to cozy viewing',()=>{const pose=watchPose(signal('play'));expect(pose.snuggle).toBe(true);expect(pose.popcorn).toBe(true);expect(pose.progress).toBe(.5)});
 it('makes note-taking visible without claiming saved memory',()=>{const pose=watchPose(signal('insight'));expect(pose.notebook).toBe(true);expect(pose.mood).toBe('taking-notes')});
 it('shows delight without inventing knowledge',()=>{const pose=watchPose(signal('surprise'));expect(pose.wingWave).toBe(true);expect(pose.heart).toBe(true)});
 it('clamps invalid playback progress',()=>{expect(watchPose({kind:'play',positionMs:Infinity,durationMs:100}).progress).toBe(0);expect(watchPose({kind:'play',positionMs:999,durationMs:100}).progress).toBe(1)});
 it('covers all player signals',()=>{for(const kind of ['play','pause','buffer','seek','frame','caption','insight','surprise','end'] as const){expect(watchPose(signal(kind)).label.length).toBeGreaterThan(0)}});
});
