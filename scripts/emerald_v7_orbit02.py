"""Source-pinned V7 orbit-02 tail-root yaw correction for original V6 GLBs.

Exports review-only candidates. Does not modify original geometry, skin,
materials, other 380 motion clips or next-form growth. No GPU/artist approval.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, math, mmap, os, struct
from pathlib import Path
import numpy as np

SOURCES = {
 'pathfinder': (114693124, '20d6a6a62b3ff232572e1b25d799f1461d4e343ce3b7d30a328faed8837c4063'),
 'archivist': (114815776, '8d72d43773a98444133ab628db552bddad06ea0f101cfe223897bf8ba0944973'),
}
OUTPUTS = {
 'pathfinder': (114696520, '27e1a6a22fad045d26edf4dc2813292829aab8dcaa129fac407f80ee83229ade'),
 'archivist': (114819168, 'f224671cf6d0886365f081faa29f9dcf2509d52211677d2a83152a389389acaf'),
}
DONOR = 'c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a'
ROOT_JOINT = 34
ANGLE = .18
TARGET_CLIP = 'orbit-02'
MAX_BYTES = 512*1024**2

def require(b, reason):
 if not b: raise ValueError(reason)

def sha256(path):
 with Path(path).open('rb') as source:
  return hashlib.file_digest(source, 'sha256').hexdigest()

def post_y(q):
 require(q.ndim == 2 and q.shape[1] == 4 and len(q) == 160 and np.isfinite(q).all(),
         'unreviewed orbit02 quaternion shape')
 require(np.max(np.abs(np.linalg.norm(q, axis=1)-1)) < 2e-5, 'invalid source quaternions')
 x,y,z,w = q.T.astype(np.float64)
 s=math.sin(ANGLE/2); c=math.cos(ANGLE/2)
 result=np.column_stack([c*x-s*z,c*y+s*w,c*z+s*x,c*w-s*y])
 result/=np.linalg.norm(result, axis=1)[:,None]
 require(np.isfinite(result).all(), 'nonfinite corrected quaternion')
 return np.ascontiguousarray(result, dtype='<f4')

def export(stage, source, out):
 require(stage in SOURCES, 'unqualified source stage')
 src=Path(source); dest=Path(out)
 require(dest.parent.is_dir() and not dest.parent.is_symlink() and
         not os.path.lexists(dest), 'unused destination required')
 size, sha = SOURCES[stage]
 require(src.is_file() and not src.is_symlink() and
         src.stat().st_size == size and sha256(src) == sha, 'wrong exact V6 model')
 handle=src.open('rb'); raw=mmap.mmap(handle.fileno(),0,access=mmap.ACCESS_READ)
 try:
  require(len(raw)>=32, 'truncated glb')
  magic,version,total,jsonlen,tag=struct.unpack_from('<4sIIII',raw)
  require((magic,version,total,tag)==(b'glTF',2,len(raw),0x4e4f534a) and
          0<jsonlen<=32*1024**2 and jsonlen%4==0, 'GLB header invalid')
  binlen,bintag=struct.unpack_from('<II',raw,20+jsonlen); base=28+jsonlen
  require(bintag==0x004e4942 and base+binlen==len(raw), 'GLB binary invalid')
  original=json.loads(raw[20:20+jsonlen]); doc=copy.deepcopy(original)
  require(doc['asset']['version']=='2.0' and doc['extras']['stage']==stage and
          doc['extras']['donorSha256']==DONOR, 'donor mismatch')
  require(len(doc['skins'])==1 and len(doc['skins'][0]['joints'])==108 and
          len(doc['animations'])==381, 'wrong skeleton or catalogue')
  require(doc['extras']['tailClearanceCorrection']['schema']=='skeleton.emerald.tail-clearance.v1'
          and doc['extras']['tailClearanceCorrection']['clips']==['orbit-01','landing-1']
          and doc['extras']['tailClearanceCorrection']['joint_index']==ROOT_JOINT,
          'unexpected V6 correction lineage')
  require(len(doc['buffers'])==1 and doc['buffers'][0]['byteLength']<=binlen,
          'unexpected embedded buffer')
  animations=doc['animations']; names=[a['name'] for a in animations]
  require(len(set(names))==381 and
          names[-1]=='growth-'+stage+'-to-'+('archivist' if stage=='pathfinder' else 'hoarder'),
          'growth catalogue differs')
  a=next(a for a in animations if a['name']==TARGET_CLIP)
  node=doc['skins'][0]['joints'][ROOT_JOINT]
  channels=[ch for ch in a['channels']
            if ch['target']['node']==node and ch['target']['path']=='rotation']
  require(len(channels)==1, 'missing or duplicate orbit02 tail rotation')
  sampler=a['samplers'][channels[0]['sampler']]
  require(sampler['interpolation']=='LINEAR', 'unexpected interpolation')
  acc=doc['accessors'][sampler['output']]; view=doc['bufferViews'][acc['bufferView']]
  require(acc['type']=='VEC4' and acc['componentType']==5126 and
          acc['count']==160 and 'sparse' not in acc and 'byteStride' not in view,
          'wrong original tail track')
  local=acc.get('byteOffset',0); offset=view.get('byteOffset',0)+local
  require(local>=0 and local+acc['count']*16<=view['byteLength'] and
          offset+acc['count']*16<=doc['buffers'][0]['byteLength'],
          'out of bounds rotations')
  original_q=np.frombuffer(raw,dtype='<f4',count=acc['count']*4,
                           offset=base+offset).reshape(-1,4).copy()
  transformed=post_y(original_q); data=transformed.tobytes()
  content_bytes=doc['buffers'][0]['byteLength']
  padding=(-content_bytes)%4; new_offset=content_bytes+padding
  doc['bufferViews'].append({'buffer':0,'byteOffset':new_offset,'byteLength':len(data)})
  sampler['output']=len(doc['accessors'])
  doc['accessors'].append({'bufferView':len(doc['bufferViews'])-1,
                           'componentType':5126,'count':len(transformed),'type':'VEC4'})
  new_content=new_offset+len(data)
  doc['buffers'][0]['byteLength']=new_content
  doc['asset']['generator']='Emerald original-donor '+stage+' V7 orbit-02 tail clearance candidate'
  doc['extras']['orbit02ClearanceCorrection']={
   'schema':'skeleton.emerald.orbit02-tail-clearance.v1',
   'source_v6_sha256':sha,'donor_sha256':DONOR,
   'joint_index':ROOT_JOINT,'clip':TARGET_CLIP,'local_y_radians':ANGLE,
   'modified_rotation_streams':1,'modified_keyframes':160,
   'original_binary_prefix_exact':True,
   'old_380_clips_unchanged_except_orbit02':True,
   'growth_clip_unchanged':True,
   'equipment_enabled':False,
   'real_mixer_qualified':False,'crossfade_transition_qualified':False,
   'continuous_collision_qualified':False,'artist_approved':False,
   'unreal_compiled':False,'physical_rtx_verified':False,'release_qualified':False}
  require(animations[-1]==original['animations'][-1], 'growth clip modified')
  for old_clip,new_clip in zip(original['animations'],animations):
   if old_clip['name']!=TARGET_CLIP:
    require(old_clip==new_clip, 'non-target original animation modified')
  js=json.dumps(doc,separators=(',',':'),ensure_ascii=False).encode('utf-8')
  js+=b' '*((-len(js))%4)
  output_padding=(-new_content)%4; total=28+len(js)+new_content+output_padding
  require(total<MAX_BYTES, 'model too big')
  try:
   with dest.open('xb') as file:
    file.write(struct.pack('<4sIIII',b'glTF',2,total,len(js),0x4e4f534a))
    file.write(js)
    file.write(struct.pack('<II',new_content+output_padding,0x004e4942))
    file.write(raw[base:base+content_bytes])
    file.write(b'\0'*padding); file.write(data)
    file.write(b'\0'*output_padding)
    file.flush();os.fsync(file.fileno())
   require(dest.stat().st_size==total and dest.stat().st_size>size and
           (dest.stat().st_size,sha256(dest))==OUTPUTS[stage],
           'candidate differs from independently measured V7 output')
  except BaseException:
   if dest.exists():dest.unlink()
   raise
  return {'schema':'skeleton.emerald.orbit02-export.v1',
          'stage':stage,'source_sha256':sha,
          'v7_sha256':OUTPUTS[stage][1],'v7_bytes':total,
          'tail_root_joint':ROOT_JOINT,'corrected_clip':TARGET_CLIP,
          'modified_keyframes':160,'growth_unchanged':True,
          'original_embedded_binary_prefix_exact':True,
          'artist_approved':False,'real_mixer_qualified':False,
          'continuous_collision_qualified':False,'release_qualified':False}
 finally:
  del original_q
  raw.close();handle.close()

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('stage',choices=SOURCES)
 p.add_argument('--source',required=True,type=Path)
 p.add_argument('--output',required=True,type=Path)
 a=p.parse_args()
 print(json.dumps(export(a.stage,a.source,a.output),indent=2))
