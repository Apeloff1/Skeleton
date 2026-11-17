import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import test from 'node:test';
import * as THREE from 'three';

import {parseDocument,parseOriginal,buildBones,clipFromDocument,trace,
        V7,DONOR,TRANSITIONS,FADE_SECONDS} from './emerald-v7-three-mixer-trace.mjs';

const names=[...new Set(TRANSITIONS.flat())];
function synthetic(){
  const buffers=[],views=[],accessors=[];
  let bytes=0;
  const put=(numbers,kind)=>{
    const array=Buffer.alloc(numbers.length*4);
    numbers.forEach((x,i)=>array.writeFloatLE(x,i*4));
    const view=views.length;
    views.push({buffer:0,byteOffset:bytes,byteLength:array.length});
    buffers.push(array);bytes+=array.length;
    const count=numbers.length/({SCALAR:1,VEC3:3,VEC4:4}[kind]);
    const accessor=accessors.length;
    accessors.push({bufferView:view,componentType:5126,count,type:kind});
    return accessor;
  };
  const nodes=Array.from({length:108},(_,i)=>({
    name:'joint_'+i,translation:[0.001*i,0,0],rotation:[0,0,0,1],
    ...(i<107?{children:[i+1]}:{}),
  }));
  const animations=names.map((name,i)=>{
    const samplers=[],channels=[];
    for(let j=0;j<88;j++){
      const kind=j<71?'rotation':'translation';
      const t=put([0,1],'SCALAR');
      const yaw=.06*(i+1)*(j===34?1:.1);
      const r=(kind==='rotation'
        ?[0,0,0,1,0,Math.sin(yaw/2),0,Math.cos(yaw/2)]
        :[0,0,0,.01*(i+1),0,0]);
      const o=put(r,kind==='rotation'?'VEC4':'VEC3');
      const sampler=samplers.length;
      samplers.push({input:t,output:o,interpolation:'LINEAR'});
      channels.push({sampler,target:{node:j,path:kind}});
    }
    return {name,channels,samplers};
  });
  const doc={asset:{version:'2.0'},nodes,skins:[{joints:nodes.map((_,i)=>i)}],
    animations,buffers:[{byteLength:bytes}],bufferViews:views,accessors,
    extras:{stage:'pathfinder',donorSha256:DONOR,
      orbit02ClearanceCorrection:{schema:'skeleton.emerald.orbit02-tail-clearance.v1',
      clip:'orbit-02',joint_index:34,local_y_radians:.18,modified_keyframes:160,
      release_qualified:false,artist_approved:false,physical_rtx_verified:false,
      continuous_collision_qualified:false}}};
  const raw=Buffer.concat(buffers);
  return {document:doc,buffer:raw,binary:0,length:raw.length};
}
function asGlb(original){
  const doc=original.document;
  const js=Buffer.from(JSON.stringify(doc),'utf8');
  const padded=Buffer.concat([js,Buffer.alloc((4-js.length%4)%4,32)]);
  const bin=original.buffer;
  const out=Buffer.alloc(28+padded.length+bin.length);
  out.write('glTF');out.writeUInt32LE(2,4);out.writeUInt32LE(out.length,8);
  out.writeUInt32LE(padded.length,12);out.writeUInt32LE(0x4e4f534a,16);
  padded.copy(out,20);
  out.writeUInt32LE(bin.length,20+padded.length);
  out.writeUInt32LE(0x004e4942,24+padded.length);
  bin.copy(out,28+padded.length);
  return out;
}

test('source V7 hashes, 0.22s mixer policy and no hardware claims are immutable',()=>{
  assert.equal(DONOR,'c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a');
  assert.equal(V7.pathfinder.bytes,114696520);
  assert.equal(V7.archivist.bytes,114819168);
  assert.equal(FADE_SECONDS,.22);
  assert.equal(TRANSITIONS.length,6);
  assert.equal(THREE.REVISION,'186');
});

test('real Three creates 108 original named bones with exact parent hierarchy',()=>{
  const original=synthetic();
  const {root,bones,parents}=buildBones(THREE,original);
  assert.equal(root.children.length,1);
  assert.equal(bones.length,108);
  assert.equal(parents[34],33);
  assert.equal(bones[34].name,'joint_34');
  assert.equal(bones[34].parent,bones[33]);
});

test('all six original motion clips become genuine Three tracks without texture rendering',()=>{
  const original=synthetic();
  const {bones}=buildBones(THREE,original);
  for(const name of names){
    const clip=clipFromDocument(THREE,original,bones,name);
    assert.equal(clip.name,name);
    assert.equal(clip.tracks.length,88);
    assert.equal(clip.duration,1);
    const track=clip.tracks.find(x=>x.name==='joint_34.quaternion');
    assert.ok(track instanceof THREE.QuaternionKeyframeTrack);
  }
});

test('actual 0.22s Three AnimationMixer executes six source routes, nine phases, 108 joints',()=>{
  const original=synthetic();
  const result=trace(THREE,original,'pathfinder',9);
  assert.equal(result.three_revision,'186');
  assert.equal(result.total_sampled_poses,54);
  assert.equal(result.routes.length,6);
  assert.equal(result.geometry_collision_scanned,false);
  assert.equal(result.continuous_collision_qualified,false);
  assert.equal(result.real_browser_playheads_qualified,false);
  assert.equal(result.physical_rtx_verified,false);
  assert.equal(result.release_qualified,false);
  for(const route of result.routes){
    assert.equal(route.samples.length,9);
    assert.equal(route.samples[0].alpha,0);
    assert.equal(route.samples[8].alpha,1);
    assert.equal(route.samples[4].alpha,.5);
    for(const sample of route.samples){
      assert.equal(sample.joints.length,108);
      assert.ok(Number.isFinite(sample.incoming_weight));
      assert.ok(sample.incoming_weight>=-1e-7&&sample.incoming_weight<=1+1e-7);
      for(const bone of sample.joints){
        assert.equal(bone.local_quaternion.length,4);
        assert.equal(bone.world_matrix.length,16);
        assert.ok(bone.world_matrix.every(Number.isFinite));
      }
    }
    assert.ok(Math.abs(route.samples[0].outgoing_weight-1)<1e-5);
    assert.ok(Math.abs(route.samples[8].incoming_weight-1)<1e-5);
  }
});

test('wrong model SHA and modified original glTF source are denied before animation',()=>{
  const original=synthetic(),bytes=asGlb(original);
  assert.throws(()=>parseOriginal(bytes,'pathfinder'),/Exact original V7 GLB byte or SHA/);
  assert.throws(()=>parseDocument(bytes,'pathfinder'),/Wrong original V7 donor, rig or animation catalogue/);
});
