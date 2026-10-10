/** Original Dragon World Codex: 128 editable systems, 256 levels each.
 * Exact world IDs are strings; hardware content != compiled executables.
 */
import React from 'react';
import {ActivityIndicator,Platform,SafeAreaView,ScrollView,StyleSheet,Text,
  TextInput,TouchableOpacity,View} from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
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
type OptionalGate={id:string;source_axis:string;source_domain:string;
  route_type:string;accessible_now:boolean;reason:string;
  earliest_turn:number;next_possible_turn:number|null;
  season_window:number;current_season:number;period:number;
  required_era:number;current_era:number;
  required_mastery:number[];current_mastery:number[]};
type OptionalAccessPreview={
  ok:boolean;optional_paths:OptionalGate[];world_must_have_an_ending:boolean;
};
type Artwork={ok:boolean;source:{
  target_id:string;native_layout:string;named_tiles:string[];
  palette:string[];tile_pixels:number[][][];
  compatible_format_encoder:boolean;emitted_into_final_rom:boolean;
  hardware_verified:boolean;digest:string;
};independent_format_verification:{verified:boolean;tiles:number}};
type StoryView={ok:boolean;actual_decisions:string[];
  original_story_world:{
    original_world_bible:{setting:string;core_conflict:string;
      perspective:string;timeline:string;staging:string;
      delayed_revelation_steps:number;originality_boundary:string};
    player:{chapters:number;observations:number;evidence:number;
      commune_support:number;wilderness_support:number;
      revelations:string[];endings:string[];scene_log:string[]};
    choices:Record<string,{available:boolean;reason:string}>;
    ended_a_story:boolean;ended_the_world:boolean;
    playable_after_story:boolean;
  };
};
type OptionalAccessProof={
  ok:boolean;gate:string;found_within_budget:boolean;
  actions:string[];actual_replay_digest?:string;
  not_a_global_unwinnability_claim:boolean;reason?:string;
};
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
  const [story,setStory]=React.useState<StoryView|null>(null);
  const [storyDecisions,setStoryDecisions]=React.useState<string[]>([]);
  const [art,setArt]=React.useState<Artwork|null>(null);
  const [access,setAccess]=React.useState<OptionalAccessPreview|null>(null);
  const [accessProof,setAccessProof]=React.useState<OptionalAccessProof|null>(null);
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
    setAccess(null);setAccessProof(null);setStory(null);setArt(null);
    setStoryDecisions([]);
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
        setAccess(null);setAccessProof(null);
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
  const startStory=async()=>{
    if(!opened||busy)return;
    const ticket=++generation.current;setBusy(true);setError('');
    try{
      const opening=await api<StoryView>('/story',{
        index:address,decisions:[],
      });
      if(!opening.ok||!opening.original_story_world.playable_after_story)
        throw Error('Original narrative engine lacks actual continuing player choices.');
      if(ticket===generation.current){
        setStory(opening);setStoryDecisions([]);
      }
    }catch(e){if(ticket===generation.current)setError(
      e instanceof Error?e.message:'Original story cannot be created.');}
    finally{if(ticket===generation.current)setBusy(false);}
  };
  const decideStory=async(decision:string)=>{
    if(!story||busy||!story.original_story_world.choices[decision]?.available||
       storyDecisions.length>=96)return;
    const next=[...storyDecisions,decision];
    const ticket=++generation.current;setBusy(true);setError('');
    try{
      const played=await api<StoryView>('/story',{
        index:address,decisions:next,
      });
      if(!played.ok||played.actual_decisions.join('|')!==next.join('|'))
        throw Error('Original story history did not replay.');
      if(ticket===generation.current){
        setStory(played);setStoryDecisions(next);
        setNotice(played.original_story_world.ended_a_story
          ?'One story ended; the game world and other choices remain playable.'
          :'Original relationship and narrative state changed.');
      }
    }catch(e){if(ticket===generation.current)setError(
      e instanceof Error?e.message:'Story route is not yet earned.');}
    finally{if(ticket===generation.current)setBusy(false);}
  };
  const inspectOptionalAccess=async()=>{
    if(!opened||busy)return;
    const ticket=++generation.current;setBusy(true);setError('');
    try{
      const result=await api<OptionalAccessPreview>(
        '/access-matrix',{index:address,domain,actions:[]});
      if(!result.ok||result.optional_paths.length!==8||
         result.world_must_have_an_ending)
        throw Error('Optional world route projection is malformed.');
      if(ticket===generation.current){
        setAccess(result);setAccessProof(null);
        setNotice('Eight real optional access contracts loaded.');
      }
    }catch(e){if(ticket===generation.current)setError(
      e instanceof Error?e.message:'Optional route inspection failed.');}
    finally{if(ticket===generation.current)setBusy(false);}
  };
  const proveOptionalAccess=async(id:string)=>{
    if(!opened||busy)return;
    const ticket=++generation.current;setBusy(true);setError('');
    try{
      const actual=await api<OptionalAccessProof>(
        '/access-proof',{index:address,gate_id:id,horizon:96});
      if(!actual.ok||!actual.not_a_global_unwinnability_claim)
        throw Error('Optional route evidence is inconsistent.');
      if(ticket===generation.current){
        setAccessProof(actual);
        setNotice(actual.found_within_budget
          ?'Actual seasonal and historical route was reached by replay.'
          :'This optional route was not proven inside 96 turns; the world remains playable.');
      }
    }catch(e){if(ticket===generation.current)setError(
      e instanceof Error?e.message:'Original optional passage proof unavailable.');}
    finally{if(ticket===generation.current)setBusy(false);}
  };
  const saveActualC99Game=async()=>{
    if(!opened||busy)return;
    const ticket=++generation.current;setBusy(true);setError('');
    try{
      const generated=await api<{
        ok:boolean;project:{
          source_name:string;source:string;source_sha256:string;
          actual_native_binary_produced:boolean;
        };
        independent_source_verification:{verified_source:boolean};
      }>('/native-desktop-source',{index:address});
      if(!generated.ok||!generated.independent_source_verification.verified_source||
         generated.project.actual_native_binary_produced||
         generated.project.source_name!=='dragon_codex_game.c'||
         !generated.project.source.includes('DRAGON_CODEX_SELFTEST_PASS')||
         !generated.project.source.includes('#define AXES 128')||
         generated.project.source.length>120000||
         !FileSystem.documentDirectory)
        throw Error('Original C99 source is invalid or mobile export unavailable.');
      const path=FileSystem.documentDirectory+'dragon-codex-'+
        opened.design.codex_digest.slice(0,16)+'.c';
      await FileSystem.writeAsStringAsync(path,generated.project.source);
      if(Platform.OS!=='web'&&await Sharing.isAvailableAsync()){
        await Sharing.shareAsync(path,{
          mimeType:'text/x-c',dialogTitle:'Export original Dragon C99 game source',
          UTI:'public.c-source',
        });
      }
      if(ticket===generation.current)setNotice(
        'Original C99 game source saved. Compile locally and run --selftest; no binary or hardware certification is implied.');
    }catch(e){if(ticket===generation.current)setError(
      e instanceof Error?e.message:'Original C99 game source cannot be exported.');}
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
  const createOriginalArt=async()=>{
    if(!opened||busy)return;
    const ticket=++generation.current;setBusy(true);setError('');
    try{
      const asset=await api<Artwork>('/tiles',{index:address,target});
      if(!asset.ok||!asset.independent_format_verification.verified||
         asset.source.named_tiles.length!==12||
         asset.source.emitted_into_final_rom||asset.source.hardware_verified)
        throw Error('Original world tile data failed native layout inspection.');
      if(ticket===generation.current){
        setArt(asset);
        setNotice('Real original platform tile bytes generated; no ROM/hardware claim.');
      }
    }catch(e){if(ticket===generation.current)setError(
      e instanceof Error?e.message:'Original platform pixels cannot be generated.');}
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
        <Text style={s.heading}>Original literary and cinematic world grammar</Text>
        <Text style={s.copy}>
          Experience original settings, point of view, interleaved eras,
          delayed revelations, ethical uncertainty and branching
          consequences. A narrative can end without ending this game.
        </Text>
        <TouchableOpacity style={s.action} disabled={busy}
          onPress={startStory}>
          <Text style={s.actionText}>Compose and play original story</Text>
        </TouchableOpacity>
        {story&&<>
          <Text style={s.heading}>
            {friendly(story.original_story_world.original_world_bible.setting)}
          </Text>
          <Text style={s.copy}>
            Conflict: {friendly(story.original_story_world.original_world_bible.core_conflict)}
            {' · '}POV {friendly(story.original_story_world.original_world_bible.perspective)}
          </Text>
          <Text style={s.hint}>
            Timeline: {friendly(story.original_story_world.original_world_bible.timeline)}
            {' · '}Presentation: {friendly(story.original_story_world.original_world_bible.staging)}
            {' · '}revelation delay: {story.original_story_world.original_world_bible.delayed_revelation_steps} steps
          </Text>
          <Text style={s.copy}>
            Evidence {story.original_story_world.player.evidence} ·
            Commune support {story.original_story_world.player.commune_support} ·
            Wilderness support {story.original_story_world.player.wilderness_support}
          </Text>
          <Text style={s.hint}>
            Endings: {story.original_story_world.player.endings.length
              ?story.original_story_world.player.endings.map(friendly).join(', ')
              :'No ending required yet'}
          </Text>
          {Object.entries(story.original_story_world.choices).map(([name,choice])=>(
            <TouchableOpacity key={name} style={[s.choice,
              (!choice.available||busy)&&s.disabled]}
              disabled={!choice.available||busy}
              onPress={()=>decideStory(name)}>
              <Text style={s.actionText}>{friendly(name)}</Text>
              <Text style={s.hint}>
                {choice.available?'A consequential real story decision':
                  friendly(choice.reason)}
              </Text>
            </TouchableOpacity>
          ))}
          <Text style={s.hint}>
            Original abstract genre grammar only; no borrowed book scene,
            film plot, dialogue, iconic character or protected game map.
          </Text>
        </>}
      </View>
      <View style={s.panel}>
        <Text style={s.heading}>Advanced conditional access matrix</Text>
        <Text style={s.copy}>
          Every world axis also owns a real optional route. Routes can
          require changing seasons, social mastery, historical progression,
          specific calendar windows or multiple prerequisites.
          A route may remain unreachable without invalidating the world.
        </Text>
        <TouchableOpacity style={s.action} disabled={busy}
          onPress={inspectOptionalAccess}>
          <Text style={s.actionText}>
            Analyze eight optional {friendly(domain)} passages
          </Text>
        </TouchableOpacity>
        {access&&access.optional_paths.map(item=>(
          <View key={item.id} style={s.axis}>
            <Text style={s.actionText}>
              {friendly(item.source_axis)} · {friendly(item.route_type)}
            </Text>
            <Text style={s.copy}>
              {friendly(item.reason)} ·
              {' '}season {item.current_season+1} / {item.season_window+1} ·
              {' '}era {item.current_era} / {item.required_era}
            </Text>
            <Text style={s.hint}>
              Masteries {item.current_mastery.join(', ')}
              {' '}/ {item.required_mastery.join(', ')} ·
              earliest turn {item.earliest_turn} ·
              window every {item.period} turns.
            </Text>
            <TouchableOpacity style={s.chip}
              disabled={busy} onPress={()=>proveOptionalAccess(item.id)}>
              <Text style={s.actionText}>
                Find actual bounded access route
              </Text>
            </TouchableOpacity>
          </View>
        ))}
        {accessProof&&<View style={s.axis}>
          <Text style={s.heading}>{friendly(accessProof.gate)}</Text>
          <Text style={s.copy}>
            {accessProof.found_within_budget
              ?'Proved by '+accessProof.actions.length+' real decisions.'
              :'Not proven in the bounded search. Not a world failure.'}
          </Text>
          {accessProof.found_within_budget&&
            <Text style={s.hint}>
              Source replay {accessProof.actual_replay_digest?.slice(0,22)}…
            </Text>}
        </View>}
      </View>
      <View style={s.panel}>
        <Text style={s.heading}>Playable C99 world game source</Text>
        <Text style={s.copy}>
          Export an original interactive desktop game with 128 trained
          abilities, sixteen temporal travel gates, endless exploration
          and a sixteen-gate executable self-test. This is genuine source
          code, not a fake binary for unsupported hardware.
        </Text>
        <TouchableOpacity style={s.action} disabled={busy}
          onPress={saveActualC99Game}>
          <Text style={s.actionText}>Save and share original C99 game</Text>
        </TouchableOpacity>
        <Text style={s.hint}>
          Linux/macOS toolchains: cc -std=c99 dragon_codex_game.c -o dragon_codex
          and then run ./dragon_codex --selftest. Windows requires a
          compatible C99 compiler. Hardware SDK releases remain separate.
        </Text>
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
                onPress={()=>{setTarget(item.target);setPack(null);setArt(null);}}>
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
          <TouchableOpacity style={s.chip} disabled={busy}
            onPress={createOriginalArt}>
            <Text style={s.actionText}>Generate real original world tiles</Text>
          </TouchableOpacity>
          {art&&<View style={s.axis}>
            <Text style={s.copy}>
              {art.source.named_tiles.length} original 8×8 tiles
              {' · '}{art.source.native_layout}
            </Text>
            <View style={s.chips}>
              {art.source.tile_pixels.map((pixels,tile)=>(
                <View key={art.source.named_tiles[tile]} style={s.artTile}>
                  <Text style={s.small}>{friendly(art.source.named_tiles[tile])}</Text>
                  {pixels.map((line,row)=>(
                    <View key={row} style={s.artRow}>
                      {line.map((color,col)=>(
                        <View key={col} style={{
                          width:9,height:9,
                          backgroundColor:art.source.palette[color]||'#445',
                        }}/>
                      ))}
                    </View>
                  ))}
                </View>
              ))}
            </View>
            <Text style={s.hint}>
              Native tile format source checked. Physical console ROM: not yet.
            </Text>
          </View>}
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
 artTile:{padding:7,borderRadius:7,backgroundColor:'#243e4b',gap:3},
 artRow:{flexDirection:'row'},
});
