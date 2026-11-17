"""Source-locked append-only shoulder and terminal wing correction for original V4.
This generates review-only candidates; no geometry/weight/UV/material/growth changes.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,math,mmap,os,struct
from pathlib import Path
import numpy as np

DONOR='c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a'
SOURCES={
 'pathfinder':(112706532,'e51e44a3277da1123df017d23f41aee43e373ea1c9e126f30dafd9a24c213092','archivist'),
 'archivist':(112829184,'0b7804643c65a5eb06f5baac2008d88b101b363613d2244016b3a33470c18d8f','hoarder'),
}
OUTPUTS={
 'pathfinder':(114687832,'80a98c198f5d8a6e101b571a9def6869904df4dfb0e5d90cba33f8890de9112f'),
 'archivist':(114810480,'569fdf85be64705b857a43e2491b62ae6970fe90739c1050ffb49494da642b27'),
}
ANGLES={68:('Y',-.30),80:('Y',-.30),79:('Z',.18),91:('Z',.18)}
MAX_MODEL=512*1024**2

def require(x,msg):
 if not x:raise ValueError(msg)

def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def corrected(q,axis,angle):
 require(q.ndim==2 and q.shape[1]==4 and np.isfinite(q).all(),'invalid quaternion array')
 require(np.max(abs(np.linalg.norm(q,axis=1)-1))<2e-5,'non-unit source rotation')
 require(math.isfinite(angle) and ((axis=='Y' and angle==-.30) or (axis=='Z' and angle==.18)),'unreviewed correction')
 s,c=math.sin(angle/2),math.cos(angle/2)
 x,y,z,w=q.T.astype(np.float64)
 if axis=='Z':v=np.column_stack((c*x+s*y,c*y-s*x,c*z+s*w,c*w-s*z))
 elif axis=='Y':v=np.column_stack((c*x-s*z,c*y+s*w,c*z+s*x,c*w-s*y))
 else:raise ValueError('unsupported axis')
 v/=np.linalg.norm(v,axis=1)[:,None]
 require(np.isfinite(v).all(),'non-finite correction')
 return np.ascontiguousarray(v,dtype='<f4')

def attr(raw,doc,base,index):
 a=doc['accessors'][index];view=doc['bufferViews'][a['bufferView']];offset=view.get('byteOffset',0)+a.get('byteOffset',0)
 require(a['type']=='VEC4' and a['componentType']==5126 and a['count']>0 and 'sparse' not in a and 'byteStride' not in view,'unsupported quaternion accessor')
 require(a.get('byteOffset',0)>=0 and a.get('byteOffset',0)+a['count']*16<=view['byteLength'] and offset+a['count']*16<=doc['buffers'][0]['byteLength'],'accessor bounds')
 return np.frombuffer(raw,dtype='<f4',count=a['count']*4,offset=base+offset).reshape(-1,4)

def build(stage,source,destination):
 require(stage in SOURCES,'invalid stage')
 source=Path(source);destination=Path(destination)
 size,source_sha,next_stage=SOURCES[stage]
 require(source.is_file() and not source.is_symlink() and source.stat().st_size==size and sha(source)==source_sha,'untrusted original source')
 require(destination.parent.is_dir() and not destination.parent.is_symlink() and not os.path.lexists(destination),'trusted empty output required')
 f=source.open('rb');raw=mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ)
 try:
  magic,ver,total,jsonlen,tag=struct.unpack_from('<4sIIII',raw)
  require((magic,ver,total,tag)==(b'glTF',2,len(raw),0x4e4f534a) and 4<=jsonlen<=32*1024**2 and jsonlen%4==0,'invalid source GLB')
  binlen,bin_tag=struct.unpack_from('<II',raw,20+jsonlen);base=28+jsonlen
  require(bin_tag==0x004e4942 and base+binlen==len(raw),'invalid source binary')
  original=json.loads(raw[20:20+jsonlen]);doc=copy.deepcopy(original)
  require(doc['asset']['version']=='2.0' and doc['extras']['stage']==stage and doc['extras']['donorSha256']==DONOR,'wrong donor model')
  skin=doc['skins'][0];require(len(doc['skins'])==1 and len(skin['joints'])==108 and len(doc['animations'])==381,'wrong original rig or clips')
  names=[a['name'] for a in doc['animations']];require(len(set(names))==381 and names[-1]=='growth-'+stage+'-to-'+next_stage,'growth metadata mismatch')
  ids={skin['joints'][k]:val for k,val in ANGLES.items()};require(len(ids)==4,'duplicate wing joints')
  appended=[];bytes_new=binlen;tracks=0
  for animation in doc['animations'][:380]:
   seen=set()
   for channel in animation['channels']:
    node=channel['target']['node'];prop=channel['target']['path']
    if node not in ids or prop!='rotation':continue
    require(node not in seen,'duplicate corrected joint');seen.add(node)
    sampler=animation['samplers'][channel['sampler']]
    old=attr(raw,original,base,sampler['output'])
    axis,angle=ids[node];out=corrected(old,axis,angle);pad=(-bytes_new)%4
    appended.extend((b'\0'*pad,out.tobytes()))
    bytes_new+=pad;view=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':bytes_new,'byteLength':out.nbytes})
    sampler['output']=len(doc['accessors']);doc['accessors'].append({'bufferView':view,'componentType':5126,'count':len(out),'type':'VEC4'})
    bytes_new+=out.nbytes;tracks+=1
    del old,out
   require(seen==set(ids),'missing corrected rotation in '+animation['name'])
  require(tracks==1520 and doc['animations'][-1]==original['animations'][-1],'incomplete corrective sequence')
  doc['buffers'][0]['byteLength']=bytes_new
  doc['asset']['generator']='Emerald original-donor '+stage+' wing shoulder+terminal candidate r1'
  doc['extras']['wingFoldCorrection']={'schema':'skeleton.emerald.proximal-wingfold.v1','source_model_sha256':source_sha,'donor_sha256':DONOR,'root_shoulder_joint_ids':[68,80],'root_local_y_radians':-.30,'terminal_joint_ids':[79,91],'terminal_local_z_radians':.18,'corrected_tracks':tracks,'growth_unchanged':True,'original_binary_prefix_exact':True,'equipment_enabled':False,'continuous_collision_qualified':False,'artist_approved':False,'unreal_compiled':False,'physical_rtx_verified':False,'release_qualified':False}
  js=json.dumps(doc,ensure_ascii=False,separators=(',',':')).encode('utf8');js+=b' '*((-len(js))%4)
  pad=(-bytes_new)%4;size_new=28+len(js)+bytes_new+pad
  require(size_new<MAX_MODEL,'candidate too large')
  try:
   with destination.open('xb') as out:
    out.write(struct.pack('<4sIIII',b'glTF',2,size_new,len(js),0x4e4f534a));out.write(js);out.write(struct.pack('<II',bytes_new+pad,0x004e4942));out.write(raw[base:base+binlen]);
    for block in appended:out.write(block)
    out.write(b'\0'*pad);out.flush();os.fsync(out.fileno())
   target_size,target_sha=OUTPUTS[stage]
   require(destination.stat().st_size==size_new==target_size and sha(destination)==target_sha,'candidate output differs from independently measured exact SHA')
  except BaseException:
   if destination.exists():destination.unlink()
   raise
  return {'schema':'skeleton.emerald.proximal-wingfold-build.v1','stage':stage,'candidate_bytes':size_new,'candidate_sha256':target_sha,'source_sha256':source_sha,'donor_sha256':DONOR,'corrected_tracks':tracks,'joints':[68,79,80,91],'growth_unchanged':True,'original_embedded_binary_prefix_exact':True,'continuous_collision_qualified':False,'equipment_enabled':False,'artist_approved':False,'unreal_compiled':False,'physical_rtx_verified':False,'release_qualified':False}
 finally:
  raw.close();f.close()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=SOURCES);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
 if a.receipt.exists():raise FileExistsError(a.receipt)
 report=build(a.stage,a.source,a.out);a.receipt.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
