import React,{useCallback,useEffect,useRef,useState} from 'react';
import {AppState,ActivityIndicator,Switch,Text,TextInput,TouchableOpacity,View} from 'react-native';
import {getAuthToken} from '../../auth/gameforgeAuth';
import {getDragonDeepCatalog,queryDragonWiki,configureDragonArchive,configureLegacyTreasuryArchive,eraseCrawl,crawlRequestKey,
 type DragonDeepCatalog,type DragonDeepRecord,type DragonWikiCatalog,type DragonWikiSearchOptions} from '../../product/crawlerClient';
import s,{colors} from './CrawlerWorkspace.styles';
type Props={revision:string;canWrite:boolean;disabled:boolean;onWindow:(ids?:string[],query?:string)=>void;onChanged:()=>void};
function Button({label,action,disabled}:{label:string;action:()=>void;disabled?:boolean}){
 return <TouchableOpacity accessibilityRole="button" accessibilityState={{disabled:!!disabled}} disabled={disabled}
 style={[s.button,disabled&&s.disabled]} onPress={action}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
}
const field={backgroundColor:colors.bg,borderWidth:1,borderColor:colors.edge,borderRadius:9,padding:10,color:colors.text};
export default function DragonDeepArchivePanel({revision,canWrite,disabled,onWindow,onChanged}:Props){
 const [catalog,setCatalog]=useState<DragonDeepCatalog|null>(null),[wiki,setWiki]=useState<DragonWikiCatalog|null>(null);
 const [query,setQuery]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [mode,setMode]=useState<'historic'|'current'>('historic'),[managed,setManaged]=useState<string|null>(null);
 const [sort,setSort]=useState<DragonWikiSearchOptions['order']>('relevance'),[requireAll,setRequireAll]=useState(false),[partition,setPartition]=useState('');
 const [rights,setRights]=useState(false),[erase,setErase]=useState(''),[days,setDays]=useState('30');
 const owner=useRef(getAuthToken()),epoch=useRef(0),pending=useRef<AbortController|null>(null),timer=useRef<ReturnType<typeof setTimeout>|null>(null);
 const invalidate=useCallback(()=>{epoch.current++;pending.current?.abort();pending.current=null;if(timer.current!==null)clearTimeout(timer.current);timer.current=null;},[]);
 const clear=useCallback(()=>{invalidate();setCatalog(null);setWiki(null);setManaged(null);setRights(false);setErase('');setBusy(false);setError('');},[invalidate]);
 useEffect(()=>{clear();return invalidate;},[revision,clear,invalidate]);
 useEffect(()=>{const sub=AppState.addEventListener('change',state=>{if(state!=='active')clear();});
 const tick=setInterval(()=>{if(owner.current!==getAuthToken()){owner.current=getAuthToken();clear();}},1000);
 return()=>{sub.remove();clearInterval(tick);};},[clear]);
 function start(){invalidate();owner.current=getAuthToken();const ctrl=new AbortController(),gen=epoch.current,token=owner.current;
 pending.current=ctrl;setBusy(true);setError('');return {ctrl,valid:()=>!ctrl.signal.aborted&&gen===epoch.current&&getAuthToken()===token,
 finish:()=>{if(gen===epoch.current){pending.current=null;setBusy(false);}}};}
 async function load(cursor?:string){if(disabled||busy)return;const run=start();setCatalog(null);setWiki(null);setManaged(null);setRights(false);setErase('');
 try{const page=await getDragonDeepCatalog(cursor,run.ctrl.signal);if(run.valid())setCatalog(page);}
 catch(e){if(run.valid())setError(e instanceof Error?e.message:'Catalogue unavailable.');}finally{run.finish();}}
 async function search(cursor?:string){if(disabled||busy||!query.trim())return;const run=start();setWiki(null);const started=performance.now();
 try{const part=partition.trim()===''?null:Number(partition);
 if(mode==='historic'&&part!==null&&(!Number.isInteger(part)||part<0||part>1023)){setError('Choose a partition from 0 to 1023.');return;}
 const filters:DragonWikiSearchOptions=mode==='historic'?{partition:part,order:sort,match:requireAll?'all':'any'}:{partition:null,order:'relevance',match:'any'};
 const result=await queryDragonWiki(query,mode,cursor,run.ctrl.signal,filters);if(!run.valid())return;
 const ttl=(result.valid_until-result.as_of_unix)*1000-(performance.now()-started);
 if(ttl<=0){setError('Wiki citation permission expired.');return;}setWiki(result);
 timer.current=setTimeout(()=>{if(run.valid())setWiki(null);},ttl);
 }catch(e){if(run.valid())setError(e instanceof Error?e.message:'Wiki lookup unavailable.');}finally{run.finish();}}
 async function command(row:DragonDeepRecord,action:'grant'|'revoke'|'erase'){
 if(disabled||busy||action!=='revoke'&&!canWrite||action==='grant'&&!rights||action==='erase'&&erase!=='ERASE')return;
 const n=Number(days);if(!Number.isInteger(n)||n<1||n>30){setError('Choose 1–30 days.');return;}
 const run=start();setWiki(null);const body={expected_version:row.version,idempotency_key:crawlRequestKey('deep-'+action)};
 try{if(action==='erase')await eraseCrawl(row.session_id,body,run.ctrl.signal);
 else{const request={...body,enabled:action==='grant',days:n,archive_rights_acknowledged:action==='grant'&&rights};
 if(row.legacy_runtime!==false||action==='revoke')await configureLegacyTreasuryArchive(row.session_id,request,run.ctrl.signal);
 else await configureDragonArchive(row.session_id,request,run.ctrl.signal);}
 if(run.valid()){setCatalog(null);setManaged(null);setRights(false);setErase('');onWindow(undefined);onChanged();}
 }catch(e){if(run.valid())setError(e instanceof Error?e.message:'Refresh before retrying.');}finally{run.finish();}}
 const locked=disabled||busy||owner.current!==getAuthToken();
 return <View style={s.check}>
 <Text style={s.heading}>Deep archive · HOAG Wiki nucleus</Text>
 <Text style={s.small}>1,024 reservation partitions × 1,024 expeditions. Nominal capacity, not measured storage. Original records remain in canonical custody; historical citations cannot authorize inference or knowledge promotion.</Text>
 <Button label="Load first deep catalogue page" disabled={locked} action={()=>void load()}/>
 {catalog&&<><Text style={s.small}>{catalog.records.length} records on this page; storage capacity not independently verified.</Text>
 {catalog.records.map(row=><View key={row.session_id} style={s.check}>
  <Text selectable style={s.label}>{row.session_id}</Text>
  <Text style={s.small}>{row.integrity_held?'Integrity held':'Partition '+row.archive?.partition+' · '+(row.archive?.released?'archived':'transition pending')} · {row.grant_recorded?'recorded history grant':'no live recorded grant'} · {row.index_recorded?'index recorded':'index pending'}</Text>
  <Button label="Manage retained expedition" disabled={locked} action={()=>{setManaged(managed===row.session_id?null:row.session_id);setRights(false);setErase('');}}/>
  {managed===row.session_id&&<>
   {canWrite&&!row.integrity_held&&<><TextInput value={days} onChangeText={setDays} maxLength={2} keyboardType="number-pad" style={field} accessibilityLabel="Historical use days"/>
    <View style={s.row}><Switch value={rights} onValueChange={setRights} accessibilityLabel="Confirm historical source rights"/><Text style={[s.small,s.grow]}>Authorize only retained historical use.</Text></View>
    <Button label="Authorize finite archive use" disabled={locked||!rights} action={()=>void command(row,'grant')}/></>}
   {!row.integrity_held&&<Button label="Withdraw historical use" disabled={locked} action={()=>void command(row,'revoke')}/>}
   {canWrite&&<><TextInput value={erase} onChangeText={setErase} maxLength={5} style={field} autoCapitalize="characters" accessibilityLabel="Type ERASE to delete retained record"/>
   <Button label="Erase retained expedition" disabled={locked||erase!=='ERASE'} action={()=>void command(row,'erase')}/></>}
  </>}
 </View>)}
 <Button label="Next catalogue page" disabled={locked||!catalog.next_cursor} action={()=>void load(catalog.next_cursor??undefined)}/></>}
 <Text style={s.label}>Search Wiki citation pointers</Text>
 <TextInput value={query} onChangeText={value=>{invalidate();setBusy(false);setWiki(null);setQuery(value);}} style={field} maxLength={256} editable={!locked} accessibilityLabel="HOAG Wiki search query"/>
 <View style={s.row}><Button label="Historical index" disabled={locked||mode==='historic'} action={()=>{setMode('historic');setWiki(null);}}/>
 <Button label="Current AI evidence" disabled={locked||mode==='current'} action={()=>{setMode('current');setWiki(null);}}/></View>
 {mode==='historic'&&<View style={s.check}>
 <Text style={s.small}>Index order: {sort==='relevance'?'relevance within candidate pages':sort==='archive_newest'?'newest archive admission first':'oldest archive admission first'}</Text>
 <View style={s.row}>{(['relevance','archive_newest','archive_oldest'] as const).map(value=><Button key={value} label={value.replaceAll('_',' ')} disabled={locked||sort===value} action={()=>{setSort(value);setWiki(null);}}/>)}</View>
 <View style={s.row}><Switch value={requireAll} onValueChange={value=>{setRequireAll(value);setWiki(null);}} disabled={locked} accessibilityLabel="Require all lexical terms"/><Text style={[s.small,s.grow]}>Require every normalized query term in an exact source</Text></View>
 <TextInput value={partition} onChangeText={value=>{setPartition(value);setWiki(null);}} maxLength={4} keyboardType="number-pad" editable={!locked} style={field} placeholder="All partitions" accessibilityLabel="Optional archive partition number"/>
 </View>}
 <Button label="Search selected evidence plane" disabled={locked||!query.trim()} action={()=>void search()}/>
 {wiki&&<View style={s.check}><Text style={s.small}>{wiki.pointers.length} request-local {wiki.mode} citations. No prose persisted into Wiki; no knowledge promotion.</Text>
 {wiki.pointers.map(hit=><Text selectable key={hit.citation} style={s.small}>{hit.citation}{hit.matched_terms?' · '+hit.matched_terms+' terms':''}{hit.partition!==undefined?' · partition '+hit.partition:''}{hit.archived_at!==undefined?' · archived '+new Date(hit.archived_at*1000).toLocaleDateString():''}</Text>)}
 {wiki.mode==='historic'&&<Button label="Inspect matching historical passages" disabled={locked||!wiki.pointers.length}
 action={()=>onWindow([...new Set(wiki.pointers.map(x=>x.session_id))].sort(),query)}/>}
 <Button label="Next indexed page" disabled={locked||!wiki.next_cursor} action={()=>void search(wiki.next_cursor??undefined)}/></View>}
 {busy&&<ActivityIndicator color={colors.accent}/>}
 {!!error&&<Text style={s.error} accessibilityLiveRegion="polite">{error}</Text>}
 </View>;
}
