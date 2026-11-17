"""Original-donor V4 skinned-triangle contact scanner (offline, bounded, fail-closed).

Samples high-risk joint-dominant mesh regions across *actual* animation
channels. Reports 0 contacts only within those sampled classified surfaces.
Unclassified seams, nonlinear between-frame motion, morph intermediates,
equipment, artist review and physical GPU/Unreal remain unqualified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import mmap
from pathlib import Path
import re
import struct
import time
import traceback
import zipfile

import numpy as np
from scipy.spatial.transform import Rotation

from emerald_v4_contact_geometry import IncompleteAudit, witness

ROOT=Path(__file__).resolve().parents[1]
PIN=ROOT/'frontend/src/features/Jeeves/companion/atelier/evolutionPin.json'
DONOR='c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a'
STAGES=('hatchling','scout','scholar','pathfinder','archivist')
REGIONS={
 'head':tuple(range(8,14)), 'fore_near':tuple(range(14,19)),
 'fore_far':tuple(range(19,24)), 'hind_near':tuple(range(24,29)),
 'hind_far':tuple(range(29,34)), 'wing_near':tuple(range(68,80)),
 'wing_far':tuple(range(80,92)),
}
PAIRS=(
 ('wing_near','head'),('wing_far','head'),
 ('wing_near','fore_near'),('wing_near','hind_near'),
 ('wing_far','fore_far'),('wing_far','hind_far'),
 ('wing_near','wing_far'),
)
CLIPS=('ground-idle-1','ground-cuddle-1','ground-stretch-1',
       'takeoff-1','orbit-01','landing-1')

def require(ok,why):
 if not ok:raise ValueError(why)

def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def source_pin(stage):
 require(stage in STAGES,'unknown development stage')
 pin=json.loads(PIN.read_bytes())
 require(pin['donorSha256']==DONOR and pin['forms'][stage]['equipmentEnabled'] is False,
         'wrong donor or optional equipment enabled')
 return pin['forms'][stage]

class GLB:
 def __init__(self,path,identity,stage):
  require(path.is_file() and not path.is_symlink() and path.stat().st_size==identity['bytes']
          and sha(path)==identity['sha256'],'original-donor model byte identity mismatch')
  self.f=path.open('rb');self.raw=mmap.mmap(self.f.fileno(),0,access=mmap.ACCESS_READ)
  try:
   require(len(self.raw)>=32,'truncated GLB')
   magic,version,actual,jlen,kind=struct.unpack_from('<4sIIII',self.raw)
   require((magic,version,actual,kind)==(b'glTF',2,len(self.raw),0x4e4f534a)
           and 0<jlen<=32*1024**2 and jlen%4==0,'invalid GLB structure')
   size,k=struct.unpack_from('<II',self.raw,20+jlen)
   self.offset=28+jlen
   require(k==0x004e4942 and size+self.offset==len(self.raw),'invalid binary chunk')
   self.d=json.loads(self.raw[20:20+jlen])
   doc=self.d
   require(doc['asset']['version']=='2.0'
           and doc['extras']['stage']==stage
           and doc['extras']['donorSha256']==DONOR,'wrong stage or source identity')
   require(len(doc['skins'])==1 and len(doc['skins'][0]['joints'])==108
           and len(doc['animations'])==381,'wrong weighted skin or source repertoire')
   require(len(doc['buffers'])==1 and 'uri' not in doc['buffers'][0]
           and doc['buffers'][0]['byteLength']<=size,'external GLB binary not permitted')
   self.clips={a['name']:a for a in doc['animations']}
   require(len(self.clips)==381,'duplicate animation')
  except BaseException:
   self.close()
   raise

 def acc(self,index):
  a=self.d['accessors'][index];v=self.d['bufferViews'][a['bufferView']]
  require('sparse' not in a and 'byteStride' not in v and v['buffer']==0,
          'unsupported accessor')
  cols={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']]
  dtype={5126:'<f4',5123:'<u2',5125:'<u4'}[a['componentType']]
  length=cols*a['count']*np.dtype(dtype).itemsize
  local=a.get('byteOffset',0);offset=v.get('byteOffset',0)+local
  require(a['count']>0 and 0<=local and local+length<=v['byteLength']
          and offset+length<=self.d['buffers'][0]['byteLength'],
          'accessor outside local embedded buffer')
  return np.frombuffer(self.raw,dtype,cols*a['count'],self.offset+offset).reshape(-1,cols)

 def geometry(self):
  d=self.d;joints=d['skins'][0]['joints'];lookup={node:i for i,node in enumerate(joints)}
  parents=np.full(108,-1,'i4')
  for i,node in enumerate(joints):
   for c in d['nodes'][node].get('children',[]):
    if c in lookup:parents[lookup[c]]=i
  require(parents[0]==-1 and np.all(parents[1:]>=0)
          and np.all(parents[1:]<np.arange(1,108)),'bad hierarchy')
  inverse=self.acc(d['skins'][0]['inverseBindMatrices']).reshape(108,4,4).transpose(0,2,1)
  rest=-inverse[:,:3,3].astype('f8')
  arrays={k:[] for k in ('positions','faces','joints','weights')}
  cursor=0
  for primitive in d['meshes'][0]['primitives']:
   a=primitive['attributes'];pos=self.acc(a['POSITION'])
   j=self.acc(a['JOINTS_0']);w=self.acc(a['WEIGHTS_0'])
   faces=self.acc(primitive['indices']).reshape(-1,3)
   require(len(pos)==len(j)==len(w) and faces.max()<len(pos),'broken skin geometry')
   arrays['positions'].append(pos);arrays['joints'].append(j)
   arrays['weights'].append(w);arrays['faces'].append(faces+cursor)
   cursor+=len(pos)
  g={k:np.concatenate(v) for k,v in arrays.items()}
  g.update(rest=rest,parents=parents,joint_nodes=joints,lookup=lookup)
  require(len(g['positions'])==365997 and len(g['faces'])==719312
          and g['joints'].max()<108 and np.max(abs(g['weights'].sum(1)-1))<2e-5,
          'original topology or weights mismatch')
  return g

 def skinned(self,g,clip,fraction):
  require(clip in self.clips and not clip.startswith('growth-'),
          'invalid source animation')
  d=self.d;nodes=g['joint_nodes']
  t=np.array([d['nodes'][n].get('translation',[0,0,0]) for n in nodes],dtype='f8')
  q=np.array([d['nodes'][n].get('rotation',[0,0,0,1]) for n in nodes],dtype='f8')
  animation=self.clips[clip]
  duration=max(float(self.acc(s['input'])[-1,0]) for s in animation['samplers'])
  now=duration*fraction
  for channel in animation['channels']:
   sampler=animation['samplers'][channel['sampler']]
   ts=self.acc(sampler['input']).ravel();values=self.acc(sampler['output'])
   k=int(np.clip(np.searchsorted(ts,now)-1,0,len(ts)-2))
   f=float(np.clip((now-ts[k])/max(1e-12,ts[k+1]-ts[k]),0,1))
   prop=channel['target']['path']
   require(prop in ('rotation','translation'),'unsupported source animation')
   i=g['lookup'][channel['target']['node']]
   if prop=='translation':t[i]=values[k]*(1-f)+values[k+1]*f
   else:
    a=values[k].astype('f8');b=values[k+1].astype('f8')
    a/=max(1e-12,np.linalg.norm(a));b/=max(1e-12,np.linalg.norm(b))
    dp=float(np.dot(a,b))
    if dp<0:b=-b;dp=-dp
    angle=math.acos(float(np.clip(dp,-1,1)))
    value=a*(1-f)+b*f if angle<1e-6 else (
       math.sin((1-f)*angle)*a+math.sin(f*angle)*b)/math.sin(angle)
    q[i]=value/max(1e-12,np.linalg.norm(value))
  m=np.broadcast_to(np.eye(4),(108,4,4)).copy()
  m[:,:3,:3]=Rotation.from_quat(q).as_matrix()
  m[:,:3,3]=t
  for i in range(1,108):m[i]=m[g['parents'][i]]@m[i]
  m[:,:3,3]-=np.einsum('nij,nj->ni',m[:,:3,:3],g['rest'])
  skin=m[g['joints']]
  points=g['positions'].astype('f8')
  return np.einsum('nk,nkj->nj',g['weights'],
    np.einsum('nkij,nj->nki',skin[:,:,:3,:3],points)+skin[:,:,:3,3])

 def close(self):
  try:self.raw.close()
  except BufferError:pass
  self.f.close()

def classify(g):
 choices=np.argmax(g['weights'],axis=1)
 dominant=g['joints'][np.arange(len(choices)),choices]
 strength=g['weights'][np.arange(len(choices)),choices]
 groups={}
 covered=np.zeros(len(g['faces']),bool)
 for name,joints in REGIONS.items():
  selected=np.flatnonzero(np.all((np.isin(dominant,joints)&(strength>=.4))[g['faces']],axis=1))
  groups[name]=selected;covered[selected]=True
 return groups,{'region_triangles':{k:int(len(v)) for k,v in groups.items()},
                'classified_triangles':int(covered.sum()),
                'unclassified_seam_and_other_triangles':int((~covered).sum())}

def audit(path,stage,clips,fractions,margin,max_pairs,deadline):
 identity=source_pin(stage);model=GLB(path,identity,stage)
 try:
  g=model.geometry();groups,census=classify(g)
  require(all(len(v)>0 for v in groups.values()),'missing classified anatomical region')
  rows=[];contact_total=0
  for clip in clips:
   for fraction in fractions:
    if time.monotonic()>deadline:raise IncompleteAudit('total scan time exhausted')
    positions=model.skinned(g,clip,fraction)
    require(np.isfinite(positions).all(),'nonfinite weighted vertices')
    pairs={}
    for a,b in PAIRS:
     if time.monotonic()>deadline:raise IncompleteAudit('pair scan time exhausted')
     faces_a=groups[a];faces_b=groups[b]
     result=witness(positions[g['faces'][faces_a]],
                    positions[g['faces'][faces_b]],
                    faces_a,faces_b,margin,max_pairs,deadline)
     contact_total+=result['contact_count'];pairs[a+'__'+b]=result
    rows.append({'clip':clip,'fraction':fraction,'contacts':pairs})
  return {'schema':'skeleton.emerald.sampled-triangle-contact.v2',
          'stage':stage,'sha256':identity['sha256'],'bytes':identity['bytes'],
          'donor_sha256':DONOR,'scan_complete':True,'poses':len(rows),
          'clips':list(clips),'fractions':list(fractions),'margin_m':margin,
          'triangle_coverage':census,'sampled_contact_count':contact_total,
          'unresolved_nonlinear_intervals':len(clips)*(len(fractions)-1),
          'continuous_collision_qualified':False,'all_morphs_qualified':False,
          'optional_equipment_enabled':False,'physical_rtx_verified':False,
          'artist_approved':False,'release_qualified':False,'evidence':rows}
 finally:model.close()

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--model',type=Path,required=True)
 ap.add_argument('--stage',required=True,choices=STAGES)
 ap.add_argument('--output',type=Path,required=True)
 ap.add_argument('--clips',default=','.join(CLIPS))
 ap.add_argument('--fractions',default='0,0.5,1')
 ap.add_argument('--margin',type=float,default=.008)
 ap.add_argument('--max-pairs',type=int,default=200000)
 ap.add_argument('--timeout',type=float,default=120)
 args=ap.parse_args()
 clips=tuple(args.clips.split(','))
 fractions=tuple(float(x) for x in args.fractions.split(','))
 require(0<len(clips)<=380 and len(set(clips))==len(clips)
         and all(re.fullmatch('[a-z0-9-]{1,80}',c) for c in clips),
         'invalid source clips')
 require(2<=len(fractions)<=257 and fractions[0]==0 and fractions[-1]==1
         and all(0<=x<=1 and math.isfinite(x) for x in fractions)
         and all(a<b for a,b in zip(fractions,fractions[1:])), 'bad sample spacing')
 require(math.isfinite(args.timeout) and 1<=args.timeout<=7200,'invalid timeout')
 require(args.output.parent.is_dir() and not args.output.exists(),
         'new receipt must be inside existing trusted directory')
 started=time.monotonic()
 try:
  report=audit(args.model,args.stage,clips,fractions,
               args.margin,args.max_pairs,started+args.timeout)
 except IncompleteAudit as error:
  report={'schema':'skeleton.emerald.sampled-triangle-contact.v2',
          'stage':args.stage,'scan_complete':False,
          'reason':str(error),'continuous_collision_qualified':False,
          'optional_equipment_enabled':False,'release_qualified':False}
 report['elapsed_seconds']=time.monotonic()-started
 with args.output.open('x',encoding='utf8') as dest:
  json.dump(report,dest,indent=2,allow_nan=False)
  dest.write('\n')
 print(json.dumps({k:v for k,v in report.items() if k!='evidence'},indent=2))
 if not report['scan_complete']:raise SystemExit(3)
 if report['sampled_contact_count']:raise SystemExit(2)

if __name__=='__main__':main()
