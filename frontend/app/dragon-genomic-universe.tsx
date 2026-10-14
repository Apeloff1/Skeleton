/** Dragon Genome Forge: an exact-addressed astronomical world and path editor.
 *
 * Never converts huge IDs to JavaScript numbers. Worlds and paths are
 * materialized one at a time by the server and replayed through actual
 * original turn rules; capacity is not a count of shipped unique games.
 */
import React from 'react';
import {
  ActivityIndicator,SafeAreaView,ScrollView,StyleSheet,Text,
  TextInput,TouchableOpacity,View,
} from 'react-native';
import StudioLoginGate,{useStudioAuth} from '../src/auth/StudioLoginGate';
import {authHeaders} from '../src/auth/gameforgeAuth';
import {API_BASE} from '../utils/apiBase';

const API=(API_BASE||'').replace(/\/$/,'')+
  '/api/dragon-academy/native/production/worlds/genome';
const CHOICE_VERBS=[
  'survey_elevation','map_biomes','study_river','explore_caves',
  'scan_skies','forecast_storm','study_seasons','chart_stars',
  'tend_flora','track_fauna','forage_food','prospect_ore',
  'plan_building','mediate_dispute','scout_pass','trace_shifting_wall',
] as const;
type Option={
  name:string;available:boolean;reason:string;strength?:number;
  genomic_cost?:number;physical_axis?:string;source?:string;
};
type Terrain={
  realm:number;x:number;y:number;biome:string;landmark:string;
  original_biome?:string;player_caused_terrain_change?:boolean;
  genome_cell_sha256:string;
  genomic_environment:Record<string,number>;
};
type GameReport={
  schema:string;address:string;genome_digest:string;
  style:string;lifecycle:string;
  has_mandatory_win:boolean;has_possible_ending:boolean;
  experienced_endings:string[];playable:boolean;postgame:boolean;
  player:{
    base:{realm:number;x:number;y:number;turn:number;
      history_digest:string;endings_seen:string[]};
    stamina:number;hydration:number;food:number;
    material:number;credits:number;knowledge:number;
    community:number;ecology:number;danger:number;
    infrastructure:number;portal_charge:number;
    signals:number[];choices:number;history_digest:string;
  };
  local_terrain:Terrain[];actions:Option[];
  physical_controls:Record<string,{
    level:number;strength:number;domain:string;
  }>;
  audit_scope:string;
};
type SourceAddress={
  schema:string;decimal_index:string;base_design_index:number;
  world_id:number;variant:number;style:string;lifecycle:string;
  genomic_code:string;levels:number[];
  genome_digest:string;actual_game_configuration:boolean;
  completed_unique_game:boolean;
};
type Capacity={
  ok:boolean;
  genomic_world_space:{
    controlled_simulation_axes:number;
    levels_per_axis:number;
    axes:{id:string;description:string;levels:number}[];
    genomes_per_original_base_design:string;
    reversibly_addressable_world_configurations:string;
    completed_or_legally_cleared_games:number;
    address_encoding:string;
  };
  real_choice_path_space:{
    actual_implemented_choices_per_step:number;
    bounded_executable_decisions_per_path:number;
    per_world_choice_programs:string;
    globally_addressable_choice_paths:string;
    shipped_unique_games:number;
  };
  claim:string;
};
type Inspect={ok:boolean;source_address:SourceAddress;
  actual_game_state:GameReport;materialized_cells:number;
  goal_required:boolean};
type Play={ok:boolean;replayed_actions:string[];
  actual_game_state:GameReport;
  final_history_digest:string;source_fingerprint:string};
type Route={
  schema:string;decimal_path_index:string;
  actions:string[];word:number[];world_decimal_index:string;
  final_history_digest:string;distinct_source_actions:number;
  final_energy:number;final_hydration:number;final_knowledge:number;
  actually_played:boolean;finished_game_release_approved:boolean;
  execution_digest:string;
};
type Composed={ok:boolean;exact_decimal_path_address:string;
  playable_route:Route;verification:{verified:boolean;
    actual_actions:number;world_still_playable:boolean}};
type Samples={ok:boolean;sampled_count:number;
  distinct_actual_action_histories:number;
  routes:Route[];claim:string};
const fallbackAxisNames=[
  'terrain_elevation','biome_mosaic','watershed','cavern_density',
  'sky_islands','weather_violence','season_clock','day_cycle',
  'flora_dynamics','fauna_aggression','food_bounty','mineral_density',
  'building_complexity','settlement_growth','market_cycle',
  'diplomacy_tension','hostile_pressure','traversal_drag',
  'shifting_maze_rate','portal_instability','discovery_rarity',
  'research_depth','narrative_choice_impact','postgame_renewal',
];
const paint:Record<string,string>={
  woodland:'#366b55',desert:'#927149',coast:'#416b83',
  mountain:'#59677b',ruins:'#694f71',wetlands:'#3d7b74',
  caverns:'#48516c',skylands:'#698ba1',orbital:'#55528c',
  crystal_fields:'#805d93',tundra:'#8ca7a9',garden:'#52916a',
};
const readable=(value:string)=>value.replace(/_/g,' ');
const digitsOnly=(raw:string)=>/^(0|[1-9][0-9]*)$/.test(raw);
async function request<T>(endpoint:string,payload?:object):Promise<T>{
  const response=await fetch(API+endpoint,{
    method:payload?'POST':'GET',cache:'no-store',
    headers:authHeaders(payload?{'Content-Type':'application/json'}:{}),
    ...(payload?{body:JSON.stringify(payload)}:{}),
  });
  if(!response.ok)throw new Error(
    response.status===403?'Original world creation requires editor permission.':
    response.status===422?'This genome, path or action failed exact replay or constraint validation.':
    'Dragon genomic world engine or signing is not available.');
  return response.json() as Promise<T>;
}
function GenomeEditor(){
  const {role}=useStudioAuth();
  const editor=role==='admin'||role==='editor';
  const [capacity,setCapacity]=React.useState<Capacity|null>(null);
  const [address,setAddress]=React.useState('0');
  const [snapshot,setSnapshot]=React.useState<Inspect|null>(null);
  const [play,setPlay]=React.useState<GameReport|null>(null);
  const [moves,setMoves]=React.useState<string[]>([]);
  const [word,setWord]=React.useState<number[]>(
    Array.from({length:16},(_,i)=>i));
  const [compiled,setCompiled]=React.useState<Composed|null>(null);
  const [samples,setSamples]=React.useState<Samples|null>(null);
  const [working,setWorking]=React.useState(false);
  const [error,setError]=React.useState('');
  const [message,setMessage]=React.useState('');
  const epoch=React.useRef(0);
  React.useEffect(()=>{
    let active=true;
    request<Capacity>('/capabilities').then(answer=>{
      if(active&&answer.ok)setCapacity(answer);
    }).catch(()=>{if(active)setCapacity(null);});
    return ()=>{active=false;};
  },[]);
  const invalidate=()=>{
    epoch.current+=1;
    setSnapshot(null);setPlay(null);setMoves([]);
    setCompiled(null);setSamples(null);setError('');setMessage('');
  };
  const inspect=async(index:string)=>{
    if(!editor||working||!digitsOnly(index)||index.length>80)return;
    const ticket=++epoch.current;
    setWorking(true);setError('');setMessage('');
    try{
      const fresh=await request<Inspect>('/inspect',{index});
      if(!fresh.ok||
         fresh.source_address?.decimal_index!==index||
         !fresh.source_address.actual_game_configuration||
         fresh.source_address.levels.length!==24||
         fresh.actual_game_state.local_terrain.length!==25||
         fresh.actual_game_state.address!==index)
        throw new Error('Original world generator did not return a coherent executable world.');
      if(ticket===epoch.current){
        setAddress(index);setSnapshot(fresh);
        setPlay(fresh.actual_game_state);setMoves([]);
        setCompiled(null);setSamples(null);
      }
    }catch(caught){
      if(ticket===epoch.current)setError(caught instanceof Error?
        caught.message:'Cannot materialize original world.');
    }finally{if(ticket===epoch.current)setWorking(false);}
  };
  const setAxis=async(axis:string,value:number)=>{
    if(!snapshot||!editor||working||value<0||value>15)return;
    const ticket=++epoch.current;
    setWorking(true);setError('');
    try{
      const revised=await request<{
        ok:boolean;reversible_decimal_address:string;
        updated_source:SourceAddress;
      }>('/edit',{index:address,changes:{[axis]:value}});
      if(!revised.ok||revised.updated_source.decimal_index!==
         revised.reversible_decimal_address)
        throw new Error('Genomic world edit failed to round-trip its identity.');
      const next=await request<Inspect>('/inspect',{
        index:revised.reversible_decimal_address,
      });
      if(!next.ok||next.source_address.decimal_index!==
         revised.reversible_decimal_address)
        throw new Error('Edited world cannot be re-materialized.');
      if(ticket===epoch.current){
        setAddress(revised.reversible_decimal_address);
        setSnapshot(next);setPlay(next.actual_game_state);
        setMoves([]);setSamples(null);setCompiled(null);
        setMessage('Updated '+readable(axis)+' in the actual world physics.');
      }
    }catch(caught){
      if(ticket===epoch.current)setError(caught instanceof Error?
        caught.message:'Could not apply genomic simulation axis.');
    }finally{if(ticket===epoch.current)setWorking(false);}
  };
  const advance=async(action:string)=>{
    if(!play||!snapshot||!editor||working||moves.length>=128)return;
    if(!play.actions.some(option=>
      option.name===action&&option.available))return;
    const ticket=++epoch.current;
    setWorking(true);setError('');
    const next=[...moves,action];
    try{
      const out=await request<Play>('/play',{index:address,actions:next});
      if(!out.ok||out.replayed_actions.join('|')!==next.join('|')||
         out.source_fingerprint!==snapshot.source_address.genome_digest)
        throw new Error('Game-world replay drifted from its exact source genome.');
      if(ticket===epoch.current){
        setMoves(next);setPlay(out.actual_game_state);
        setMessage(out.actual_game_state.postgame
          ?'Original story completed; postgame remains playable.'
          :'Real world action applied to simulation state.');
      }
    }catch(caught){
      if(ticket===epoch.current)setError(caught instanceof Error?
        caught.message:'Original action was not replayable.');
    }finally{if(ticket===epoch.current)setWorking(false);}
  };
  const reverse=async()=>{
    if(!play||!snapshot||working||moves.length===0)return;
    const ticket=++epoch.current;
    setWorking(true);setError('');
    const old=moves.slice(0,-1);
    try{
      const out=await request<Play>('/play',{index:address,actions:old});
      if(!out.ok||out.replayed_actions.join('|')!==old.join('|'))
        throw new Error('World rewinding would lose exact source history.');
      if(ticket===epoch.current){
        setMoves(old);setPlay(out.actual_game_state);
        setMessage('Earlier source-verified game state restored.');
      }
    }catch(caught){
      if(ticket===epoch.current)setError(caught instanceof Error?
        caught.message:'Cannot undo original world choice.');
    }finally{if(ticket===epoch.current)setWorking(false);}
  };
  const compose=async()=>{
    if(!snapshot||working||!editor||word.length!==16)return;
    const ticket=++epoch.current;
    setWorking(true);setError('');
    try{
      const actual=await request<Composed>('/compose-path',{
        index:address,word,
      });
      if(!actual.ok||!actual.verification.verified||
         actual.playable_route.actions.length!==16||
         actual.playable_route.finished_game_release_approved)
        throw new Error('Authored original route lacked actual gameplay evidence.');
      if(ticket===epoch.current)setCompiled(actual);
    }catch(caught){
      if(ticket===epoch.current)setError(caught instanceof Error?
        caught.message:'Cannot compile original path decisions.');
    }finally{if(ticket===epoch.current)setWorking(false);}
  };
  const sample=async()=>{
    if(!snapshot||working||!editor)return;
    const ticket=++epoch.current;
    setWorking(true);setError('');
    try{
      const actual=await request<Samples>('/sample-paths',{
        index:address,limit:4,
      });
      if(!actual.ok||actual.sampled_count!==4||actual.routes.length!==4)
        throw new Error('Original path sample did not execute all four playthroughs.');
      if(ticket===epoch.current)setSamples(actual);
    }catch(caught){
      if(ticket===epoch.current)setError(caught instanceof Error?
        caught.message:'Cannot sample actual route histories.');
    }finally{if(ticket===epoch.current)setWorking(false);}
  };
  const axes=capacity?.genomic_world_space.axes||
    fallbackAxisNames.map(id=>({id,description:readable(id),levels:16}));
  const tiles=play?.local_terrain||[];
  const current=play?.player;
  const mapCount=Math.sqrt(tiles.length);
  return <SafeAreaView style={s.root}>
    <ScrollView contentContainerStyle={s.page}>
      <Text style={s.title}>Dragon · Genomic Universe Forge</Text>
      <Text style={s.copy}>
        Combine physical world rules, real resource economics, ecology,
        travel and story into an addressable universe far beyond a
        quintillion. Every genome control changes executable game mechanics.
        You can intentionally build worlds with no ending.
      </Text>
      {!editor&&<Text style={s.warning}>
        A signed-in editor is required to construct these worlds.
      </Text>}
      {capacity&&<View style={s.panel}>
        <Text style={s.heading}>Exact combinatorial capacity</Text>
        <Text style={s.metric}>24 independently editable physical axes × 16 levels</Text>
        <Text style={s.copy}>
          World-genome configurations (exact decimal):
        </Text>
        <Text selectable style={s.longNumber}>
          {capacity.genomic_world_space.reversibly_addressable_world_configurations}
        </Text>
        <Text style={s.copy}>
          Independently addressable 16-choice path programs (exact decimal):
        </Text>
        <Text selectable style={s.longNumber}>
          {capacity.real_choice_path_space.globally_addressable_choice_paths}
        </Text>
        <Text style={s.hint}>
          Both are lazy addresses. Zero completed or commercially cleared
          games are claimed by these capacity figures; uniqueness and
          enjoyment require further evaluation.
        </Text>
      </View>}
      <View style={s.panel}>
        <Text style={s.heading}>Arbitrary-precision world address</Text>
        <TextInput style={s.input} value={address} maxLength={80}
          autoCapitalize="none" keyboardType="number-pad"
          accessibilityLabel="Exact original genomic world address"
          editable={editor&&!working} onChangeText={text=>{
            setAddress(text);invalidate();
          }}/>
        <TouchableOpacity style={[s.action,
          (!editor||working||!digitsOnly(address))&&s.disabled]}
          disabled={!editor||working||!digitsOnly(address)}
          onPress={()=>inspect(address)}>
          <Text style={s.actionText}>Materialize and verify exact world</Text>
        </TouchableOpacity>
      </View>
      {working&&<ActivityIndicator color="#baf4c6"/>}
      {snapshot&&play&&current&&<>
        <View style={s.panel}>
          <Text style={s.heading}>
            {readable(snapshot.source_address.style)}
          </Text>
          <Text style={s.copy}>
            {readable(snapshot.source_address.lifecycle)}
            {' · '}world {snapshot.source_address.world_id}
            {' · '}variation {snapshot.source_address.variant+1}
          </Text>
          <Text style={s.hint}>
            {play.has_mandatory_win
              ?'This particular authored mode requires a final objective.'
              :play.has_possible_ending
                ?'Endings exist but the world need not end when one occurs.'
                :'This world has no fixed victory condition.'}
          </Text>
          <Text style={s.copy}>
            {play.playable?'Playable':'Current run ended'}
            {play.postgame?' · Continuing after a story ending':''}
          </Text>
          <Text style={s.hint}>
            Genome evidence: {snapshot.source_address.genome_digest.slice(0,20)}…
          </Text>
        </View>
        <View style={s.panel}>
          <Text style={s.heading}>24 world-generation controls</Text>
          <Text style={s.hint}>
            Change any level from 0 to 15. Each edit regenerates an exact
            new world address and recomputes actual environmental constraints.
          </Text>
          {axes.map((axis,i)=>{
            const level=snapshot.source_address.levels[i];
            return <View key={axis.id} style={s.axis}>
              <View style={s.axisHeader}>
                <View style={{flex:1}}>
                  <Text style={s.actionText}>{readable(axis.id)}</Text>
                  <Text style={s.hint}>{axis.description}</Text>
                </View>
                <Text style={s.metric}>{level}/15</Text>
              </View>
              <View style={s.chips}>
                <TouchableOpacity style={[s.chip,(working||level===0)&&s.disabled]}
                  disabled={working||level===0} onPress={()=>setAxis(axis.id,level-1)}>
                  <Text style={s.actionText}>−</Text>
                </TouchableOpacity>
                {[0,4,8,12,15].map(mark=>(
                  <TouchableOpacity key={mark}
                    style={[s.chip,level===mark&&s.selected]}
                    disabled={working}
                    onPress={()=>setAxis(axis.id,mark)}>
                    <Text style={s.text}>{mark}</Text>
                  </TouchableOpacity>
                ))}
                <TouchableOpacity style={[s.chip,(working||level===15)&&s.disabled]}
                  disabled={working||level===15} onPress={()=>setAxis(axis.id,level+1)}>
                  <Text style={s.actionText}>+</Text>
                </TouchableOpacity>
              </View>
            </View>;
          })}
        </View>
        <View style={s.panel}>
          <Text style={s.heading}>Real generated terrain and traversal</Text>
          {Array.from({length:Math.floor(mapCount)},(_,row)=>(
            <View key={row} style={s.mapRow}>
              {tiles.slice(row*mapCount,(row+1)*mapCount).map((tile,col)=>(
                <View key={tile.x+'-'+tile.y}
                  style={[s.cell,{backgroundColor:paint[tile.biome]||'#3e5961'},
                    row===2&&col===2&&s.here]}>
                  <Text style={s.tileText}>
                    {row===2&&col===2?'●':
                      tile.player_caused_terrain_change?'◆':
                      tile.landmark!=='ordinary_land'?'◇':'·'}
                  </Text>
                </View>
              ))}
            </View>
          ))}
          <Text style={s.hint}>
            Realm {current.base.realm+1}, cell ({current.base.x},
            {current.base.y}). Each tile has calculated elevation,
            water depth, weather, flora, fauna and resource availability.
          </Text>
          {tiles[12]&&<View style={s.chips}>
            {Object.entries(tiles[12].genomic_environment).slice(0,8)
              .map(([name,value])=>(
                <Text key={name} style={s.minorLabel}>
                  {readable(name)}: {value}
                </Text>
              ))}
          </View>}
        </View>
        <View style={s.panel}>
          <Text style={s.heading}>Play — real state changes</Text>
          <Text style={s.copy}>
            Turn {current.base.turn} · stamina {current.stamina} ·
            {' '}water {current.hydration} · food {current.food} ·
            {' '}materials {current.material} · credits {current.credits}
          </Text>
          <Text style={s.copy}>
            Knowledge {current.knowledge} · community {current.community} ·
            {' '}ecology {current.ecology} · danger {current.danger}
          </Text>
          <Text style={s.copy}>
            Infrastructure {current.infrastructure} ·
            portal charge {current.portal_charge}
          </Text>
          <View style={s.chips}>
            <TouchableOpacity style={s.chip} disabled={working||!moves.length}
              onPress={reverse}><Text style={s.actionText}>Undo last action</Text></TouchableOpacity>
            <TouchableOpacity style={s.chip} disabled={working}
              onPress={()=>{setMoves([]);setPlay(snapshot.actual_game_state);
                setMessage('Original world run restarted.');}}>
              <Text style={s.actionText}>Reset world run</Text>
            </TouchableOpacity>
          </View>
          <Text style={s.hint}>
            {moves.length}/128 server-replayed actions in this session.
            This source explorer does not yet have genome-specific durable
            checkpoint storage; Living Worlds has the existing persistent saves.
          </Text>
          {play.actions.map(option=>(
            <TouchableOpacity key={option.name}
              style={[s.choice,(!option.available||working)&&s.disabled]}
              disabled={working||!option.available||moves.length>=128}
              onPress={()=>advance(option.name)}>
              <Text style={s.actionText}>{readable(option.name)}</Text>
              <Text style={s.hint}>
                {option.available
                  ?option.physical_axis
                    ?'Controls '+readable(option.physical_axis)+
                      ' · strength '+option.strength
                    :option.source
                  :readable(option.reason)}
              </Text>
            </TouchableOpacity>
          ))}
          <Text style={s.hint}>
            Distinct gameplay outcomes result from actions and resource
            constraints, not from claiming a procedural ID is a unique game.
          </Text>
        </View>
        <View style={s.panel}>
          <Text style={s.heading}>Author a 16-decision world path</Text>
          <Text style={s.copy}>
            Choose one of sixteen implemented world actions at each step.
            The backend compiles all choices into an exact 64-bit program,
            performs sixteen real game-state transitions and verifies the
            resulting world history.
          </Text>
          {word.map((digit,i)=>(
            <View key={i} style={s.wordRow}>
              <Text style={s.wordIndex}>{i+1}.</Text>
              <TouchableOpacity style={s.chip} disabled={working}
                onPress={()=>setWord(values=>values.map((v,n)=>
                  n===i?(v+15)%16:v))}>
                <Text style={s.actionText}>◀</Text>
              </TouchableOpacity>
              <View style={{flex:1}}>
                <Text style={s.actionText}>{readable(CHOICE_VERBS[digit])}</Text>
                <Text style={s.hint}>Action {digit+1}/16</Text>
              </View>
              <TouchableOpacity style={s.chip} disabled={working}
                onPress={()=>setWord(values=>values.map((v,n)=>
                  n===i?(v+1)%16:v))}>
                <Text style={s.actionText}>▶</Text>
              </TouchableOpacity>
            </View>
          ))}
          <TouchableOpacity style={[s.action,working&&s.disabled]}
            disabled={working} onPress={compose}>
            <Text style={s.actionText}>
              Compile, actually play and verify authored path
            </Text>
          </TouchableOpacity>
          {compiled&&<>
            <Text style={s.copy}>Exact global route ID:</Text>
            <Text selectable style={s.longNumber}>
              {compiled.exact_decimal_path_address}
            </Text>
            <Text style={s.hint}>
              {compiled.playable_route.actions.length} actions executed ·
              independently verified: {compiled.verification.verified?'yes':'no'} ·
              {' '}{compiled.playable_route.distinct_source_actions} unique
              gameplay verbs.
            </Text>
            <Text style={s.hint}>
              Last-history digest:
              {' '}{compiled.playable_route.final_history_digest.slice(0,24)}…
            </Text>
          </>}
        </View>
        <View style={s.panel}>
          <Text style={s.heading}>Independently sample path alternatives</Text>
          <TouchableOpacity style={[s.action,working&&s.disabled]}
            disabled={working} onPress={sample}>
            <Text style={s.actionText}>Execute four distant route programs</Text>
          </TouchableOpacity>
          {samples&&<>
            <Text style={s.copy}>
              {samples.distinct_actual_action_histories} actually distinct
              histories in {samples.sampled_count} sampled original routes.
            </Text>
            {samples.routes.map(item=>(
              <View key={item.decimal_path_index} style={s.choice}>
                <Text style={s.actionText}>
                  {item.distinct_source_actions} gameplay verbs ·
                  {' '}stamina {item.final_energy} · knowledge {item.final_knowledge}
                </Text>
                <Text selectable style={s.hint}>
                  Route {item.decimal_path_index}
                </Text>
              </View>
            ))}
            <Text style={s.hint}>{samples.claim}</Text>
          </>}
        </View>
      </>}
      {!!error&&<Text accessibilityRole="alert" style={s.warning}>{error}</Text>}
      {!!message&&<Text accessibilityRole="alert" style={s.success}>{message}</Text>}
      <Text style={s.hint}>
        This is a functional original turn-based world-generation and route
        compiler. It does not mean trillions of art assets, unique finished
        narratives, AAA physics, compiled console games or legal publishing
        rights have been delivered. Gameplay QA and originality review remain
        release gates.
      </Text>
    </ScrollView>
  </SafeAreaView>;
}
export default function DragonGenomicUniverse(){
  return <StudioLoginGate><GenomeEditor/></StudioLoginGate>;
}
const s=StyleSheet.create({
  root:{flex:1,backgroundColor:'#111c28'},
  page:{padding:14,paddingBottom:78,gap:12,width:'100%',maxWidth:950,
        alignSelf:'center'},
  title:{fontSize:25,fontWeight:'700',color:'#f1fff1'},
  heading:{fontSize:16,fontWeight:'700',color:'#d4f7dc'},
  metric:{fontSize:16,fontWeight:'700',color:'#cfecdc'},
  copy:{fontSize:13,lineHeight:21,color:'#c3d8cc'},
  hint:{fontSize:12,lineHeight:18,color:'#abc4b7'},
  text:{fontSize:13,color:'#edf8ef'},
  longNumber:{fontSize:12,color:'#b7f0c7',fontWeight:'600',lineHeight:20},
  warning:{fontSize:13,color:'#ffb9a6'},
  success:{fontSize:13,color:'#aeefc4'},
  panel:{padding:13,borderRadius:11,backgroundColor:'#203442',gap:9},
  input:{padding:12,borderWidth:1,borderColor:'#668976',
         borderRadius:9,color:'#fff',backgroundColor:'#233d47'},
  chips:{flexDirection:'row',flexWrap:'wrap',gap:6},
  chip:{paddingHorizontal:11,paddingVertical:8,borderRadius:8,
        backgroundColor:'#304d57'},
  selected:{backgroundColor:'#317c58'},
  action:{padding:13,borderRadius:10,backgroundColor:'#347f57',
          alignItems:'center'},
  actionText:{fontSize:13,color:'#f5fff4',fontWeight:'700'},
  disabled:{opacity:0.38},
  axis:{borderBottomWidth:1,borderColor:'#3e5960',paddingVertical:9,gap:7},
  axisHeader:{flexDirection:'row',alignItems:'center',gap:8},
  mapRow:{flexDirection:'row',justifyContent:'center',gap:4},
  cell:{height:41,width:43,justifyContent:'center',alignItems:'center',
        borderRadius:4},
  here:{borderWidth:3,borderColor:'#c2f4ad'},
  tileText:{fontSize:18,color:'#fff',fontWeight:'700'},
  minorLabel:{fontSize:11,color:'#bddac3',padding:6,
              backgroundColor:'#304956',borderRadius:6},
  choice:{padding:10,borderRadius:9,backgroundColor:'#2b4859',gap:3},
  wordRow:{flexDirection:'row',alignItems:'center',gap:8,
           paddingVertical:5},
  wordIndex:{fontSize:12,color:'#bbd4c4',width:24},
});
