/** Dragon World Atlas — multiple actually playable, completed original mazes.
 *
 * Each room movement and every inter-region portal is checked against
 * authoritative Python mechanics. Native C99 compilation is separately
 * available for individual regions; this screen does not claim a single
 * compiled multi-region binary or original game publication clearance.
 */
import React from 'react';
import {
  SafeAreaView,ScrollView,StyleSheet,Text,TextInput,
  TouchableOpacity,View,ActivityIndicator,
} from 'react-native';
import StudioLoginGate,{useStudioAuth} from '../src/auth/StudioLoginGate';
import {authHeaders} from '../src/auth/gameforgeAuth';
import {API_BASE} from '../utils/apiBase';
const API=(API_BASE||'').replace(/\/$/,'')+
  '/api/dragon-academy/native/production/routes/atlas';
type Branch={destination:number;command:string;route_type:string;available:boolean};
type Option={edge:string;to:string;mode:string;shape:string[];
  time_minutes:number;available:boolean;access:string};
type GameState={
  region:number;total_regions:number;visited_regions:number[];
  played_commands:string[];completed_world:boolean;
  regional_play:{
    world_position:string;goal:string;completed:boolean;
    options:Option[];elapsed_minutes:number;known_tokens:string[];
  };
  portal_choices:Branch[];
};
type AtlasPreview={
  ok:boolean;review:{
    status:string;rooms:number;regions:number;
    regional_routes:number;climate_completion:boolean;
  };
  atlas:{
    proof:{
      fast_replay_commands:string[];scenic_replay_commands:string[];
      fast_regional_route:number[];scenic_regional_route:number[];
      distinct_regional_goal_paths:number;
      all_room_proofs_available:boolean;
      regional_climates_verified:boolean;
      guarantee_scope:string;
    };
    regional:Array<{
      index:number;rooms:number;deadends:number;secrets:number;
      scenic_tours:number;maze_digest:string;
    }>;
  };
  player:GameState;native_claim:string;
};
const climates=['clear','rain','windy','storm','snow','high_tide'] as const;
const profiles=['gentle','balanced','challenging','spicy'] as const;
const readable=(x:string)=>x.replace(/_/g,' ');
async function request<T>(endpoint:string,body:object):Promise<T>{
  const response=await fetch(API+endpoint,{
    method:'POST',cache:'no-store',
    headers:authHeaders({'Content-Type':'application/json'}),
    body:JSON.stringify(body),
  });
  if(!response.ok)throw new Error(response.status===403
    ?'A creator/editor identity is required for original maze worlds.'
    :response.status===422
    ?'The world passage, player state or bounded region proof was rejected.'
    :'Dragon multi-region world service unavailable.');
  return response.json() as Promise<T>;
}
function AtlasEditor(){
  const {role}=useStudioAuth();
  const editor=role==='editor'||role==='admin';
  const [seed,setSeed]=React.useState('1977');
  const [regions,setRegions]=React.useState(4);
  const [width,setWidth]=React.useState(6);
  const [height,setHeight]=React.useState(6);
  const [climate,setClimate]=React.useState<typeof climates[number]>('clear');
  const [challenge,setChallenge]=React.useState<typeof profiles[number]>('balanced');
  const [preview,setPreview]=React.useState<AtlasPreview|null>(null);
  const [player,setPlayer]=React.useState<GameState|null>(null);
  const [commands,setCommands]=React.useState<string[]>([]);
  const [tour,setTour]=React.useState<string[]|null>(null);
  const [busy,setBusy]=React.useState(false);
  const [error,setError]=React.useState('');
  const [message,setMessage]=React.useState('');
  const generation=React.useRef(0);
  const numeric=Number(seed);
  const valid=/^\d{1,10}$/.test(seed)&&Number.isSafeInteger(numeric)&&
    numeric>=0&&numeric<=0xffffffff;
  const config={
    seed:numeric,regions,width,height,climate,challenge,
    scenic_density:60,detour_density:70,secret_count:2,
  };
  const clear=()=>{
    generation.current++;
    setBusy(false);setPreview(null);setPlayer(null);setCommands([]);
    setTour(null);setError('');setMessage('');
  };
  const create=async()=>{
    if(!editor||!valid||busy)return;
    const ticket=++generation.current;
    setBusy(true);setError('');setMessage('');
    try{
      const proof=await request<AtlasPreview>('/preview',config);
      if(!proof.ok||
         proof.review?.status!=='hierarchical_completion_verified'||
         !proof.review?.climate_completion||
         !proof.atlas?.proof?.all_room_proofs_available||
         !proof.atlas?.proof?.regional_climates_verified||
         proof.review.rooms!==regions*width*height||
         proof.atlas.regional.length!==regions)
        throw new Error('Original world atlas returned an incomplete completion proof.');
      if(ticket===generation.current){
        setPreview(proof);setPlayer(proof.player);
        setCommands([]);setTour(null);
      }
    }catch(caught){
      if(ticket===generation.current)setError(
        caught instanceof Error?caught.message:'Cannot construct original world atlas.');
    }finally{if(ticket===generation.current)setBusy(false);}
  };
  const move=async(action:string)=>{
    if(!preview||!player||busy||commands.length>=512)return;
    const allowed=player.portal_choices.some(x=>x.available&&x.command===action)||
      player.regional_play.options.some(x=>x.available&&x.edge===action);
    if(!allowed)return;
    const ticket=++generation.current;
    setBusy(true);setError('');
    const next=[...commands,action];
    try{
      const current=await request<GameState&{ok:boolean}>('/play',{
        ...config,commands:next,
      });
      if(!current.ok||current.played_commands.join('|')!==next.join('|'))
        throw new Error('Native-original world traversal integrity changed.');
      if(ticket===generation.current){
        setCommands(next);setPlayer(current);
        setMessage(current.completed_world
          ? 'Entire original game atlas complete. Try the alternative world route!'
          : '');
      }
    }catch(caught){
      if(ticket===generation.current)setError(
        caught instanceof Error?caught.message:'Regional game move was rejected.');
    }finally{if(ticket===generation.current)setBusy(false);}
  };
  const startTour=(route:string[])=>{
    if(!preview||!route.length||busy)return;
    setCommands([]);setPlayer(preview.player);setTour(route);
    setError('');setMessage('Replay the selected world-scale route one genuine decision at a time.');
  };
  const nextTour=()=>{
    if(!tour||busy||!player||player.completed_world||
       commands.length>=tour.length)return;
    move(tour[commands.length]);
  };
  const restart=()=>{
    if(!preview||busy)return;
    setCommands([]);setPlayer(preview.player);
    setTour(null);setMessage('');setError('');
  };
  return <SafeAreaView style={s.root}>
    <ScrollView contentContainerStyle={s.page}>
      <Text style={s.title}>Dragon · World Atlas</Text>
      <Text style={s.copy}>
        Link several truly completable original mazes into one branching
        adventure. Every regional goal is playable, every portal is earned,
        and shortcut and full exploration journeys lead to the final world.
      </Text>
      {!editor&&<Text style={s.warning}>Editor access is required.</Text>}
      <Text style={s.heading}>Original world seed</Text>
      <TextInput style={s.input} value={seed} maxLength={10}
        onChangeText={v=>{setSeed(v);clear();}}
        keyboardType="number-pad" editable={editor&&!busy}
        accessibilityLabel="Original atlas world seed"/>
      <Text style={s.heading}>Playable regions</Text>
      <View style={s.chips}>{[2,3,4,6,8,12].map(n=>(
        <TouchableOpacity key={n} disabled={!editor||busy}
          onPress={()=>{setRegions(n);clear();}}
          style={[s.chip,regions===n&&s.selected]}>
          <Text style={s.copy}>{n} regions</Text>
        </TouchableOpacity>
      ))}</View>
      <Text style={s.heading}>Rooms per region</Text>
      <View style={s.chips}>{[
        [4,4],[5,4],[6,6],[8,6],
      ].map(([w,h])=>(
        <TouchableOpacity key={w+'x'+h} disabled={!editor||busy}
          onPress={()=>{setWidth(w);setHeight(h);clear();}}
          style={[s.chip,width===w&&height===h&&s.selected]}>
          <Text style={s.copy}>{w}×{h}</Text>
        </TouchableOpacity>
      ))}</View>
      <Text style={s.heading}>Climate and route challenge</Text>
      <View style={s.chips}>{climates.map(item=>(
        <TouchableOpacity key={item} disabled={!editor||busy}
          onPress={()=>{setClimate(item);clear();}}
          style={[s.chip,climate===item&&s.selected]}>
          <Text style={s.copy}>{readable(item)}</Text>
        </TouchableOpacity>
      ))}</View>
      <View style={s.chips}>{profiles.map(item=>(
        <TouchableOpacity key={item} disabled={!editor||busy}
          onPress={()=>{setChallenge(item);clear();}}
          style={[s.chip,challenge===item&&s.selected]}>
          <Text style={s.copy}>{item}</Text>
        </TouchableOpacity>
      ))}</View>
      <TouchableOpacity style={[s.action,(!editor||busy||!valid)&&s.disabled]}
        disabled={!editor||busy||!valid} onPress={create}>
        <Text style={s.actionText}>Build and verify entire original atlas</Text>
      </TouchableOpacity>
      {busy&&<ActivityIndicator color="#a7f2be"/>}
      {preview&&player&&<>
        <View style={s.panel}>
          <Text style={s.heading}>
            {preview.review.rooms} individually certified rooms
          </Text>
          <Text style={s.copy}>
            {preview.review.regions} regions ·
            {' '}{preview.review.regional_routes} distinct regional goal paths ·
            six climate conditions per maze
          </Text>
          <Text style={s.hint}>
            These are game-world room completions, not automatically
            certified console releases or player enjoyment studies.
          </Text>
          {preview.atlas.regional.map(region=>(
            <View key={region.index} style={[
              s.stage,region.index===player.region&&s.here,
            ]}>
              <Text style={s.actionText}>
                Region {region.index+1} · {region.rooms} rooms
                {player.visited_regions.includes(region.index)?' ✓':''}
              </Text>
              <Text style={s.copy}>
                {region.deadends} dead ends · {region.secrets} secret routes ·
                {' '}{region.scenic_tours} scenic trips
              </Text>
            </View>
          ))}
        </View>
        <View style={s.panel}>
          <Text style={s.heading}>
            {player.completed_world?'Entire Atlas Completed!':
              'Region '+(player.region+1)+': '+readable(player.regional_play.world_position)}
          </Text>
          <Text style={s.copy}>
            {player.regional_play.elapsed_minutes} minutes in this region ·
            {' '}{commands.length} total real game choices
          </Text>
          <Text style={s.hint}>
            Collected: {player.regional_play.known_tokens.map(readable).join(', ')}
          </Text>
          {!player.completed_world&&player.regional_play.options.map(option=>(
            <TouchableOpacity key={option.edge}
              disabled={!option.available||busy} onPress={()=>move(option.edge)}
              style={[s.stage,(!option.available||busy)&&s.disabled]}>
              <Text style={s.actionText}>
                {readable(option.mode)} → {readable(option.to)}
              </Text>
              <Text style={s.hint}>
                {option.time_minutes} min · {option.shape.map(readable).join(' / ')}
                {!option.available?' · '+readable(option.access):''}
              </Text>
            </TouchableOpacity>
          ))}
          {player.portal_choices.map(portal=>(
            <TouchableOpacity key={portal.command}
              disabled={!portal.available||busy}
              onPress={()=>move(portal.command)}
              style={[s.action,(!portal.available||busy)&&s.disabled]}>
              <Text style={s.actionText}>
                {portal.route_type==='shortcut'?'Skip optional region →':'Explore next region →'}
                {' '}Region {portal.destination+1}
              </Text>
            </TouchableOpacity>
          ))}
          <View style={s.chips}>
            <TouchableOpacity style={s.chip} disabled={busy}
              onPress={restart}>
              <Text style={s.actionText}>Restart atlas</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.chip}
              disabled={busy||!commands.length}
              onPress={async()=>{
                if(busy||!commands.length)return;
                const ticket=++generation.current;
                setBusy(true);
                const next=commands.slice(0,-1);
                try{
                  const replay=await request<GameState&{ok:boolean}>('/play',{
                    ...config,commands:next,
                  });
                  if(!replay.ok||replay.played_commands.join('|')!==next.join('|'))
                    throw new Error('Atlas rewind proof mismatched');
                  if(ticket===generation.current){
                    setCommands(next);setPlayer(replay);setMessage('');
                  }
                }catch(e){if(ticket===generation.current)setError(
                  e instanceof Error?e.message:'Could not rewind travel.');}
                finally{if(ticket===generation.current)setBusy(false);}
              }}>
              <Text style={s.actionText}>Undo travel decision</Text>
            </TouchableOpacity>
          </View>
        </View>
        <View style={s.panel}>
          <Text style={s.heading}>Choose how to complete the world</Text>
          <TouchableOpacity style={s.stage} disabled={busy}
            onPress={()=>startTour(preview.atlas.proof.fast_replay_commands)}>
            <Text style={s.actionText}>Fast cross-region shortcuts</Text>
            <Text style={s.copy}>
              {preview.atlas.proof.fast_replay_commands.length} real
              decisions · {preview.atlas.proof.fast_regional_route.length} regions
            </Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.stage} disabled={busy}
            onPress={()=>startTour(preview.atlas.proof.scenic_replay_commands)}>
            <Text style={s.actionText}>Long scenic every-region expedition</Text>
            <Text style={s.copy}>
              {preview.atlas.proof.scenic_replay_commands.length} real
              decisions · {preview.atlas.proof.scenic_regional_route.length} regions
            </Text>
          </TouchableOpacity>
          {tour&&<TouchableOpacity style={[s.action,busy&&s.disabled]}
            onPress={nextTour}
            disabled={busy||player.completed_world||commands.length>=tour.length}>
            <Text style={s.actionText}>
              Advance proven route {commands.length}/{tour.length}
            </Text>
          </TouchableOpacity>}
        </View>
      </>}
      {!!error&&<Text accessibilityRole="alert" style={s.warning}>{error}</Text>}
      {!!message&&<Text accessibilityRole="alert" style={s.success}>{message}</Text>}
      <Text style={s.hint}>
        The regional world and portal gameplay is currently served by the
        authenticated Python runtime. Each region has C99-capable source,
        but no one-binary multi-region native or physical console approval
        is claimed. An emergency restart remains available after exhausting
        arbitrary time or move budgets.
      </Text>
    </ScrollView>
  </SafeAreaView>;
}
export default function DragonWorldAtlas(){
  return <StudioLoginGate><AtlasEditor/></StudioLoginGate>;
}
const s=StyleSheet.create({
  root:{flex:1,backgroundColor:'#111923'},
  page:{padding:16,paddingBottom:75,gap:12,width:'100%',maxWidth:850,alignSelf:'center'},
  title:{fontSize:25,fontWeight:'700',color:'#f0f7f3'},
  heading:{fontSize:16,fontWeight:'700',color:'#d7ede0'},
  copy:{fontSize:13,lineHeight:20,color:'#c8d8d0'},
  hint:{fontSize:12,lineHeight:19,color:'#a3bcb4'},
  actionText:{fontSize:13,fontWeight:'700',color:'#effff0'},
  warning:{fontSize:13,color:'#ffc2ad'},
  success:{fontSize:13,color:'#aff0c3'},
  input:{padding:12,borderRadius:9,borderColor:'#5a726b',
    borderWidth:1,backgroundColor:'#20343c',color:'#fff'},
  chips:{flexDirection:'row',flexWrap:'wrap',gap:7},
  chip:{padding:11,borderRadius:9,backgroundColor:'#28404b'},
  selected:{backgroundColor:'#41765c'},
  action:{padding:14,borderRadius:10,backgroundColor:'#357852',alignItems:'center'},
  disabled:{opacity:0.4},
  panel:{backgroundColor:'#1a2d39',borderRadius:12,padding:14,gap:9},
  stage:{backgroundColor:'#244050',borderRadius:9,padding:11,gap:5},
  here:{backgroundColor:'#28654e'},
});
