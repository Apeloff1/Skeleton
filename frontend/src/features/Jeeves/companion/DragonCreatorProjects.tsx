import React,{useEffect,useRef,useState} from 'react';
import {Platform,Pressable,StyleSheet,Text,View} from 'react-native';
import * as Crypto from 'expo-crypto';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import {API_BASE} from '../../../utils/apiBase';
import {authHeaders,getAuthToken,getAuthEpoch,initializeStoredToken,subscribeAuthChanges} from '../../../auth/gameforgeAuth';
import {CREATOR_MAX_BYTES,canonicalCreatorJSON,creatorBytes,normalizeCreatorDocument,
  normalizeCreatorSummaries,normalizeCreatorHistory,verifyCreatorProject,parseCreatorExport,
  createCreatorMutation,type CreatorProjectDocument,type CreatorProject,type CreatorProjectSummary,
  type CreatorRevision,type CreatorMutation} from '../../../product/dragonCreatorProject';

const ROOT = API_BASE+'/api/dragon-academy/native/production/projects';
const hash = (text:string) => Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256,text);
type Fence = {signal:AbortSignal; current:()=>boolean; headers:Record<string,string>};
type Replacement = {document:CreatorProjectDocument;head:CreatorProject|null;baseline:string|null;label:string};
class ProjectError extends Error {constructor(message:string,readonly status=0){super(message);}}
function safeMessage(data:unknown,status:number):string {
  if(status===409)return 'A newer revision exists. Your draft is preserved. Reopen the saved project or save this draft as a copy.';
  if(status===401||status===403)return 'Sign in with permission to use creator projects.';
  if(status===404)return 'This project or revision is no longer available to this account.';
  if(status===413)return 'The creator document exceeds the project size limit.';
  if(status===422||status===400)return 'Project controls could not be saved. Keep your draft and check its fields.';
  return 'Project storage did not confirm the request. Keep your draft and retry.';
}
async function boundedText(response:Response,limit:number):Promise<string>{
  const declared=response.headers.get('content-length');
  if(declared&&(!/^\d+$/.test(declared)||Number(declared)>limit))throw new ProjectError('Project response exceeds its size limit.');
  if(!response.body?.getReader){const value=await response.text();if(creatorBytes(value)>limit)throw new ProjectError('Project response exceeds its size limit.');return value;}
  const reader=response.body.getReader();const decoder=new TextDecoder('utf-8',{fatal:true});let bytes=0,result='';
  try{while(true){const next=await reader.read();if(next.done)break;bytes+=next.value.byteLength;
    if(bytes>limit)throw new ProjectError('Project response exceeds its size limit.');result+=decoder.decode(next.value,{stream:true});}
    return result+decoder.decode();
  }finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
}
async function request(path:string,fence:Fence,method='GET',body?:string):Promise<Record<string,unknown>>{
  const response=await fetch(ROOT+path,{method,headers:{...fence.headers,'Content-Type':'application/json'},
    body,signal:fence.signal,credentials:'omit',redirect:'error',cache:'no-store'});
  const raw=await boundedText(response,384*1024);if(!fence.current())throw new ProjectError('Account changed.');
  let data:Record<string,unknown>;try{data=JSON.parse(raw);}catch{throw new ProjectError('Project service returned an unreadable response.');}
  if(!response.ok)throw new ProjectError(safeMessage(data,response.status),response.status);
  if(data?.ok!==true)throw new ProjectError('Project response did not confirm success.');return data;
}
async function downloadJSON(text:string,current:()=>boolean):Promise<void>{
  if(!current())return;
  if(Platform.OS==='web'){
    const url=URL.createObjectURL(new Blob([text],{type:'application/json'}));
    try{if(!current())return;const a=document.createElement('a');a.href=url;a.download='dragon-creator-project.json';
      document.body.appendChild(a);a.click();a.remove();}finally{setTimeout(()=>URL.revokeObjectURL(url),1000);}return;
  }
  if(!FileSystem.cacheDirectory||!await Sharing.isAvailableAsync())throw new ProjectError('Sharing creator JSON is unavailable on this device.');
  if(!current())return;
  const path=FileSystem.cacheDirectory+'dragon-creator-'+Crypto.randomUUID()+'.json';
  try{await FileSystem.writeAsStringAsync(path,text,{encoding:FileSystem.EncodingType.UTF8});
    if(current())await Sharing.shareAsync(path,{mimeType:'application/json',dialogTitle:'Export Dragon creator source'});
  }finally{await FileSystem.deleteAsync(path,{idempotent:true}).catch(()=>{});}
}
export interface DragonCreatorProjectsProps {
  document:CreatorProjectDocument|null;
  onLoad:(document:CreatorProjectDocument)=>void;
  onIdentityChange?:()=>void;
  disabled?:boolean;
  readOnly?:boolean;
}
export default function DragonCreatorProjects({document:currentDocument,onLoad,onIdentityChange,disabled=false,readOnly=false}:DragonCreatorProjectsProps){
  const [items,setItems]=useState<CreatorProjectSummary[]>([]);
  const [head,setHead]=useState<CreatorProject|null>(null);
  const [baseline,setBaseline]=useState<string|null>(null);
  const [history,setHistory]=useState<{id:string;head:number;revisions:CreatorRevision[];before:number|null;next:number|null}|null>(null);
  const [nextOffset,setNextOffset]=useState<number|null>(null);
  const [offset,setOffset]=useState(0);
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');
  const [pending,setPending]=useState<CreatorMutation|null>(null);
  const [replacement,setReplacement]=useState<Replacement|null>(null);
  const [approved,setApproved]=useState(false);
  const mounted=useRef(true);const sequence=useRef(0);const active=useRef<AbortController|null>(null);
  const pendingRef=useRef<CreatorMutation|null>(null);const identityCallback=useRef(onIdentityChange);
  identityCallback.current=onIdentityChange;
  const draftRef=useRef(currentDocument);draftRef.current=currentDocument;
  const normalized=normalizeCreatorDocument(currentDocument);
  const currentCanonical=normalized?canonicalCreatorJSON(normalized):null;
  const dirty=currentCanonical===null?currentDocument!==null:currentCanonical!==baseline;
  useEffect(()=>{setApproved(false);},[currentCanonical]);
  function clearIdentity(){sequence.current++;active.current?.abort();active.current=null;pendingRef.current=null;
    setItems([]);setHead(null);setBaseline(null);setHistory(null);setPending(null);setReplacement(null);
    setApproved(false);setNextOffset(null);setOffset(0);setBusy(false);setError('');setNotice('Account changed. Creator drafts were cleared.');identityCallback.current?.();}
  async function perform(work:(f:Fence)=>Promise<void>){
    if(active.current||disabled)return;const controller=new AbortController();active.current=controller;
    const local=++sequence.current;setBusy(true);setError('');
    const timer=setTimeout(()=>controller.abort(),15000);
    try{await initializeStoredToken();const token=getAuthToken(),epoch=getAuthEpoch();
      const current=()=>mounted.current&&sequence.current===local&&!controller.signal.aborted
        &&getAuthToken()===token&&getAuthEpoch()===epoch;
      if(!token)throw new ProjectError('Sign in to open your creator project library.',401);
      if(!mounted.current||sequence.current!==local||controller.signal.aborted)return;
      await work({signal:controller.signal,current,headers:{...authHeaders()}});
    }catch(e){if(mounted.current&&sequence.current===local){setError(e instanceof ProjectError?e.message:
      controller.signal.aborted?'The request timed out. Your draft is preserved; retry the same save if one is pending.':'The request was interrupted. Your draft is preserved.');}}
    finally{clearTimeout(timer);if(active.current===controller)active.current=null;if(mounted.current&&sequence.current===local)setBusy(false);}
  }
  async function list(f:Fence,page:number){
    const data=await request('?offset='+page+'&limit=32',f);const rows=normalizeCreatorSummaries(data.items);
    if(!rows||!(data.next_offset===null||Number.isSafeInteger(data.next_offset)&&Number(data.next_offset)>page&&Number(data.next_offset)<=63))throw new ProjectError('Project library returned an invalid page.');
    if(f.current()){setItems(rows);setOffset(page);setNextOffset(data.next_offset as number|null);}
  }
  function refresh(page=offset){void perform(async f=>{await list(f,page);if(f.current())setNotice('Saved project library refreshed.');});}
  useEffect(()=>{mounted.current=true;const unsubscribe=subscribeAuthChanges(clearIdentity);refresh(0);
    return()=>{mounted.current=false;sequence.current++;active.current?.abort();unsubscribe();};
    // Initial read and account invalidation do not depend on draft edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[]);
  async function verified(data:Record<string,unknown>,f:Fence,id?:string){
    const project=await verifyCreatorProject(data.project,hash);
    if(!project||id&&project.project_id!==id)throw new ProjectError('Saved project failed its identity or digest check.');
    if(!f.current())return null;return project;
  }
  function apply(next:Replacement){setHead(next.head);setBaseline(next.baseline);setReplacement(null);setApproved(false);
    setHistory(null);onLoad(next.document);setNotice(next.label+' Loaded as editable source; review and build approval must be checked again.');}
  function propose(next:Replacement){
    const draft=normalizeCreatorDocument(draftRef.current);
    const draftCanonical=draft?canonicalCreatorJSON(draft):null;
    if(draftCanonical===null||draftCanonical!==baseline){setReplacement(next);setApproved(false);setNotice('Confirm before replacing the current unsaved draft.');}
    else apply(next);
  }
  function load(id:string){void perform(async f=>{
    const project=await verified(await request('/'+id,f),f,id);if(!project)return;
    propose({document:project.document,head:project,baseline:canonicalCreatorJSON(project.document),label:'Saved revision '+project.version+'.'});
  });}
  function save(copy=false){
    if(readOnly||pendingRef.current||!normalized)return;
    const operation=createCreatorMutation(normalized,Crypto.randomUUID(),copy?null:head);
    pendingRef.current=operation;setPending(operation);void perform(f=>mutate(operation,f));
  }
  async function mutate(operation:CreatorMutation,f:Fence){
    try{
      const project=await verified(await request(operation.projectId?'/'+operation.projectId:'',f,operation.method,operation.body),f,operation.projectId??undefined);
      if(!project)return;
      if(canonicalCreatorJSON(project.document)!==operation.documentCanonical)throw new ProjectError('The confirmed save differs from its original document. Keep the original save identity for recovery.');
      pendingRef.current=null;setPending(null);setHead(project);setBaseline(operation.documentCanonical);setReplacement(null);
      const savedNotice='Saved revision '+project.version+'. '+(project.head_version&&project.head_version>project.version
        ?'A newer head revision exists. Reopen it before editing, or save your draft as a copy.'
        :'Subsequent edits remain an unsaved draft.');
      setNotice(savedNotice);
      try{await list(f,0);}catch{if(f.current())setNotice(savedNotice+' The library refresh failed; refresh it without saving again.');}
    }catch(e){
      if(f.current()&&e instanceof ProjectError&&e.status>=400&&e.status<500){pendingRef.current=null;setPending(null);}
      throw e;
    }
  }
  function showHistory(id:string,before?:number){void perform(async f=>{const query=before===undefined?'':'?before_version='+before+'&limit=32';
    const data=normalizeCreatorHistory(await request('/'+id+'/history'+query,f),id,before);
    if(!data)throw new ProjectError('Revision history failed its identity checks.');
    if(f.current()){setHistory({id,head:data.head_version,revisions:data.revisions,before:before??null,next:data.next_before_version});setNotice('History is read-only. Opening an earlier revision creates an editable draft.');}
  });}
  function loadRevision(version:number,digest:string){if(!history)return;const id=history.id;
    void perform(async f=>{
      const project=await verified(await request('/'+id,f),f,id);if(!project)return;
      const data=await request('/'+id+'/history/'+version,f);
      const document=normalizeCreatorDocument(data.document);
      if(data.project_id!==id||data.version!==version||data.head_version!==project.version||data.approval_restored!==false
        ||data.document_sha256!==digest||!document||await hash(canonicalCreatorJSON(document))!==digest)throw new ProjectError('Historical revision changed or failed its integrity check. Refresh history and retry.');
      if(f.current())propose({document,head:project,baseline:canonicalCreatorJSON(project.document),
        label:'Historical revision '+version+' from head '+project.version+'. Saving creates a new head revision.'});
    });
  }
  function importProject(){void perform(async f=>{
    const picked=await DocumentPicker.getDocumentAsync({type:['application/json','text/plain'],copyToCacheDirectory:true,multiple:false});
    if(!f.current()||picked.canceled)return;const file=picked.assets[0];
    if(!file||typeof file.size==='number'&&file.size>CREATOR_MAX_BYTES)throw new ProjectError('Creator import exceeds 128 KiB.');
    let raw:string;
    if(Platform.OS==='web'){
      if(!file.file||file.file.size>CREATOR_MAX_BYTES)throw new ProjectError('Choose a bounded local creator JSON file.');
      raw=await file.file.text();
    }else{
      try{
        const info=await FileSystem.getInfoAsync(file.uri);if(!info.exists||info.isDirectory||info.size>CREATOR_MAX_BYTES)throw new ProjectError('Creator import exceeds 128 KiB.');
        raw=await FileSystem.readAsStringAsync(file.uri,{encoding:FileSystem.EncodingType.UTF8});
      }finally{
        if(FileSystem.cacheDirectory&&file.uri.startsWith(FileSystem.cacheDirectory))await FileSystem.deleteAsync(file.uri,{idempotent:true}).catch(()=>{});
      }
    }
    const document=await parseCreatorExport(raw,hash);
    if(f.current())propose({document,head:null,baseline:null,label:'Portable project imported as a new unsaved draft.'});
  });}
  function exportProject(){if(!head)return;const id=head.project_id;void perform(async f=>{
    const response=await fetch(ROOT+'/'+id+'/export',{headers:f.headers,signal:f.signal,credentials:'omit',redirect:'error',cache:'no-store'});
    if(!response.ok)throw new ProjectError(safeMessage(null,response.status),response.status);
    if(!/^application\/json(?:;|$)/i.test(response.headers.get('content-type')??''))throw new ProjectError('Creator export has an invalid content type.');
    const raw=await boundedText(response,CREATOR_MAX_BYTES);
    const envelopeDigest=response.headers.get('x-content-sha256');
    if(!envelopeDigest||await hash(raw)!==envelopeDigest)throw new ProjectError('Creator export failed its download digest check.');
    await parseCreatorExport(raw,hash);if(!f.current())return;
    await downloadJSON(raw,f.current);if(f.current())setNotice('Saved source JSON exported. Unsaved edits are not included.');
  });}
  const blocked=busy||disabled;
  const action=(id:string,label:string,onPress:()=>void,off=false)=><Pressable testID={id} accessibilityRole="button" accessibilityLabel={label}
    accessibilityState={{disabled:off}} disabled={off} onPress={onPress} style={[s.button,off&&s.disabled]}><Text style={s.buttonText}>{label}</Text></Pressable>;
  return <View testID="dcp-library" style={s.panel}>
    <Text style={s.title}>Creator project library</Text>
    <Text style={s.note}>Save your design, authored stages and cited brief. Sources are references; importing or reopening a project restores no review, rights, compilation or publishing approval.</Text>
    {readOnly&&<Text style={s.note}>Read-only library. You can inspect and import drafts; saving requires an editor or administrator.</Text>}
    <Text testID="dcp-current" style={s.note}>{head?'Opened: '+head.document.title+' · revision '+head.version:'New unsaved project'}{dirty?' · unsaved draft':''}</Text>
    {!normalized&&<Text testID="dcp-draft-help" style={s.note}>Finish a valid title, seed, target selection and citation JSON. Authored boards must match the stage count. Saving a draft does not require solving its boards.</Text>}
    <View style={s.row}>
      {action('dcp-save',head?'Save new revision':'Save project',()=>save(),blocked||readOnly||!normalized||!!pending)}
      {action('dcp-save-copy','Save a copy',()=>save(true),blocked||readOnly||!normalized||!!pending)}
      {action('dcp-refresh','Refresh library',()=>refresh(0),blocked)}
      {action('dcp-import','Import source JSON',importProject,blocked||!!pending)}
      {action('dcp-export','Export saved JSON',exportProject,blocked||!head)}
    </View>
    {pending&&<View style={s.warning}><Text style={s.note}>This save has not been confirmed. Keep editing if needed; retry sends the original snapshot and save identity.</Text>
      {action('dcp-retry','Retry original save',()=>{if(!readOnly&&pendingRef.current)void perform(f=>mutate(pendingRef.current!,f));},blocked||readOnly)}</View>}
    {replacement&&<View style={s.warning}>
      <Text style={s.note}>{replacement.label} The current draft will be replaced.</Text>
      <Pressable testID="dcp-approve-replace" accessibilityRole="checkbox" accessibilityState={{checked:approved}}
        onPress={()=>setApproved(value=>!value)} style={s.row}><Text style={s.note}>{approved?'☑':'☐'} I approve discarding the current unsaved draft.</Text></Pressable>
      <View style={s.row}>{action('dcp-confirm-replace','Replace draft',()=>apply(replacement),blocked||!approved)}
        {action('dcp-cancel-replace','Keep current draft',()=>{setReplacement(null);setApproved(false);setNotice('Current draft preserved.');},blocked)}</View>
    </View>}
    {!!error&&<Text testID="dcp-error" accessibilityRole="alert" style={s.error}>{error}</Text>}
    {!!notice&&<Text testID="dcp-status" accessibilityLiveRegion="polite" style={s.note}>{notice}</Text>}
    {!items.length&&<Text style={s.note}>No saved projects on this page. Your current form is saved only when you choose Save.</Text>}
    {items.map(item=><View key={item.project_id} style={s.item}><Text style={s.itemTitle}>{item.title}</Text>
      <Text style={s.note}>{item.style.replace(/_/g,' ')} · {item.targets.join(', ')} · revision {item.version}</Text>
      <View style={s.row}>{action('dcp-project-'+item.project_id,'Open '+item.title,()=>load(item.project_id),blocked||!!pending)}
        {action('dcp-history-'+item.project_id,'History: '+item.title,()=>showHistory(item.project_id),blocked)}</View></View>)}
    <View style={s.row}>{offset>0&&action('dcp-previous','Previous projects',()=>refresh(Math.max(0,offset-32)),blocked)}
      {nextOffset!==null&&action('dcp-next','More projects',()=>refresh(nextOffset),blocked)}</View>
    {history&&<View style={s.item}><Text style={s.itemTitle}>Committed revisions · head {history.head}</Text>
      <Text style={s.note}>Opening history changes the draft only. It never rewinds the saved project.</Text>
      {history.revisions.map(r=><View key={r.version} style={s.row}><Text style={s.note}>Revision {r.version} · {r.title}</Text>
        {action('dcp-revision-'+r.version,'Open revision '+r.version,()=>loadRevision(r.version,r.document_sha256),blocked||!!pending)}</View>)}
      <View style={s.row}>
        {history.before!==null&&action('dcp-history-newest','Latest revisions',()=>showHistory(history.id),blocked)}
        {history.next!==null&&action('dcp-history-older','Older revisions',()=>showHistory(history.id,history.next!),blocked)}
      </View>
    </View>}
  </View>;
}
const s=StyleSheet.create({panel:{padding:14,gap:10,borderRadius:14,borderWidth:1,borderColor:'#375451',backgroundColor:'#102421'},
  title:{color:'#e2f5eb',fontSize:18,fontWeight:'700'},note:{color:'#b7cfc7',fontSize:13,lineHeight:20,flexShrink:1},
  row:{flexDirection:'row',flexWrap:'wrap',alignItems:'center',gap:8},button:{paddingHorizontal:12,paddingVertical:10,borderRadius:9,backgroundColor:'#254b40',borderColor:'#54796b',borderWidth:1},
  buttonText:{color:'#eef9f2',fontSize:13,fontWeight:'600'},disabled:{opacity:.42},error:{color:'#fecaca',fontSize:13,lineHeight:20},
  warning:{padding:12,gap:9,borderRadius:10,borderWidth:1,borderColor:'#ac8545',backgroundColor:'#30291b'},
  item:{padding:12,gap:8,borderRadius:10,backgroundColor:'#18322c'},itemTitle:{color:'#e2f5eb',fontSize:14,fontWeight:'600'}});
