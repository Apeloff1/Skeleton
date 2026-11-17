"""Independent V7 exact-byte comparison against original V6 GLBs.

Only 160 orbit-02 tail-root quaternions may change. All source geometry,
skin, materials, other animation channels and growth must be byte-identical.
"""
from __future__ import annotations
import argparse, json, mmap, struct
from pathlib import Path
import numpy as np
from emerald_v7_orbit02 import SOURCES, OUTPUTS, DONOR, ROOT_JOINT, ANGLE, TARGET_CLIP, sha256, post_y, require

def parse(raw):
 require(len(raw)>=32, 'truncated GLB')
 magic,version,total,n,tag=struct.unpack_from('<4sIIII',raw)
 require((magic,version,total,tag)==(b'glTF',2,len(raw),0x4e4f534a)
         and n%4==0 and 0<n<=32*1024**2, 'GLB header mismatch')
 data,kind=struct.unpack_from('<II',raw,20+n);start=28+n
 require(kind==0x004e4942 and start+data==len(raw), 'BIN mismatch')
 return json.loads(raw[20:20+n]),start,data

def read_quats(raw,doc,start,idx):
 acc=doc['accessors'][idx];view=doc['bufferViews'][acc['bufferView']]
 require(acc['type']=='VEC4' and acc['componentType']==5126 and
         acc['count']==160 and 'sparse' not in acc and 'byteStride' not in view,
         'wrong target accessor')
 offset=view.get('byteOffset',0)+acc.get('byteOffset',0)
 require(offset>=0 and offset+160*16<=doc['buffers'][0]['byteLength'],
         'invalid orbit02 target bounds')
 return np.frombuffer(raw,dtype='<f4',count=640,offset=start+offset).reshape(160,4).copy()

def verify(stage,source,candidate):
 require(stage in SOURCES, 'unknown original evolution stage')
 source=Path(source);candidate=Path(candidate)
 require(source.is_file() and candidate.is_file() and
         not source.is_symlink() and not candidate.is_symlink(), 'missing or linked original models')
 require((source.stat().st_size,sha256(source))==SOURCES[stage], 'source exact SHA differs')
 require((candidate.stat().st_size,sha256(candidate))==OUTPUTS[stage],
         'candidate exact output SHA differs')
 with source.open('rb') as fa,candidate.open('rb') as fb:
  a=mmap.mmap(fa.fileno(),0,access=mmap.ACCESS_READ)
  b=mmap.mmap(fb.fileno(),0,access=mmap.ACCESS_READ)
  try:
   before,ba,na=parse(a);after,bb,_nb=parse(b)
   require(b[bb:bb+na]==a[ba:ba+na],
           'original embedded binary prefix was modified')
   preserved=set(before)-{'asset','extras','animations','accessors','bufferViews','buffers'}
   require(all(before[k]==after[k] for k in preserved)
           and after['asset']['version']==before['asset']['version'],
           'source mesh, skin, PBR or node declarations differ')
   require(after['accessors'][:len(before['accessors'])]==before['accessors']
           and after['bufferViews'][:len(before['bufferViews'])]==before['bufferViews']
           and len(after['accessors'])==len(before['accessors'])+1
           and len(after['bufferViews'])==len(before['bufferViews'])+1,
           'old source accessor modified or wrong new sampler count')
   require(all(after['extras'][k]==v for k,v in before['extras'].items()),
           'original source provenance changed')
   correction=after['extras']['orbit02ClearanceCorrection']
   require(correction['schema']=='skeleton.emerald.orbit02-tail-clearance.v1'
           and correction['source_v6_sha256']==SOURCES[stage][1]
           and correction['donor_sha256']==DONOR
           and correction['joint_index']==ROOT_JOINT
           and correction['clip']==TARGET_CLIP
           and correction['local_y_radians']==ANGLE
           and correction['modified_keyframes']==160
           and all(correction[k] is False for k in (
               'equipment_enabled','real_mixer_qualified',
               'crossfade_transition_qualified','continuous_collision_qualified',
               'artist_approved','unreal_compiled','physical_rtx_verified',
               'release_qualified')),
           'unreviewed source correction or false acceptance')
   require(len(before['animations'])==len(after['animations'])==381
           and before['animations'][-1]==after['animations'][-1],
           'next-form growth animation modified')
   target_node=before['skins'][0]['joints'][ROOT_JOINT]
   count=unchanged=0;worst_error=0.
   for old_clip,new_clip in zip(before['animations'],after['animations']):
    require(old_clip['name']==new_clip['name']
            and old_clip['channels']==new_clip['channels']
            and len(old_clip['samplers'])==len(new_clip['samplers']),
            'animation channel declaration changed')
    for channel in old_clip['channels']:
     old_s=old_clip['samplers'][channel['sampler']]
     new_s=new_clip['samplers'][channel['sampler']]
     if (old_clip['name']==TARGET_CLIP and
         channel['target']['node']==target_node and
         channel['target']['path']=='rotation'):
      original=read_quats(a,before,ba,old_s['output'])
      corrected=read_quats(b,after,bb,new_s['output'])
      require(old_s['input']==new_s['input']
              and old_s['interpolation']==new_s['interpolation']=='LINEAR',
              'original animation timebase changed')
      error=float(np.max(abs(post_y(original)-corrected)))
      require(error<=4e-7,'quaternion correction not exact')
      worst_error=max(worst_error,error)
      count+=1
     else:
      require(old_s==new_s,'unapproved animation sampler changed')
      unchanged+=1
   require(count==1 and unchanged==44512, 'incomplete orbit-02 correction')
   return {
     'schema':'skeleton.emerald.v7.independent-source-integrity.v1',
     'stage':stage,'source_v6_sha256':SOURCES[stage][1],
     'v7_sha256':OUTPUTS[stage][1],'v7_bytes':OUTPUTS[stage][0],
     'modified_sampler_streams':count,'modified_keyframes':160,
     'other_sampler_channels_preserved':unchanged,
     'max_rotation_error':worst_error,
     'growth_clip_exact':True,
     'original_embedded_binary_prefix_exact':True,
     'original_mesh_skin_materials_exact':True,
     'continuous_collision_qualified':False,
     'real_mixer_qualified':False,'artist_approved':False,
     'physical_rtx_verified':False,'release_qualified':False,
   }
  finally:
   a.close();b.close()

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('stage',choices=SOURCES)
 p.add_argument('--source',required=True,type=Path)
 p.add_argument('--candidate',required=True,type=Path)
 a=p.parse_args()
 print(json.dumps(verify(a.stage,a.source,a.candidate),indent=2))
