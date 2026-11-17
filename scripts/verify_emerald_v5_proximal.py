"""Independently verify every V5 proximal candidate edit against original V4 bytes."""
from __future__ import annotations
import argparse,hashlib,json,mmap,struct
from pathlib import Path
import numpy as np
from emerald_v5_proximal_wingfold import SOURCES,OUTPUTS,ANGLES,DONOR,sha,attr,corrected,require

def source_document(raw):
 require(len(raw)>=32,'GLB truncated')
 magic,version,total,jslen,tag=struct.unpack_from('<4sIIII',raw)
 require((magic,version,total,tag)==(b'glTF',2,len(raw),0x4e4f534a)
         and jslen>0 and jslen<=32*1024**2 and jslen%4==0,'unsupported GLB')
 n,tag=struct.unpack_from('<II',raw,20+jslen)
 require(tag==0x004e4942 and 28+jslen+n==len(raw),'GLB BIN chunk mismatch')
 return json.loads(raw[20:20+jslen]),28+jslen,n

def check(stage,source,candidate):
 require(stage in SOURCES,'unsupported stage')
 source=Path(source);candidate=Path(candidate)
 size,source_sha,next_stage=SOURCES[stage]
 output_bytes,output_sha=OUTPUTS[stage]
 require(source.is_file() and not source.is_symlink() and
         source.stat().st_size==size and sha(source)==source_sha,'source identity mismatch')
 require(candidate.is_file() and not candidate.is_symlink() and
         candidate.stat().st_size==output_bytes and sha(candidate)==output_sha,
         'candidate output digest mismatch')
 left_file=source.open('rb');right_file=candidate.open('rb')
 left=mmap.mmap(left_file.fileno(),0,access=mmap.ACCESS_READ)
 right=mmap.mmap(right_file.fileno(),0,access=mmap.ACCESS_READ)
 try:
  before,start,length=source_document(left)
  after,after_start,after_length=source_document(right)
  require(after['asset']['version']==before['asset']['version']=='2.0' and
          before['extras']['donorSha256']==after['extras']['donorSha256']==DONOR and
          before['extras']['stage']==after['extras']['stage']==stage,'donor or stage mismatch')
  correction=after['extras'].get('wingFoldCorrection',{})
  require(correction.get('schema')=='skeleton.emerald.proximal-wingfold.v1'
          and correction.get('source_model_sha256')==source_sha
          and correction.get('donor_sha256')==DONOR
          and correction.get('root_shoulder_joint_ids')==[68,80]
          and correction.get('root_local_y_radians')==-.30
          and correction.get('terminal_joint_ids')==[79,91]
          and correction.get('terminal_local_z_radians')==.18
          and correction.get('corrected_tracks')==1520
          and correction.get('growth_unchanged') is True
          and all(correction.get(k) is False for k in (
             'equipment_enabled','continuous_collision_qualified',
             'artist_approved','unreal_compiled','physical_rtx_verified','release_qualified')),
          'unreviewed correction or false qualification flags')
  unchanged=set(before)-{'asset','extras','animations','accessors','bufferViews','buffers'}
  require({k:before[k] for k in unchanged}=={k:after[k] for k in unchanged},
          'original geometry, material or skin declarations modified')
  require(before['bufferViews']==after['bufferViews'][:len(before['bufferViews'])] and
          before['accessors']==after['accessors'][:len(before['accessors'])] and
          len(after['bufferViews'])-len(before['bufferViews'])==1520 and
          len(after['accessors'])-len(before['accessors'])==1520,
          'append-only buffer/accessor contract changed')
  require(length<=after_length and
          hashlib.sha256(left[start:start+length]).digest()==
          hashlib.sha256(right[after_start:after_start+length]).digest(),
          'original binary bytes not preserved exactly')
  require(len(before['animations'])==len(after['animations'])==381 and
          before['animations'][-1]==after['animations'][-1] and
          before['animations'][-1]['name']=='growth-'+stage+'-to-'+next_stage,
          'original growth clip altered')
  ids={before['skins'][0]['joints'][k]:v for k,v in ANGLES.items()}
  require(len(ids)==4 and len(before['skins'][0]['joints'])==108,'invalid original joint map')
  count=other=0;maxerror=0.
  for old_clip,new_clip in zip(before['animations'][:380],after['animations'][:380]):
   require(old_clip['name']==new_clip['name'] and
           old_clip['channels']==new_clip['channels'] and
           len(old_clip['samplers'])==len(new_clip['samplers']),
           'original animation channels modified')
   seen=set()
   for ch in old_clip['channels']:
    o=old_clip['samplers'][ch['sampler']];n=new_clip['samplers'][ch['sampler']]
    require(o['input']==n['input'] and o['interpolation']==n['interpolation'],
            'original timing modified')
    joint=ch['target']['node']
    if joint in ids and ch['target']['path']=='rotation':
     require(joint not in seen,'duplicate corrected joint')
     seen.add(joint)
     original=attr(left,before,start,o['output']).copy()
     actual=attr(right,after,after_start,n['output']).copy()
     axis,angle=ids[joint]
     expected=corrected(original,axis,angle)
     error=float(np.max(np.abs(expected-actual)))
     require(error<4e-7,'corrected track no longer exact')
     maxerror=max(maxerror,error);count+=1
    else:
     require(o==n,'unreviewed original motion modified')
     other+=1
   require(seen==set(ids),'missing a review-bound shoulder or wing finger')
  require(count==1520,'incomplete corrective repertoire')
  return {'schema':'skeleton.emerald.proximal-wingfold-independent.v1',
          'stage':stage,'source_sha256':source_sha,'candidate_sha256':output_sha,
          'candidate_bytes':output_bytes,'donor_sha256':DONOR,
          'corrected_rotation_tracks':count,'unchanged_other_tracks':other,
          'maximum_quaternion_error':maxerror,
          'original_binary_prefix_identical':True,
          'original_mesh_skin_materials_identical':True,'growth_unchanged':True,
          'equipment_enabled':False,'continuous_collision_qualified':False,
          'artist_approved':False,'unreal_compiled':False,
          'physical_rtx_verified':False,'release_qualified':False}
 finally:
  left.close();right.close();left_file.close();right_file.close()

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('stage',choices=SOURCES);p.add_argument('--source',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True)
 a=p.parse_args();print(json.dumps(check(a.stage,a.source,a.candidate),indent=2))
