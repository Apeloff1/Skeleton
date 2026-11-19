import {replayDragonPages} from '../features/Jeeves/companion/dragonReplay';
import {reduceDragonJournal,EMPTY_COMPANION_JOURNAL,type WireDragonEvent} from '../features/Jeeves/companion/dragonJournal';
import {canSuggestCrawl,DEFAULT_COMPANION_PREFERENCES} from '../features/Jeeves/companion/dragonPreferences';
const event=(sequence:number,kind:WireDragonEvent['kind'],payload:Record<string,unknown>={}):WireDragonEvent=>({schema:'skeleton.ai.dragon_crawl.event.v1',event_id:'id-'+sequence,sequence,kind,url:'https://example.org/a',at:sequence,payload});
describe('dragon live replay contract',()=>{
 it('rejects false memory completion',()=>{
  let s=reduceDragonJournal(EMPTY_COMPANION_JOURNAL,event(1,'acquisition_accepted'));
  s=reduceDragonJournal(s,event(2,'burn_started'));
  const bad=reduceDragonJournal(s,event(3,'burn_complete'));
  expect(bad.indexed).toBe(0);expect(bad.warnings).toContain('Completion rejected: durable indexing receipt missing');
 });
 it('allows completed burn with durable receipt',()=>{
  let s=reduceDragonJournal(EMPTY_COMPANION_JOURNAL,event(1,'acquisition_accepted'));
  s=reduceDragonJournal(s,event(2,'burn_started'));
  s=reduceDragonJournal(s,event(3,'burn_complete',{persisted:true}));
  expect(s.indexed).toBe(1);expect(s.state.phase).toBe('distilling');
 });
 it('replays bounded pages',async()=>{
  const pages=[[event(1,'frontier_discovered')],[event(2,'policy_rejected')]];
  const result=await replayDragonPages(async cursor=>({events:pages[cursor?1:0],nextCursor:cursor?null:'next',hasMore:!cursor}));
  expect(result.complete).toBe(true);expect(result.journal.rejected).toBe(1);
 });
 it('defaults to private non-autonomous mode',()=>expect(canSuggestCrawl(DEFAULT_COMPANION_PREFERENCES,true)).toBe(false));
});
