/** Original Dragon Maze Forge: constructive completion, true branching decisions.
 *
 * Every move is independently re-simulated by the authenticated backend;
 * the client cannot mint secrets, bypass passage gates, or certify itself.
 * Grid cells visualize actual world nodes, NOT a static "random maze" sketch.
 */
import React from 'react';
import {
  ActivityIndicator,Platform,SafeAreaView,ScrollView,StyleSheet,Text,
  TextInput,TouchableOpacity,View,
} from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import StudioLoginGate,{useStudioAuth} from '../src/auth/StudioLoginGate';
import {authHeaders} from '../src/auth/gameforgeAuth';
import {API_BASE} from '../src/utils/apiBase';

const API=(API_BASE||'').replace(/\/$/,'')+
  '/api/dragon-academy/native/production/routes/maze';
type Weather='clear'|'rain'|'windy'|'storm'|'snow'|'high_tide';
type Challenge='gentle'|'balanced'|'challenging'|'spicy';
type RouteOption={
  edge:string;to:string;mode:string;shape:string[];
  time_minutes:number;waiting_minutes:number;
  price:number;fatigue:number;access:string;available:boolean;
};
type Player={
  world_position:string;goal:string;completed:boolean;
  played_edges:string[];visited_places:string[];
  known_tokens:string[];remaining_cash:number;
  remaining_energy:number;elapsed_minutes:number;
  options:RouteOption[];
};
type Certificate={
  world_digest:string;dimensions:[number,number];
  start:string;goal:string;backbone:string[];
  backbone_locations:string[];backbone_moves:number;
  real_dead_ends:string[];return_edges:string[];
  all_climates_backbone_verified:string[];
  location_recovery_count:number;certificate_digest:string;
  doubleback_witnesses:string[][];impractical_witnesses:string[][];
  scenic_witnesses:string[][];secret_witnesses:string[][];
  optional_shapes:string[];
  guarantee_scope:string;
};
type Preview={
  ok:boolean;source_only:boolean;
  completion:{status:string;rooms:number;verified_winning_witnesses:number};
  certificate:Certificate;player:Player;
};

const climates:readonly Weather[]=['clear','rain','windy','storm','snow','high_tide'];
const profiles:readonly Challenge[]=['gentle','balanced','challenging','spicy'];
const label=(id:string)=>id.replace(/_/g,' ');
async function post<T>(endpoint:string,body:object):Promise<T>{
  const response=await fetch(API+endpoint,{
    method:'POST',cache:'no-store',
    headers:authHeaders({'Content-Type':'application/json'}),
    body:JSON.stringify(body),
  });
  if(!response.ok)throw new Error(response.status===403
    ? 'Only an authorized creator may perform this action.'
    : response.status===422
    ? 'This maze path or construction failed the bounded completion checks.'
    : 'Original maze service unavailable.');
  return response.json() as Promise<T>;
}
async function saveZip(blob:Blob){
  if(blob.size===0||blob.size>1_500_000)
    throw new Error('Native original maze source exceeded ZIP budget.');
  if(Platform.OS==='web'){
    const uri=URL.createObjectURL(blob);
    try{
      const tag=document.createElement('a');
      tag.href=uri;tag.download='dragon-original-completable-maze.zip';
      document.body.appendChild(tag);tag.click();tag.remove();
    }finally{setTimeout(()=>URL.revokeObjectURL(uri),15_000);}
    return;
  }
  if(!FileSystem.documentDirectory)throw new Error('Device document storage unavailable.');
  const value=await new Promise<string>((resolve,reject)=>{
    const reader=new FileReader();
    reader.onerror=()=>reject(new Error('Could not encode approved maze source archive.'));
    reader.onload=()=>{
      const text=reader.result;
      if(typeof text!=='string'||!text.includes(','))
        return reject(new Error('Approved ZIP did not encode properly.'));
      resolve(text.slice(text.indexOf(',')+1));
    };
    reader.readAsDataURL(blob);
  });
  const local=FileSystem.documentDirectory+'dragon-original-completable-maze.zip';
  await FileSystem.writeAsStringAsync(local,value,{
    encoding:FileSystem.EncodingType.Base64,
  });
  if(await Sharing.isAvailableAsync())
    await Sharing.shareAsync(local,{
      mimeType:'application/zip',dialogTitle:'Original Dragon Maze Native C99 Source',
    });
}
function Editor(){
  const {role}=useStudioAuth();
  const isEditor=role==='admin'||role==='editor';
  const [seed,setSeed]=React.useState('1977');
  const [width,setWidth]=React.useState(6);
  const [height,setHeight]=React.useState(6);
  const [weather,setWeather]=React.useState<Weather>('clear');
  const [challenge,setChallenge]=React.useState<Challenge>('balanced');
  const [scenic,setScenic]=React.useState(65);
  const [detours,setDetours]=React.useState(70);
  const [secrets,setSecrets]=React.useState(2);
  const [review,setReview]=React.useState<Preview|null>(null);
  const [player,setPlayer]=React.useState<Player|null>(null);
  const [moves,setMoves]=React.useState<string[]>([]);
  const [guided,setGuided]=React.useState<string[]|null>(null);
  const [rescue,setRescue]=React.useState<{
    reachable_now:boolean;next_move:string|null;
    remaining_actions:number;reset_required:boolean;
    proof:string;
  }|null>(null);
  const [approved,setApproved]=React.useState(false);
  const [attested,setAttested]=React.useState(false);
  const [busy,setBusy]=React.useState(false);
  const [notice,setNotice]=React.useState('');
  const [error,setError]=React.useState('');
  const epoch=React.useRef(0);
  const numeric=Number(seed);
  const validSeed=/^\d{1,10}$/.test(seed)&&Number.isSafeInteger(numeric)&&
    numeric>=0&&numeric<=0xffffffff;
  const settings={
    width,height,seed:numeric,weather,challenge,
    scenic_density:scenic,detour_density:detours,
    secret_count:secrets,
  };
  const reset=()=>{
    epoch.current++;
    setBusy(false);setReview(null);setPlayer(null);setMoves([]);
    setGuided(null);setRescue(null);
    setApproved(false);setNotice('');setError('');
  };
  const create=async()=>{
    if(!isEditor||busy||!validSeed)return;
    const ticket=++epoch.current;
    setBusy(true);setReview(null);setPlayer(null);setMoves([]);
    setNotice('');setError('');
    try{
      const result=await post<Preview>('/preview',settings);
      const proof=result.certificate;
      if(!result.ok||!result.source_only||!proof||
         result.completion?.status!=='constructively_complete'||
         proof.location_recovery_count!==width*height||
         proof.all_climates_backbone_verified.length!==6||
         proof.backbone.length<4||
         proof.world_digest.length!==64)
        throw new Error('Maze certificate is incomplete or mismatched.');
      if(ticket===epoch.current){
        setReview(result);setPlayer(result.player);setGuided(null);
        setRescue(null);
      }
    }catch(caught){
      if(ticket===epoch.current)setError(caught instanceof Error
        ?caught.message:'Original maze generation failed.');
    }finally{if(ticket===epoch.current)setBusy(false);}
  };
  const play=async(edge:string)=>{
    if(!review||!player||busy||moves.length>=80)return;
    if(!player.options.some(x=>x.edge===edge&&x.available))return;
    const ticket=++epoch.current;
    setBusy(true);setError('');
    try{
      const next=[...moves,edge];
      const result=await post<Player&{ok:boolean}>('/play',{
        ...settings,moves:next,
      });
      if(!result.ok||result.played_edges.join('|')!==next.join('|'))
        throw new Error('Maze move could not be verified against original world.');
      if(ticket===epoch.current){
        setPlayer(result);setMoves(next);setRescue(null);
        if(result.completed)setNotice('Goal reached through actual original maze gameplay.');
      }
    }catch(caught){
      if(ticket===epoch.current)setError(caught instanceof Error
        ?caught.message:'Original maze move failed.');
    }finally{if(ticket===epoch.current)setBusy(false);}
  };
  const undo=async()=>{
    if(!review||busy||moves.length===0)return;
    const ticket=++epoch.current;
    setBusy(true);setError('');
    const next=moves.slice(0,-1);
    try{
      const result=await post<Player&{ok:boolean}>('/play',{
        ...settings,moves:next,
      });
      if(!result.ok||result.played_edges.join('|')!==next.join('|'))
        throw new Error('Maze return state no longer verifies.');
      if(ticket===epoch.current){
        setMoves(next);setPlayer(result);setNotice('');setRescue(null);
      }
    }catch(caught){
      if(ticket===epoch.current)setError(caught instanceof Error
        ?caught.message:'Cannot rewind original world journey.');
    }finally{if(ticket===epoch.current)setBusy(false);}
  };
  const findSafeWay=async()=>{
    if(!review||!player||busy)return;
    const ticket=++epoch.current;
    setBusy(true);setError('');setRescue(null);
    try{
      const proof=await post<{
        ok:boolean;reachable_now:boolean;next_move:string|null;
        remaining_actions:number;reset_required:boolean;
        proof:string;
      }>('/recovery',{...settings,moves});
      if(!proof.ok||typeof proof.reachable_now!=='boolean'||
         typeof proof.reset_required!=='boolean'||
         (proof.reachable_now&&proof.next_move!==null&&
          !player.options.some(x=>x.edge===proof.next_move&&x.available)))
        throw new Error('Current-game maze rescue proof is inconsistent.');
      if(ticket===epoch.current)setRescue(proof);
    }catch(caught){
      if(ticket===epoch.current)setError(caught instanceof Error
        ?caught.message:'Original maze recovery failed.');
    }finally{if(ticket===epoch.current)setBusy(false);}
  };
  const startWitness=(path:string[])=>{
    if(!review||busy||!path.length)return;
    setMoves([]);setPlayer(review.player);setGuided(path);setRescue(null);
    setNotice('Following a constructively proven path. Each step still plays for real.');
    setError('');
  };
  const exportProject=async()=>{
    if(!review||!approved||!attested||busy||!isEditor||!validSeed)return;
    setBusy(true);setError('');setNotice('');
    try{
      const response=await fetch(API+'/source-bundle',{
        method:'POST',cache:'no-store',
        headers:authHeaders({'Content-Type':'application/json'}),
        body:JSON.stringify({
          ...settings,original_work_attested:true,approved:true,
        }),
      });
      if(!response.ok)throw new Error('Maze source export was not authorized or proved.');
      await saveZip(await response.blob());
      setNotice('Original C99 playable maze source exported. Native build tests are separate.');
    }catch(caught){
      setError(caught instanceof Error?caught.message:'Native maze export failed.');
    }finally{setBusy(false);}
  };
  const cert=review?.certificate;
  const deadends=new Set(cert?.real_dead_ends||[]);
  const core=new Set(cert?.backbone_locations||[]);
  const path=(name:string)=>name.replace(/^maze_/,'');
  return (
    <SafeAreaView style={s.root}>
      <ScrollView contentContainerStyle={s.page}>
        <Text style={s.title}>Dragon · Maze Forge</Text>
        <Text style={s.copy}>
          Construct a genuinely finishable, original world first.
          Then add real scenic loops, long detours, doublebacks, dead ends
          with discoveries, secret shortcuts, transport and environmental routes.
          Every room must admit a proven route toward the goal.
        </Text>
        {!isEditor&&<Text style={s.warning}>An editor account is required.</Text>}
        <Text style={s.heading}>Original world seed</Text>
        <TextInput style={s.input} value={seed} maxLength={10}
          keyboardType="number-pad" editable={isEditor&&!busy}
          onChangeText={value=>{setSeed(value);reset();}}
          accessibilityLabel="Original maze seed"/>
        <Text style={s.heading}>Grid dimensions</Text>
        <View style={s.chips}>
          {([4,5,6,7,8] as const).map(v=>(
            <TouchableOpacity key={'w'+v} style={[s.chip,width===v&&s.selected]}
              onPress={()=>{setWidth(v);reset();}} disabled={!isEditor||busy}>
              <Text style={s.copy}>Width {v}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <View style={s.chips}>
          {([4,5,6] as const).map(v=>(
            <TouchableOpacity key={'h'+v} style={[s.chip,height===v&&s.selected]}
              onPress={()=>{setHeight(v);reset();}} disabled={!isEditor||busy}>
              <Text style={s.copy}>Height {v}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <Text style={s.heading}>Intentional challenge</Text>
        <View style={s.chips}>
          {profiles.map(item=>(
            <TouchableOpacity key={item}
              style={[s.chip,challenge===item&&s.selected]}
              onPress={()=>{setChallenge(item);reset();}}
              disabled={!isEditor||busy}>
              <Text style={s.copy}>{item}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <Text style={s.heading}>Environment</Text>
        <View style={s.chips}>
          {climates.map(item=>(
            <TouchableOpacity key={item}
              style={[s.chip,weather===item&&s.selected]}
              onPress={()=>{setWeather(item);reset();}}
              disabled={!isEditor||busy}>
              <Text style={s.copy}>{label(item)}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <Text style={s.heading}>Scenic loops: {scenic}%</Text>
        <View style={s.chips}>{[0,25,50,75,100].map(x=>(
          <TouchableOpacity key={x} style={[s.chip,scenic===x&&s.selected]}
            onPress={()=>{setScenic(x);reset();}} disabled={!isEditor||busy}>
            <Text style={s.copy}>{x}%</Text>
          </TouchableOpacity>
        ))}</View>
        <Text style={s.heading}>Detour braids: {detours}%</Text>
        <View style={s.chips}>{[0,25,50,70,100].map(x=>(
          <TouchableOpacity key={x} style={[s.chip,detours===x&&s.selected]}
            onPress={()=>{setDetours(x);reset();}} disabled={!isEditor||busy}>
            <Text style={s.copy}>{x}%</Text>
          </TouchableOpacity>
        ))}</View>
        <Text style={s.heading}>Unlockable secrets: {secrets}</Text>
        <View style={s.chips}>{[0,1,2,3,4].map(x=>(
          <TouchableOpacity key={x} style={[s.chip,secrets===x&&s.selected]}
            onPress={()=>{setSecrets(x);reset();}} disabled={!isEditor||busy}>
            <Text style={s.copy}>{x}</Text>
          </TouchableOpacity>
        ))}</View>
        <TouchableOpacity accessibilityRole="button"
          style={[s.action,(!isEditor||busy||!validSeed)&&s.disabled]}
          disabled={!isEditor||busy||!validSeed} onPress={create}>
          <Text style={s.actionText}>Construct and certify every room</Text>
        </TouchableOpacity>
        {busy&&<ActivityIndicator color="#9be7bc"/>}
        {cert&&player&&<>
          <View style={s.panel}>
            <Text style={s.heading}>
              {cert.dimensions[0]*cert.dimensions[1]} playable rooms
            </Text>
            <Text style={s.copy}>
              {cert.backbone_moves} guaranteed backbone decisions ·
              {' '}{cert.real_dead_ends.length} rewarding side chambers ·
              {' '}{cert.secret_witnesses.length} proven secret bypasses ·
              {' '}{cert.scenic_witnesses.length} scenic tours sampled
            </Text>
            <Text style={s.copy}>
              All {cert.all_climates_backbone_verified.length} supported climates
              and {cert.location_recovery_count} rooms checked.
            </Text>
            <Text style={s.hint}>
              Visual cells show original-world places. The choice list below
              owns actual traversable connections and hidden discoveries.
            </Text>
            {Array.from({length:height},(_,row)=>(
              <View key={row} style={s.gridrow}>
                {Array.from({length:width},(_,col)=>{
                  const node='maze_'+row+'_'+col;
                  const here=player.world_position===node;
                  const isGoal=cert.goal===node;
                  const isStart=cert.start===node;
                  const isSide=deadends.has(node);
                  const isCore=core.has(node);
                  return <View key={node} style={[s.cell,
                    isCore&&s.core, isSide&&s.side,
                    isGoal&&s.goal,here&&s.here]}>
                    <Text style={s.cellText}>
                      {here?'●':isGoal?'★':isStart?'S':isSide?'◇':'·'}
                    </Text>
                  </View>;
                })}
              </View>
            ))}
            <Text style={s.hint}>
              ● current · ★ goal · ◇ rewarding dead end · spine cells form
              the certified winning corridor
            </Text>
          </View>
          <View style={s.panel}>
            <Text style={s.heading}>
              {player.completed?'Maze completed':label(player.world_position)}
            </Text>
            <Text style={s.copy}>
              {player.elapsed_minutes} minutes · {player.remaining_cash} currency ·
              {' '}{player.remaining_energy} stamina
            </Text>
            <Text style={s.hint}>
              Discovered: {player.known_tokens.map(label).join(', ')}
            </Text>
            {!player.completed&&player.options.map(option=>(
              <TouchableOpacity key={option.edge}
                accessibilityRole="button" disabled={busy||!option.available}
                style={[s.pass,(!option.available||busy)&&s.disabled]}
                onPress={()=>play(option.edge)}>
                <Text style={s.actionText}>
                  {label(option.mode)} → {path(option.to)}
                </Text>
                <Text style={s.copy}>
                  {option.time_minutes} min · {option.price} fare ·
                  {' '}{option.shape.map(label).join(' / ')}
                </Text>
                {!option.available&&<Text style={s.warning}>
                  {label(option.access)}
                </Text>}
              </TouchableOpacity>
            ))}
            <TouchableOpacity accessibilityRole="button"
              style={[s.action,busy&&s.disabled]} disabled={busy}
              onPress={findSafeWay}>
              <Text style={s.actionText}>
                Ask Dragon for an actually playable escape
              </Text>
            </TouchableOpacity>
            {rescue&&<View style={s.pass}>
              <Text style={s.copy}>
                {rescue.reachable_now
                  ?rescue.remaining_actions+' proven safe moves remain'
                  :'Action/time budget exhausted — use Restart or Guided route'}
              </Text>
              <Text style={s.hint}>{rescue.proof}</Text>
              {rescue.next_move&&<TouchableOpacity style={s.chip}
                onPress={()=>{if(rescue.next_move)play(rescue.next_move);}}
                disabled={busy}>
                <Text style={s.actionText}>Take next protected escape step</Text>
              </TouchableOpacity>}
            </View>}
            <View style={s.chips}>
              <TouchableOpacity style={s.chip} disabled={busy||!moves.length}
                onPress={undo}>
                <Text style={s.actionText}>Undo last move</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.chip} disabled={busy}
                onPress={()=>startWitness(cert.backbone)}>
                <Text style={s.actionText}>Guided guaranteed route</Text>
              </TouchableOpacity>
            </View>
            {guided&&<TouchableOpacity accessibilityRole="button"
              disabled={busy||player.completed||moves.length>=guided.length}
              style={[s.action,busy&&s.disabled]}
              onPress={()=>play(guided[moves.length])}>
              <Text style={s.actionText}>
                Replay proven real step {moves.length}/{guided.length}
              </Text>
            </TouchableOpacity>}
          </View>
          <View style={s.panel}>
            <Text style={s.heading}>Real alternate journeys</Text>
            <Text style={s.copy}>
              Choose a route to restart and play it yourself. These routes
              include optional loops and deliberately slower alternatives.
            </Text>
            {([
              ['Long doubleback',cert.doubleback_witnesses[0]],
              ['Deliberately impractical multi-lap route',cert.impractical_witnesses[0]],
              ['Scenic detour',cert.scenic_witnesses[0]],
              ['Secret clue route',cert.secret_witnesses[0]],
            ] as const).filter(x=>!!x[1]).map(([title,route])=>(
              <TouchableOpacity key={title} style={s.pass}
                disabled={busy} onPress={()=>{if(route)startWitness(route);}}>
                <Text style={s.actionText}>{title}</Text>
                <Text style={s.copy}>{route?.length} actual maze steps</Text>
              </TouchableOpacity>
            ))}
          </View>
        </>}
        <TouchableOpacity style={s.chip} accessibilityRole="checkbox"
          accessibilityState={{checked:attested}} disabled={!isEditor||busy}
          onPress={()=>{setAttested(!attested);setApproved(false);}}>
          <Text style={s.copy}>
            {attested?'☑':'☐'} Original homebrew world; no copied or
            unlicensed third-party maze content.
          </Text>
        </TouchableOpacity>
        <TouchableOpacity style={s.chip} accessibilityRole="checkbox"
          accessibilityState={{checked:approved}}
          disabled={!isEditor||busy||!attested||!review}
          onPress={()=>setApproved(!approved)}>
          <Text style={s.copy}>
            {approved?'☑':'☐'} Approve verified original native C99 source export
          </Text>
        </TouchableOpacity>
        <TouchableOpacity accessibilityRole="button"
          style={[s.action,(!isEditor||busy||!attested||!approved||!review)&&s.disabled]}
          disabled={!isEditor||busy||!attested||!approved||!review}
          onPress={exportProject}>
          <Text style={s.actionText}>Export actual completable C99 maze source</Text>
        </TouchableOpacity>
        {!!error&&<Text accessibilityRole="alert" style={s.warning}>{error}</Text>}
        {!!notice&&<Text accessibilityRole="alert" style={s.success}>{notice}</Text>}
        <Text style={s.hint}>
          Completion is constructed and independently replayed from every room
          after normally reachable moves. Recklessly exhausted resources or
          an 80-action limit can require restart; this is not a guarantee of
          universal safe play after every arbitrary history. Game-specific
          physics and legal publication clearance remain separate.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}
export default function DragonMazeForge(){
  return <StudioLoginGate><Editor/></StudioLoginGate>;
}
const s=StyleSheet.create({
  root:{flex:1,backgroundColor:'#101a27'},
  page:{padding:16,paddingBottom:70,gap:12,width:'100%',maxWidth:850,alignSelf:'center'},
  title:{fontSize:25,fontWeight:'700',color:'#eff8f3'},
  heading:{fontSize:16,fontWeight:'700',color:'#d3efe0'},
  copy:{fontSize:13,lineHeight:19,color:'#c9dbd4'},
  hint:{fontSize:12,lineHeight:18,color:'#a9c1b9'},
  warning:{fontSize:13,color:'#fbc1ad'},
  success:{fontSize:14,color:'#b4f3c7'},
  input:{padding:12,backgroundColor:'#1b313c',borderWidth:1,
    borderColor:'#617c75',borderRadius:9,color:'#fff'},
  chips:{flexDirection:'row',flexWrap:'wrap',gap:6},
  chip:{padding:10,borderRadius:9,backgroundColor:'#263e4a'},
  selected:{backgroundColor:'#427b59'},
  disabled:{opacity:0.42},
  action:{padding:13,borderRadius:10,backgroundColor:'#347d59',alignItems:'center'},
  actionText:{fontSize:13,fontWeight:'700',color:'#edfbed'},
  panel:{padding:12,borderRadius:12,backgroundColor:'#1a2e3b',gap:8},
  pass:{padding:11,borderRadius:9,backgroundColor:'#244454',gap:3},
  gridrow:{flexDirection:'row',gap:3,justifyContent:'center'},
  cell:{width:27,height:27,borderRadius:4,backgroundColor:'#253643',
        justifyContent:'center',alignItems:'center'},
  core:{backgroundColor:'#33556a'},
  side:{backgroundColor:'#554932'},
  goal:{backgroundColor:'#738147'},
  here:{backgroundColor:'#3e9a63'},
  cellText:{fontSize:14,fontWeight:'700',color:'#fff'},
});
