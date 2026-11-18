/**
 * Original-donor V7: exact-GLB joint traces from the actual Three AnimationMixer.
 *
 * Offline and read-only. Never loads textures, creates a renderer, instantiates
 * a crawler, touches active assets, invokes networking or approves collision.
 * Run with the Three 0.186 dependency installed in frontend/node_modules.
 */
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import * as THREE from 'three';

export const DONOR='c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a';
export const V7=Object.freeze({
  pathfinder:Object.freeze({bytes:114696520,sha256:'27e1a6a22fad045d26edf4dc2813292829aab8dcaa129fac407f80ee83229ade'}),
  archivist:Object.freeze({bytes:114819168,sha256:'f224671cf6d0886365f081faa29f9dcf2509d52211677d2a83152a389389acaf'}),
});
export const FADE_SECONDS=.22;
export const TRANSITIONS=Object.freeze([
  Object.freeze(['ground-idle-1','takeoff-1']),
  Object.freeze(['takeoff-1','orbit-01']),
  Object.freeze(['orbit-01','landing-1']),
  Object.freeze(['landing-1','ground-idle-1']),
  Object.freeze(['orbit-01','orbit-02']),
  Object.freeze(['orbit-02','landing-1']),
]);
const MAX_JSON=32*1024*1024;
const MAX_TRACK_KEYS=15000;
const EXPECTED_JOINTS=108;
const EXPECTED_CLIPS=381;
function ensure(ok,why){if(!ok)throw new Error(why);}
function hash(data){return createHash('sha256').update(data).digest('hex');}
function parseArgs(argv){
  const args={};
  for(let i=0;i<argv.length;i++){
    const key=argv[i];
    ensure(['--stage','--model','--output','--samples'].includes(key) && args[key]===undefined && i+1<argv.length,
           'Unrecognized, duplicated, or missing operator argument '+key);
    args[key]=argv[++i];
  }
  ensure(Object.keys(args).length>=3 && args['--stage'] && args['--model'] && args['--output'],
         'Required: --stage <pathfinder|archivist> --model <exact GLB> --output <unused JSON> [--samples 9]');
  const samples=args['--samples']===undefined?9:Number(args['--samples']);
  ensure(Number.isSafeInteger(samples) && samples>=3 && samples<=33 && samples%2===1,
         'Invalid odd bounded sample count (3–33)');
  return {stage:args['--stage'],model:args['--model'],output:args['--output'],samples};
}
export function parseOriginal(buffer,stage){
  const pin=V7[stage];
  ensure(pin,'Unknown original V7 model stage');
  ensure(Buffer.isBuffer(buffer) && buffer.byteLength===pin.bytes && hash(buffer)===pin.sha256,
         'Exact original V7 GLB byte or SHA-256 custody mismatch');
  return parseDocument(buffer,stage);
}
export function parseDocument(buffer,stage){
  ensure(Buffer.isBuffer(buffer) && buffer.length>=32,'Truncated GLB');
  ensure(buffer.toString('ascii',0,4)==='glTF' && buffer.readUInt32LE(4)===2 &&
         buffer.readUInt32LE(8)===buffer.length,'Unqualified glTF header');
  const n=buffer.readUInt32LE(12);
  ensure(n>=4 && n<=MAX_JSON && n%4===0 && n+28<=buffer.length &&
         buffer.readUInt32LE(16)===0x4e4f534a,'Unqualified glTF JSON chunk');
  const binary=n+28, length=buffer.readUInt32LE(n+20);
  ensure(buffer.readUInt32LE(n+24)===0x004e4942 && binary+length===buffer.length,
         'GLB has external or unbounded binary');
  const document=JSON.parse(buffer.subarray(20,20+n).toString('utf8'));
  ensure(document?.asset?.version==='2.0' && document?.extras?.stage===stage &&
         document?.extras?.donorSha256===DONOR && document?.skins?.length===1 &&
         document.skins[0].joints?.length===EXPECTED_JOINTS &&
         document?.animations?.length===EXPECTED_CLIPS,'Wrong original V7 donor, rig or animation catalogue');
  const correction=document.extras.orbit02ClearanceCorrection;
  ensure(correction?.schema==='skeleton.emerald.orbit02-tail-clearance.v1' &&
         correction.clip==='orbit-02' && correction.joint_index===34 &&
         correction.local_y_radians===.18 && correction.modified_keyframes===160 &&
         correction.release_qualified===false && correction.artist_approved===false &&
         correction.physical_rtx_verified===false &&
         correction.continuous_collision_qualified===false,'Unqualified V7 correction or false acceptance');
  ensure(document.buffers?.length===1 && !document.buffers[0].uri &&
         Number.isSafeInteger(document.buffers[0].byteLength) &&
         document.buffers[0].byteLength<=length && length-document.buffers[0].byteLength<=3,
         'External source or unknown embedded buffer declaration');
  ensure(document.nodes?.length===109 &&
         Array.isArray(document.bufferViews) && Array.isArray(document.accessors) &&
         document.scene===0 && Array.isArray(document.scenes) &&
         document.scenes.length===1 &&
         JSON.stringify(document.scenes[0].nodes)==='[0,92]' &&
         Array.isArray(document.meshes) && document.meshes.length===1,
         'Original V7 109-node scene/rig census changed');
  const palette=document.skins[0].joints;
  ensure(palette.length===108 &&
         palette.every((node,index)=>node===(index<92?index:index+1)) &&
         document.skins[0].skeleton===0 &&
         document.skins[0].inverseBindMatrices===0 &&
         document.nodes[0]?.name==='root' &&
         document.nodes[92]?.name==='Emerald continuous reconstructed character' &&
         document.nodes[92]?.mesh===0 &&
         document.nodes[92]?.skin===0 &&
         !('matrix' in document.nodes[92]) &&
         !('translation' in document.nodes[92]) &&
         !('rotation' in document.nodes[92]) &&
         !('scale' in document.nodes[92]) &&
         !('children' in document.nodes[92]),
         'Original skinned donor mesh node 92 or corrective 108-joint palette changed');
  const names=document.animations.map(a=>a.name);
  ensure(new Set(names).size===EXPECTED_CLIPS &&
         TRANSITIONS.flat().every(name=>names.includes(name)) &&
         names[names.length-1]==='growth-'+stage+'-to-'+(stage==='pathfinder'?'archivist':'hoarder'),
         'Missing original motion or growth clip');
  return {document,buffer,binary,length};
}
export function accessor(original,index,kind){
  const {document,buffer,binary}=original;
  const access=document.accessors[index];
  ensure(access && access.componentType===5126 && access.type===kind &&
         Number.isSafeInteger(access.count) && access.count>=2 &&
         access.count<=MAX_TRACK_KEYS && access.sparse===undefined &&
         Number.isSafeInteger(access.bufferView),'Unqualified float32 animation accessor');
  const components=kind==='SCALAR'?1:kind==='VEC3'?3:kind==='VEC4'?4:0;
  ensure(components!==0,'Unsupported glTF accessor kind');
  const view=document.bufferViews[access.bufferView];
  ensure(view && view.buffer===0 && view.byteStride===undefined,
         'Unqualified strided or external accessor');
  const local=access.byteOffset??0, offset=view.byteOffset??0, size=access.count*components*4;
  ensure(Number.isSafeInteger(local) && Number.isSafeInteger(offset) &&
         Number.isSafeInteger(view.byteLength) && local>=0 && offset>=0 &&
         size<=view.byteLength-local && size<=document.buffers[0].byteLength-offset-local,
         'Out-of-bounds original animation accessor');
  const out=new Float32Array(access.count*components);
  const at=binary+offset+local;
  for(let i=0;i<out.length;i++){
    const v=buffer.readFloatLE(at+i*4);
    ensure(Number.isFinite(v),'Nonfinite original animation sample');
    out[i]=v;
  }
  return out;
}
export function buildBones(Three,original){
  const {document}=original;
  const joints=document.skins[0].joints;
  const nodes=document.nodes;
  ensure(joints.length===EXPECTED_JOINTS &&
         joints.every(index=>Number.isSafeInteger(index) && index>=0 && index<nodes.length) &&
         new Set(joints).size===EXPECTED_JOINTS,
         'Missing or duplicated source glTF skin node');
  // Actual donor has 109 nodes: bone 0 is named 'root', mesh node 92
  // is named 'Emerald continuous reconstructed character' and is not a
  // skin joint; node 108 is a corrective bone. Use skin palette indices.
  const nodeToJoint=new Map(joints.map((node,index)=>[node,index]));
  const bones=joints.map((nodeIndex,jointIndex)=>{
    const node=nodes[nodeIndex];
    ensure(node && typeof node.name==='string' && node.name.length>0 &&
           node.name.length<=256 && !node.matrix && node.mesh===undefined,
           'Unqualified original skinned glTF joint');
    const bone=new Three.Bone();
    bone.name='emerald_joint_'+jointIndex;
    bone.userData.originalDonorName=node.name;
    bone.userData.originalGLTFNodeIndex=nodeIndex;
    const t=node.translation??[0,0,0],r=node.rotation??[0,0,0,1],s=node.scale??[1,1,1];
    ensure([t,r,s].every(v=>Array.isArray(v)) &&
           [t,r,s].map(v=>v.length).join(',')==='3,4,3' &&
           [...t,...r,...s].every(Number.isFinite) &&
           Math.abs(new Three.Quaternion(...r).length()-1)<2e-5 &&
           s.every(value=>Math.abs(value-1)<1e-8),
           'Unqualified source bind transform or unsupported joint scale');
    bone.position.fromArray(t);bone.quaternion.fromArray(r);bone.scale.fromArray(s);
    return bone;
  });
  const parents=Array(EXPECTED_JOINTS).fill(-1);
  for(let i=0;i<bones.length;i++){
    const children=nodes[joints[i]].children??[];
    ensure(Array.isArray(children) && children.length<=EXPECTED_JOINTS,
           'Unbounded source skeleton hierarchy');
    for(const gltfChild of children){
      ensure(Number.isSafeInteger(gltfChild) && gltfChild>=0 &&
             gltfChild<nodes.length,'Invalid original skeleton child');
      const child=nodeToJoint.get(gltfChild);
      if(child===undefined)continue;
      ensure(child!==i && parents[child]===-1 && child>i,
             'Cyclic or duplicate source skin joint parent');
      parents[child]=i;
      bones[i].add(bones[child]);
    }
  }
  ensure(parents[0]===-1 && parents.slice(1).every(x=>x!==-1),
         'Missing original skin joint parent or disconnected hierarchy');
  const root=new Three.Group();
  root.name='V7 source only mixer root';
  root.add(bones[0]);root.updateMatrixWorld(true);
  return {root,bones,parents,nodeToJoint};
}
export function clipFromDocument(Three,original,bones,name){
  const {document}=original;
  const a=document.animations.find(clip=>clip.name===name);
  const permitted={
    'ground-idle-1':{rotation:97,translation:17},
    'takeoff-1':{rotation:106,translation:18},
    'orbit-01':{rotation:71,translation:17},
    'orbit-02':{rotation:71,translation:17},
    'landing-1':{rotation:105,translation:18},
  };
  const census=permitted[name];
  const count=census&&census.rotation+census.translation;
  ensure(a && count && Array.isArray(a.channels) &&
         a.channels.length===count && Array.isArray(a.samplers) &&
         a.samplers.length===count,
         'Expected source-specific motion track census for '+name);
  const palette=new Map(document.skins[0].joints.map((node,i)=>[node,i]));
  const used=new Set(),tracks=[];
  for(const channel of a.channels){
    const node=channel.target?.node,prop=channel.target?.path;
    const joint=palette.get(node);
    ensure(joint!==undefined && Number.isSafeInteger(joint) &&
           ['rotation','translation'].includes(prop) &&
           Number.isSafeInteger(channel.sampler) && channel.sampler>=0 &&
           channel.sampler<a.samplers.length,'Unsupported source track target');
    const identity=joint+':'+prop;
    ensure(!used.has(identity),'Duplicate source joint/property animation channel');
    used.add(identity);
    const sampler=a.samplers[channel.sampler];
    ensure((sampler.interpolation??'LINEAR')==='LINEAR','Unreviewed source interpolation');
    const times=accessor(original,sampler.input,'SCALAR');
    const values=accessor(original,sampler.output,prop==='rotation'?'VEC4':'VEC3');
    const stride=prop==='rotation'?4:3;
    ensure(values.length===times.length*stride &&
           times[0]===0 && times[times.length-1]>0 &&
           times.every((v,i)=>i===0||v>times[i-1]),
           'Nonmonotonic original source animation timebase');
    if(prop==='rotation'){
      for(let i=0;i<values.length;i+=4)
        ensure(Math.abs(Math.hypot(...values.subarray(i,i+4))-1)<2e-4,
               'Unqualified unnormalized source track quaternion');
      tracks.push(new Three.QuaternionKeyframeTrack(bones[joint].name+'.quaternion',times,values));
    }else{
      tracks.push(new Three.VectorKeyframeTrack(bones[joint].name+'.position',times,values));
    }
  }
  ensure(Array.from(used).filter(x=>x.endsWith(':rotation')).length===census.rotation &&
         Array.from(used).filter(x=>x.endsWith(':translation')).length===census.translation,
         'Original stage-specific rotation/translation track census differs');
  const clip=new Three.AnimationClip(name,-1,tracks);
  ensure(Number.isFinite(clip.duration) && clip.duration>=FADE_SECONDS &&
         clip.tracks.length===count,
         'Source motion clip shorter than reviewed crossfade envelope');
  return clip;
}
function tracePose(bones,oldAction,newAction,alpha,route){
  const joints=bones.map((bone,index)=>{
    bone.updateWorldMatrix(true,false);
    const q=bone.quaternion.toArray();
    const t=bone.position.toArray();
    const m=bone.matrixWorld.elements.slice();
    ensure([...q,...t,...m].every(Number.isFinite),'Nonfinite real Three mixer bone data');
    const norm=Math.hypot(...q);
    ensure(Math.abs(norm-1)<2e-4,'Unqualified real Three mixer quaternion');
    return {joint:index,local_translation:t,local_quaternion:q,world_matrix:m};
  });
  const priorWeight=oldAction.getEffectiveWeight();
  const nextWeight=newAction.getEffectiveWeight();
  ensure(Number.isFinite(priorWeight)&&Number.isFinite(nextWeight)&&
         priorWeight>=-1e-7&&nextWeight>=-1e-7&&
         priorWeight<=1+1e-7&&nextWeight<=1+1e-7,'Invalid Three action weights');
  return {
    from_clip:route[0],to_clip:route[1],alpha,
    source_old_time_s:oldAction.time,
    source_new_time_s:newAction.time,
    outgoing_weight:priorWeight,
    incoming_weight:nextWeight,
    joints,
  };
}
export function trace(Three,original,stage,sampleCount=9){
  ensure(V7[stage] && Number.isInteger(sampleCount) &&
         sampleCount>=3&&sampleCount<=33&&sampleCount%2===1,
         'Unqualified source stage or trace density');
  const routes=[];
  for(const route of TRANSITIONS){
    const {root,bones}=buildBones(Three,original);
    const outgoing=clipFromDocument(Three,original,bones,route[0]);
    const incoming=clipFromDocument(Three,original,bones,route[1]);
    const mixer=new Three.AnimationMixer(root);
    let prior=mixer.clipAction(outgoing),next=mixer.clipAction(incoming);
    ensure(prior!==next,'Identical incoming and outgoing motion not separately qualified');
    const repeat=(name)=>name.startsWith('ground-')||name.startsWith('orbit-');
    prior.reset().setLoop(repeat(route[0])?Three.LoopRepeat:Three.LoopOnce,
                          repeat(route[0])?Infinity:1);
    prior.clampWhenFinished=!repeat(route[0]);
    prior.setEffectiveTimeScale(1).setEffectiveWeight(1);
    prior.time=outgoing.duration-FADE_SECONDS;
    prior.play();
    mixer.update(0);
    next.reset().setLoop(repeat(route[1])?Three.LoopRepeat:Three.LoopOnce,
                         repeat(route[1])?Infinity:1);
    next.clampWhenFinished=!repeat(route[1]);
    next.setEffectiveTimeScale(1).setEffectiveWeight(1);
    next.play();
    next.crossFadeFrom(prior,FADE_SECONDS,false);
    // Three schedules fading interpolants lazily: update(0) is necessary
    // before reading action effective weights at the alpha=0 endpoint.
    mixer.update(0);
    const samples=[];
    for(let index=0;index<sampleCount;index++){
      if(index>0)mixer.update(FADE_SECONDS/(sampleCount-1));
      root.updateMatrixWorld(true);
      samples.push(tracePose(bones,prior,next,index/(sampleCount-1),route));
    }
    ensure(samples.length===sampleCount,'Incomplete real mixer trace');
    routes.push({from_clip:route[0],to_clip:route[1],
                 outgoing_duration_s:outgoing.duration,incoming_duration_s:incoming.duration,
                 samples});
    mixer.stopAllAction();mixer.uncacheRoot(root);
  }
  return {
    schema:'skeleton.emerald.v7.actual-three-mixer-joints.v1',
    stage,model_bytes:V7[stage].bytes,model_sha256:V7[stage].sha256,
    donor_sha256:DONOR,three_revision:String(Three.REVISION),
    mixer:'THREE.AnimationMixer and AnimationAction.crossFadeFrom (warp=false)',
    source_stage_fade_seconds:FADE_SECONDS,samples_per_route:sampleCount,
    total_sampled_poses:routes.length*sampleCount,skin_joints:EXPECTED_JOINTS,
    geometry_collision_scanned:false,
    physical_webgl_tested:false,
    real_browser_playheads_qualified:false,
    continuous_collision_qualified:false,
    all_anatomical_pairs_qualified:false,
    artist_approved:false,physical_rtx_verified:false,release_qualified:false,
    routes,
  };
}
function main(){
  const args=parseArgs(process.argv.slice(2));
  const pin=V7[args.stage];
  ensure(pin,'Unapproved original donor stage');
  ensure(String(THREE.REVISION)==='186',
         'Three library version differs from pinned source 0.186');
  const input=path.resolve(args.model),output=path.resolve(args.output);
  ensure(input!==output && fs.existsSync(input) && !fs.lstatSync(input).isSymbolicLink(),
         'Missing or linked V7 original model');
  ensure(fs.statSync(input).isFile() && fs.statSync(input).size===pin.bytes,
         'Original V7 source model size differs');
  ensure(fs.existsSync(path.dirname(output)) &&
         fs.statSync(path.dirname(output)).isDirectory() &&
         !fs.lstatSync(path.dirname(output)).isSymbolicLink() &&
         !fs.existsSync(output),'Trusted unused evidence output path required');
  const buffer=fs.readFileSync(input);
  const original=parseOriginal(buffer,args.stage);
  const report=trace(THREE,original,args.stage,args.samples);
  const encoded=Buffer.from(JSON.stringify(report));
  ensure(encoded.length<=32*1024*1024,'Unbounded Three mixer report quota');
  const staging=output+'.pending';
  ensure(!fs.existsSync(staging),'Original mixer output staging path occupied');
  try{
    const fd=fs.openSync(staging,'wx',0o600);
    try{fs.writeFileSync(fd,encoded);fs.fsyncSync(fd);}finally{fs.closeSync(fd);}
    ensure(!fs.existsSync(output),'Source evidence appeared concurrently');
    fs.renameSync(staging,output);
  }finally{if(fs.existsSync(staging))fs.unlinkSync(staging);}
  console.log(JSON.stringify({stage:args.stage,model_sha256:pin.sha256,
    three_revision:THREE.REVISION,poses:report.total_sampled_poses,
    output,continuous_collision_qualified:false,release_qualified:false},null,2));
}
import {pathToFileURL} from 'node:url';
if(process.argv[1] && import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)main();
