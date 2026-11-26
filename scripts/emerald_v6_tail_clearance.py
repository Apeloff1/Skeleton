"""Deterministic, exact-original V6 tail clearance for two selected flight clips.

Review-only: append two quaternion streams without changing geometry, weighted
skin, materials, original 378 other motion clips or next-form growth. Actual
clip-transition blending, mesh CCD, RTX, art and release remain held.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,math,mmap,os,struct
from pathlib import Path
import numpy as np

PINNED={
 'pathfinder':(114687832,'80a98c198f5d8a6e101b571a9def6869904df4dfb0e5d90cba33f8890de9112f','archivist'),
 'archivist':(114810480,'569fdf85be64705b857a43e2491b62ae6970fe90739c1050ffb49494da642b27','hoarder'),
}
OUTPUTS={
 'pathfinder':(114693124,'20d6a6a62b3ff232572e1b25d799f1461d4e343ce3b7d30a328faed8837c4063'),
 'archivist':(114815776,'8d72d43773a98444133ab628db552bddad06ea0f101cfe223897bf8ba0944973'),
}
DONOR='c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a'
ANGLE=.18
JOINT=34
CLIPS=('orbit-01','landing-1')

def require(x,why):
 if not x:raise ValueError(why)
def digest(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def quat_post_y(q,angle=ANGLE):
 require(isinstance(q,np.ndarray) and q.ndim==2 and q.shape[1]==4 and q.shape[0]>1 and np.isfinite(q).all(),'invalid quaternion track')
 require(math.isfinite(angle) and angle==ANGLE,'unapproved yaw offset')
 require(np.max(np.abs(np.linalg.norm(q,axis=1)-1))<2e-5,'source quaternions not normalized')
 x,y,z,w=q.T.astype(np.float64);s=math.sin(angle/2);c=math.cos(angle/2)
 out=np.column_stack((c*x-s*z,c*y+s*w,c*z+s*x,c*w-s*y))
 out/=np.linalg.norm(out,axis=1)[:,None]
 require(np.isfinite(out).all(),'invalid yaw correction')
 return np.ascontiguousarray(out,dtype='<f4')

def open_exact(path,stage):
 require(stage in PINNED,'unknown evolution stage')
 size,sha,next_stage=PINNED[stage]
 p=Path(path)
 require(p.is_file() and not p.is_symlink() and p.stat().st_size==size and digest(p)==sha,'exact original V5 input pin mismatch')
 handle=p.open('rb');raw=mmap.mmap(handle.fileno(),0,access=mmap.ACCESS_READ)
 try:
  require(len(raw)>32,'truncated model')
  magic,version,total,jslen,tag=struct.unpack_from('<4sIIII',raw)
  require((magic,version,total,tag)==(b'glTF',2,len(raw),0x4e4f534a) and 4<=jslen<=32*1024**2 and jslen%4==0,'invalid GLB JSON')
  binlen,bintag=struct.unpack_from('<II',raw,20+jslen)
  start=28+jslen
  require(start+binlen==len(raw) and bintag==0x004e4942,'invalid embedded BIN')
  doc=json.loads(raw[20:20+jslen])
  skin=doc['skins'];animations=doc['animations']
  require(doc['asset']['version']=='2.0' and doc['extras']['stage']==stage and doc['extras']['donorSha256']==DONOR and len(skin)==1 and len(skin[0]['joints'])==108 and len(animations)==381 and animations[-1]['name']=='growth-'+stage+'-to-'+next_stage,'source lineage, rig or growth metadata changed')
  require(doc['buffers']==[{'byteLength':binlen}],'external or padded binary source not approved')
  names=[a['name'] for a in animations]
  require(len(set(names))==381 and all(names.count(x)==1 for x in CLIPS),'missing or duplicate flight clip')
  return handle,raw,doc,start,binlen
 except BaseException:
  raw.close();handle.close();raise

def rotation_accessor(raw,doc,start,index):
 acc=doc['accessors'][index]
 view=doc['bufferViews'][acc['bufferView']]
 require(acc['type']=='VEC4' and acc['componentType']==5126 and acc['count']>=2 and 'sparse' not in acc and 'byteStride' not in view,'unsupported rotation accessor')
 local=acc.get('byteOffset',0);offset=view.get('byteOffset',0)+local;size=acc['count']*16
 require(local>=0 and local+size<=view['byteLength'] and offset+size<=doc['buffers'][0]['byteLength'],'invalid rotation bounds')
 return np.frombuffer(raw,dtype='<f4',offset=start+offset,count=acc['count']*4).reshape(-1,4).copy()

def build(stage,source,output):
 target=Path(output)
 require(target.parent.is_dir() and not target.parent.is_symlink() and not os.path.lexists(target),'trusted unused destination required')
 handle,raw,original,start,binlen=open_exact(source,stage)
 try:
  doc=copy.deepcopy(original)
  target_node=doc['skins'][0]['joints'][JOINT]
  appended=[];size=binlen;modified=[]
  for name in CLIPS:
   a=next(a for a in doc['animations'] if a['name']==name)
   channels=[ch for ch in a['channels'] if ch['target']['node']==target_node and ch['target']['path']=='rotation']
   require(len(channels)==1,'missing or duplicate tail-root rotation in '+name)
   sampler=a['samplers'][channels[0]['sampler']]
   require(sampler['interpolation']=='LINEAR','source animation interpolation changed')
   old=rotation_accessor(raw,original,start,sampler['output'])
   data=quat_post_y(old)
   pad=(-size)%4;appended.extend((b'\x00'*pad,data.tobytes()));size+=pad
   newview=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':size,'byteLength':data.nbytes})
   sampler['output']=len(doc['accessors']);doc['accessors'].append({'bufferView':newview,'componentType':5126,'count':len(data),'type':'VEC4'})
   size+=data.nbytes;modified.append({'clip':name,'keys':len(data)})
  require(doc['animations'][-1]==original['animations'][-1] and len(modified)==2,'growth or motion clip accidentally changed')
  doc['buffers'][0]['byteLength']=size
  doc['asset']['generator']='Emerald original-donor '+stage+' V6 tail-root flight clearance candidate'
  doc['extras']['tailClearanceCorrection']={
    'schema':'skeleton.emerald.tail-clearance.v1',
    'source_v5_sha256':PINNED[stage][1],
    'original_hoarder_donor_sha256':DONOR,
    'joint_index':JOINT,
    'local_y_radians':ANGLE,
    'clips':list(CLIPS),
    'other_378_original_clips_unchanged':True,
    'growth_clip_unchanged':True,
    'equipment_enabled':False,
    'cross_clip_transition_qualified':False,
    'full_continuous_collision_qualified':False,
    'artist_approved':False,
    'physical_rtx_verified':False,
    'release_qualified':False,
  }
  js=json.dumps(doc,separators=(',',':'),ensure_ascii=False).encode('utf-8')
  js+=b' '*((-len(js))%4)
  tailpad=(-size)%4;total=28+len(js)+size+tailpad
  require(total<512*1024**2,'model output too large')
  try:
   with target.open('xb') as out:
    out.write(struct.pack('<4sIIII',b'glTF',2,total,len(js),0x4e4f534a));out.write(js)
    out.write(struct.pack('<II',size+tailpad,0x004e4942))
    out.write(raw[start:start+binlen])
    for part in appended:out.write(part)
    out.write(b'\0'*tailpad);out.flush();os.fsync(out.fileno())
   require(target.stat().st_size==total and
           (total,digest(target))==OUTPUTS[stage],
           'new model does not equal independently measured output pin')
  except BaseException:
   if target.exists():target.unlink()
   raise
  return {'stage':stage,'source_v5_sha256':PINNED[stage][1],
   'source_bytes':PINNED[stage][0],
   'candidate_bytes':total,'candidate_sha256':OUTPUTS[stage][1],
   'original_hoarder_donor_sha256':DONOR,
   'corrected_rotation_streams':len(modified),'keyframe_counts':modified,
   'original_binary_prefix_identical':True,'untouched_378_clips':True,
   'growth_unchanged':True,'cross_clip_transition_qualified':False,
   'continuous_collision_qualified':False,'artist_approved':False,'release_qualified':False}
 finally:
  raw.close();handle.close()

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('stage',choices=PINNED)
 p.add_argument('--input',required=True,type=Path)
 p.add_argument('--output',required=True,type=Path)
 args=p.parse_args()
 print(json.dumps(build(args.stage,args.input,args.output),indent=2))
