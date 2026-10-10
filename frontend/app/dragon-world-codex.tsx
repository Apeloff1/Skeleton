/** Original Dragon World Codex: 128 editable systems, 256 levels each.
 * Exact world IDs are strings; hardware content != compiled executables.
 */
import React from 'react';
import {ActivityIndicator,SafeAreaView,ScrollView,StyleSheet,Text,
  TextInput,TouchableOpacity,View} from 'react-native';
import StudioLoginGate,{useStudioAuth} from '../src/auth/StudioLoginGate';
import {authHeaders} from '../src/auth/gameforgeAuth';
import {API_BASE} from '../utils/apiBase';

const API=(API_BASE||'').replace(/\/$/,'')+
  '/api/dragon-academy/native/production/worlds/codex';
const friendly=(value:string)=>value.replace(/_/g,' ');
type Gate={name:string;domain:string;available:boolean;earned:boolean;
  reason:string;next_window_turn:number;cycle_period:number;
  axis_required:string[];mastery_current:number[];mastery_required:number[]};
type World={source_address:string;world_style:string;lifecycle:string;
  current_turn:number;world_era:number;current_position:number[];
  no_mandatory_win:boolean;history_digest:string;
  player_resources:Record<string,number>;journeys:string[];
  gates:Gate[];
  available_actions:Array<{name:string;available:boolean;kind:string}>;
  domain_progress:Record<string,{reputation:number;axes:Record<string,number>}>;
  axes_level_map:Record<string,number>|null;
  terrain:{codex_terrain:Record<string,{energy:number;instability:number;
    hazard:number;resource_supply:number;clock:number}>}};
type Inspect={ok:boolean;design:{decimal_index:string;values:number[];
  codex_digest:string};game:World};
type Cap={ok:boolean;codex:{domains:number;axes:number;levels_per_axis:number;
  grouped_axes:Record<string,string[]>;
  total_exact_reversible_original_world_addresses:string};
  registered_native_targets:number};
type Platform={target:string;cohort:string;status:string;
  capability:{active_axes:number;deferred_axes:string[];
    rooms_per_chunk:number;level_buckets:number}};
type Platforms={ok:boolean;platforms:Platform[];
  available_catalog_targets:number};
async function api<T>(path:string,body?:object):Promise<T>{
  const response=await fetch(API+path,{
    method:body?'POST':'GET',cache:'no-store',
    headers:authHeaders(body?{'Content-Type':'application/json'}:{}),
    ...(body?{body:JSON.stringify(body)}:{}),
  });
  if(!response.ok)throw Error(response.status===403
    ?'Creator permission required.':response.status===422
    ?'Original world action, route, or content rule failed validation.'
    :'World Codex service unavailable.');
  return response.json() as Promise<T>;
}
function Editor(){
  const {role}=useStudioAuth();
  const editor=role==='editor'||role==='admin';
  const [cap,setCap]=React.useState<Cap|null>(null);
  const [address,setAddress]=React.useState('0');
  const [opened,setOpened]=React.useState<Inspect|null>(null);
  const [world,setWorld]=React.useState<World|null>(null);
  const [history,setHistory]=React.useState<string[]>([]);
  const [domain,setDomain]=React.useState('geology');
  const [guide,setGuide]=React.useState<string[]>([]);
  const [platforms,setPlatforms]=React.useState<Platforms|null>(null);
  const [target,setTarget]=React.useState('game_boy');
  const [pack,setPack]=React.useState<{
    package:{target:string;content_sha256:string;
      projection:{active_axes:number;deferred_axes:string[];
        hardware_binary_compiled:boolean};
      chunks:Array<{chunk:number;identity:string;rooms:unknown[]}>};
    independent_verification:{verified:boolean;room_count:number};
  }|null>(null);
  const [busy,setBusy]=React.useState(false);
  const [error,setError]=React.useState('');
  const [notice,setNotice]=React.useState('');
  const generation=React.useRef(0);
  React.useEffect(()=>{
    let live=true;
    api<Cap>('/capabilities').then(result=>{if(live)setCap(result);})
      .catch(()=>{if(live)setCap(null);});
    return ()=>{live=false;};
  },[]);
  const reset=()=>{
    generation.current++;setOpened(null);setWorld(null);
    setHistory([]);setGuide([]);setPlatforms(null);setPack(null);
    setError('');setNotice('');
  };
  const load=async(index:string)=>{
    if(!editor||busy||index.length>400||
      !/^(0|[1-9][0-9]*)$/.test(index))return;
    const ticket=++generation.current;setBusy(true);setError('');
    try{
      const result=await api<Inspect>('/inspect',{index});
      if(!result.ok||result.design.decimal_index!==index||
          result.design.values.length!==128||result.game.gates.length!==16)
        throw Error('World source identity or playable rules failed verification.');
      if(ticket===generation.current){
        setOpened(result);setWorld(result.game);setAddress(index);
        setHistory([]);setGuide([]);setPlatforms(null);setPack(null);
      }
    }catch(e){if(ticket===generation.current)setError(
      e instanceof Error?e.message:'Cannot generate this original world.');}
    finally{if(ticket===generation.current)setBusy(false);}
  };
  const change=async(axis:string,value:number)=>{
    if(!opened||busy||value<0||value>255)return;
    const ticket=++generation.current;setBusy(true);setError('');
    try{
      const result=await api<{ok:boolean;new_decimal_index:string}>(
        '/edit',{index:address,changes:{[axis]:value}});
      if(!result.ok)throw Error('Game axis edit not accepted.');
      const next=await api<Inspect>('/inspect',{
        index:result.new_decimal_index,
      });
      if(!next.ok||next.design.decimal_index!==result.new_decimal_index)
        throw Error('Changed game design did not round-trip.');
      if(ticket===generation.current){
        setAddress(result.new_decimal_index);setOpened(next);setWorld(next.game);
        setHistory([]);setGuide([]);setPlatforms(null);setPack(null);
        setNotice('Actual environment and access conditions regenerated.');
      }
    }catch(e){if(ticket===generation.current)setError(
      e instanceof Error?e.message:'World edit failed.');}
    finally{if(ticket===generation.current)setBusy(false);}
  };
  const act=async(command:string)=>{
    if(!world||busy||history.length>=96||!world.available_actions.some(
       x=>x.name===command&&x.available))return;
    const ticket=++generation.current;setBusy(true);setError('');
    const next=[...history,command];
    try{
      const result=await api<{ok:boolean;game:World;replayed_actions:string[]}>(
        '/play',{index:address,actions:next});
      if(!result.ok||result.game.source_address!==address||
        result.replayed_actions.join('|')!==next.join('|'))
        throw Error('World execution receipt does not match player decisions.');
      if(ticket===generation.current){
        setHistory(next);setWorld(result.game);
        setNotice(result.game.journeys.includes(command)
          ?'Earned passage successfully traversed.'
          :'Actual story/clock/world mastery evolved.');
      }
    }catch(e){if(ticket===generation.current)setError(
      e instanceof Error?e.message:'This passage is still locked.');}
    finally{if(ticket===generation.current)setBusy(false);}
  };
  const rewind=async()=>{
    if(!opened||!history.length||busy)return;
    const ticket=++generation.current;setBusy(true);setError('');
    const next=history.slice(0,-1);
    try{
      const result=await api<{ok:boolean;game:World;replayed_actions:string[]}>(
        '/play',{index:address,actions:next});
      if(!result.ok||result.replayed_actions.join('|')!==next.join('|'))
        throw Error('Prior game state cannot be replayed.');
      if(ticket===generation.current){setWorld(result.game);setHistory(next);}
    }catch(e){if(ticket===generation.current)setError(
      e instanceof Error?e.message:'Cannot undo game movement.');}
    finally{if(ticket===generation.current)setBusy(false);}
  };
  const witness=async()=>{
    if(!world||busy)return;
    const ticket=++generation.current;setBusy(true);setError('');
    try{
      const proof=await api<{ok:boolean;actual_commands:string[];
        completed_non_mandatory_passage:boolean}>(
        '/unlock-witness',{index:address,domain});
      if(!proof.ok||!proof.completed_non_mandatory_passage)
        throw Error('Original passage lacks an actual traversal proof.');
      if(ticket===generation.current){
        setGuide(proof.actual_commands);
        setNotice('Real learning, waiting, and passage witnessed.');
      }
    }catch(e){if(ticket===generation.current)setError(
      e instanceof Error?e.message:'Cannot prove this passage.');}
    finally{if(ticket===generation.current)setBusy(false);}
  };
  const inspectPlatforms=async()=>{
    const ticket=++generation.current;setBusy(true);setError('');
    try{
      const result=await api<Platforms>('/platforms',{index:address});
      if(!result.ok||!result.platforms.length)throw Error(
        'No documented platform content budgets returned.');
      if(ticket===generation.current)setPlatforms(result);
    }catch(e){if(ticket===generation.current)setError(
      e instanceof Error?e.message:'Cannot evaluate platform options.');}
    finally{if(ticket===generation.current)setBusy(false);}
  };
  const compile=async()=>{
    const ticket=++generation.current;setBusy(true);setError('');
    try{
      const result=await api<NonNullable<typeof pack>>(
        '/compile-target',{index:address,target,chunks:2});
      if(!result.independent_verification.verified||
         result.package.projection.hardware_binary_compiled)
        throw Error('Native game content source wrongly asserted compiled status.');
      if(ticket===generation.current)setPack(result);
    }catch(e){if(ticket===generation.current)setError(
      e instanceof Error?e.message:'World exceeds platform content constraints.');}
    finally{if(ticket===generation.current)setBusy(false);}
  };
  const axes=cap?.codex.grouped_axes[domain]||[];
  const gate=world?.gates.find(item=>item.domain===domain);
  return <SafeAreaView style={s.root}><ScrollView contentContainerStyle={s.page}>
    <Text style={s.title}>Dragon · World Codex</Text>
    <Text style={s.copy}>
      Deep original world systems, dynamic mazes, civilizations, time,
      alternate access and postgame. A world can remain playable indefinitely.
    </Text>
    {cap&&<View style={s.panel}>
      <Text style={s.heading}>
        {cap.codex.axes} axes · {cap.codex.levels_per_axis} levels
        {' · '}{cap.codex.domains} interconnected systems
      </Text>
      <Text style={s.hint}>Exact reversible world configurations:</Text>
      <Text selectable style={s.big}>
        {cap.codex.total_exact_reversible_original_world_addresses}
      </Text>
      <Text style={s.hint}>
        These are generator addresses, not finished games or cleared IP.
        Hardware and gameplay certification are separate.
      </Text>
    </View>}
    <View style={s.panel}>
      <Text style={s.heading}>Exact world address (decimal string)</Text>
      <TextInput style={s.input} value={address}
        maxLength={400} keyboardType="number-pad"
        editable={editor&&!busy}
        onChangeText={v=>{setAddress(v);reset();}}/>
      <TouchableOpacity style={s.action} disabled={!editor||busy}
        onPress={()=>load(address)}>
        <Text style={s.actionText}>Generate original world</Text>
      </TouchableOpacity>
    </View>
    {busy&&<ActivityIndicator color="#b7f2cb"/>}
    {world&&opened&&<>
      <View style={s.panel}>
        <Text style={s.heading}>
          {friendly(world.world_style)} · {friendly(world.lifecycle)}
        </Text>
        <Text style={s.copy}>
          Turn {world.current_turn} · era {world.world_era}
          {' · '}({world.current_position.join(', ')})
        </Text>
        <Text style={s.hint}>
          {world.no_mandatory_win?'A formal victory is not required.':
           'This campaign uses a completion-goal lifecycle.'}
        </Text>
        <Text style={s.copy}>
          Stamina {world.player_resources.stamina} ·
          Water {world.player_resources.hydration} ·
          Knowledge {world.player_resources.knowledge}
        </Text>
        <View style={s.chips}>
          <TouchableOpacity style={s.chip} disabled={busy||!history.length}
            onPress={rewind}><Text style={s.actionText}>Undo</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.chip} disabled={busy}
            onPress={()=>{setWorld(opened.game);setHistory([]);setGuide([]);}}>
            <Text style={s.actionText}>Restart</Text>
          </TouchableOpacity>
        </View>
      </View>
      <View style={s.panel}>
        <Text style={s.heading}>Choose original world system</Text>
        <View style={s.chips}>
          {Object.keys(cap?.codex.grouped_axes||{}).map(key=>(
            <TouchableOpacity key={key} onPress={()=>{setDomain(key);setGuide([]);}}
              disabled={busy} style={[s.chip,domain===key&&s.selected]}>
              <Text style={s.small}>{friendly(key)}</Text>
            </TouchableOpacity>
          ))}
        </View>
        {axes.map(axis=>{
          const level=world.axes_level_map?.[axis]??0;
          const mastery=world.domain_progress[domain]?.axes[axis]??0;
          return <View key={axis} style={s.axis}>
            <Text style={s.actionText}>
              {friendly(axis)} · {level}/255
            </Text>
            <Text style={s.hint}>Achieved mastery {mastery}</Text>
            <View style={s.chips}>
              <TouchableOpacity style={s.chip}
                disabled={busy||level===0}
                onPress={()=>change(axis,level-1)}>
                <Text style={s.small}>−1</Text>
              </TouchableOpacity>
              {[0,32,64,128,192,255].map(value=>(
                <TouchableOpacity key={value}
                  style={[s.chip,value===level&&s.selected]}
                  disabled={busy} onPress={()=>change(axis,value)}>
                  <Text style={s.small}>{value}</Text>
                </TouchableOpacity>
              ))}
              <TouchableOpacity style={s.chip}
                disabled={busy||level===255}
                onPress={()=>change(axis,level+1)}>
                <Text style={s.small}>+1</Text>
              </TouchableOpacity>
            </View>
            <TouchableOpacity style={s.choice}
              disabled={busy||history.length>=96}
              onPress={()=>act('study_'+axis)}>
              <Text style={s.actionText}>Train {friendly(axis)}</Text>
            </TouchableOpacity>
          </View>;
        })}
      </View>
      <View style={s.panel}>
        <Text style={s.heading}>Earned, delayed and shifting routes</Text>
        {gate&&<>
          <Text style={s.copy}>
            {friendly(gate.name)} · {friendly(gate.reason)}
            {' · '}next window: turn {gate.next_window_turn}
          </Text>
          <Text style={s.hint}>
            {gate.axis_required.map((name,i)=>
              friendly(name)+': '+gate.mastery_current[i]+'/'+
              gate.mastery_required[i]).join(' · ')}
          </Text>
          <View style={s.chips}>
            <TouchableOpacity style={s.chip}
              disabled={busy||history.length>=96}
              onPress={()=>act('wait_world')}>
              <Text style={s.actionText}>Wait for changes</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[s.chip,!gate.available&&s.disabled]}
              disabled={!gate.available||busy||history.length>=96}
              onPress={()=>act(gate.name)}>
              <Text style={s.actionText}>Traverse open passage</Text>
            </TouchableOpacity>
          </View>
          <TouchableOpacity style={s.action} disabled={busy}
            onPress={witness}>
            <Text style={s.actionText}>Prove real unlock route</Text>
          </TouchableOpacity>
          {!!guide.length&&<>
            <Text style={s.copy}>
              {guide.length} source-replayed steps to unlock and traverse.
            </Text>
            <Text style={s.hint}>
              For a fresh-world proof, restart before following the guide.
            </Text>
            <TouchableOpacity style={s.action} disabled={busy||
              history.length>=guide.length}
              onPress={()=>{const next=guide[history.length];
                if(world.available_actions.some(x=>x.name===next&&x.available))
                  act(next);}}>
              <Text style={s.actionText}>
                Execute next proved step {history.length}/{guide.length}
              </Text>
            </TouchableOpacity>
          </>}
        </>}
        {Object.entries(world.terrain.codex_terrain).map(([name,values])=>(
          <Text key={name} style={s.hint}>
            {friendly(name)}: hazard {values.hazard} ·
            resources {values.resource_supply} ·
            instability {values.instability} · clock {values.clock}
          </Text>
        ))}
      </View>
      <View style={s.panel}>
        <Text style={s.heading}>Hardware-specific world content</Text>
        <Text style={s.copy}>
          Select a registered console/PC. Quantize authored controls,
          limit active mechanics and produce deterministic original chunks.
          A content pack is not a compiled ROM.
        </Text>
        <TouchableOpacity style={s.action} disabled={busy}
          onPress={inspectPlatforms}>
          <Text style={s.actionText}>Compare platform capabilities</Text>
        </TouchableOpacity>
        {platforms&&<>
          <Text style={s.hint}>
            {platforms.available_catalog_targets} native targets registered.
          </Text>
          <View style={s.chips}>
            {platforms.platforms.map(item=>(
              <TouchableOpacity key={item.target}
                style={[s.chip,target===item.target&&s.selected]}
                disabled={busy}
                onPress={()=>{setTarget(item.target);setPack(null);}}>
                <Text style={s.small}>{friendly(item.target)}</Text>
              </TouchableOpacity>
            ))}
          </View>
          {platforms.platforms.find(x=>x.target===target)&&
            <Text style={s.copy}>
              {target} ·
              {' '}{platforms.platforms.find(x=>x.target===target)?.capability.active_axes}
              {' '}axes in source projection
            </Text>}
          <TouchableOpacity style={s.action} disabled={busy}
            onPress={compile}>
            <Text style={s.actionText}>
              Compile and verify two world-content chunks
            </Text>
          </TouchableOpacity>
        </>}
        {pack&&<View style={s.axis}>
          <Text style={s.copy}>
            {pack.independent_verification.room_count} generated rooms,
            {pack.package.projection.active_axes} active controls,
            {pack.package.projection.deferred_axes.length} deferred controls.
          </Text>
          <Text style={s.hint}>
            Verified original content: yes. Native binary: no.
            Hardware playtest: no.
          </Text>
          <Text selectable style={s.hint}>
            Content receipt {pack.package.content_sha256}
          </Text>
        </View>}
      </View>
    </>}
    {!!error&&<Text style={s.warning}>{error}</Text>}
    {!!notice&&<Text style={s.success}>{notice}</Text>}
    <Text style={s.hint}>
      Deep abstract original game-state simulation. Original homebrew
      content is not a finished renderer, all-console compiler or licensed
      commercial release. Playability and originality remain distinct.
    </Text>
  </ScrollView></SafeAreaView>;
}
export default function DragonWorldCodex(){
  return <StudioLoginGate><Editor/></StudioLoginGate>;
}
const s=StyleSheet.create({
 root:{flex:1,backgroundColor:'#111b27'},
 page:{padding:14,paddingBottom:80,gap:12,maxWidth:880,width:'100%',alignSelf:'center'},
 title:{fontSize:25,fontWeight:'700',color:'#f4faf3'},
 heading:{fontSize:16,fontWeight:'700',color:'#d4f3e0'},
 copy:{fontSize:13,lineHeight:20,color:'#c4d8d0'},
 hint:{fontSize:12,lineHeight:19,color:'#a8c2b6'},
 small:{fontSize:12,color:'#eafff0'},
 big:{fontSize:11,color:'#b3edc2',lineHeight:17},
 warning:{fontSize:13,color:'#ffc0ae'},
 success:{fontSize:13,color:'#b9efc8'},
 panel:{padding:13,borderRadius:11,backgroundColor:'#1c3040',gap:9},
 axis:{borderBottomWidth:1,borderColor:'#425b63',paddingVertical:10,gap:6},
 input:{padding:12,color:'#fff',backgroundColor:'#27414a',
   borderWidth:1,borderColor:'#6b9483',borderRadius:9},
 chips:{flexDirection:'row',flexWrap:'wrap',gap:6},
 chip:{padding:9,borderRadius:8,backgroundColor:'#315363'},
 selected:{backgroundColor:'#397d58'},
 choice:{padding:10,borderRadius:8,backgroundColor:'#345867'},
 action:{padding:12,borderRadius:9,backgroundColor:'#357a57',alignItems:'center'},
 actionText:{fontSize:13,color:'#f3fff5',fontWeight:'700'},
 disabled:{opacity:0.4},
});
