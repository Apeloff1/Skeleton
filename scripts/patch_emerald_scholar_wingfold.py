"""Append-only, source-bound Scholar wing-fold candidate exporter.

Experimental local-only art. No mesh/rig/UV/material changes, original growth
clip changes, Hoarder mutation, equipment, auto-adoption or CCD assertion.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,math,mmap,os,struct
from pathlib import Path
import numpy as np

DONOR_SHA='c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a'
SCHOLAR_V4_SHA='db15c598fe3c6ef71384ca5f834c7eb2271014819ff0603207d454a87c03fdb9'
SCHOLAR_V4_BYTES=112509064
STAGE='scholar'
TARGET_RIG_IDS=(79,91)

def require(value,reason):
 if not value:raise ValueError(reason)

def sha(path):
 with Path(path).open('rb') as src:return hashlib.file_digest(src,'sha256').hexdigest()

def quat_correct(values,angle):
 """Hamilton q * localZ(angle), independent of library quaternion ordering."""
 require(values.ndim==2 and values.shape[1]==4 and np.isfinite(values).all(),'rotation keys shape')
 require(np.max(abs(np.linalg.norm(values,axis=1)-1))<2e-5,'original nonunit quaternions')
 s,c=math.sin(angle/2),math.cos(angle/2)
 x,y,z,w=values.T.astype(np.float64)
 out=np.column_stack((c*x+s*y,c*y-s*x,c*z+s*w,c*w-s*z))
 out/=np.linalg.norm(out,axis=1)[:,None]
 require(np.isfinite(out).all(),'invalid corrected quaternions')
 return np.ascontiguousarray(out,dtype='<f4')

def read_source(path):
 path=Path(path)
 require(path.is_file() and not path.is_symlink() and path.stat().st_size==SCHOLAR_V4_BYTES and sha(path)==SCHOLAR_V4_SHA,'wrong original Scholar model')
 f=path.open('rb');raw=mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ)
 try:
  require(len(raw)>=32,'truncated input')
  magic,version,total,json_len,json_tag=struct.unpack_from('<4sIIII',raw)
  require((magic,version,total,json_tag)==(b'glTF',2,len(raw),0x4e4f534a) and json_len<=32*1024**2,'unsupported GLB')
  binary_len,binary_tag=struct.unpack_from('<II',raw,20+json_len)
  start=28+json_len
  require(binary_tag==0x004e4942 and start+binary_len==total,'unsupported binary length')
  doc=json.loads(raw[20:20+json_len])
  require(doc['asset']['version']=='2.0' and doc['extras']['stage']==STAGE and doc['extras']['donorSha256']==DONOR_SHA,'wrong model lineage')
  require(len(doc['skins'])==1 and len(doc['skins'][0]['joints'])==108 and len(doc['animations'])==381,'source rig/clip mismatch')
  return f,raw,doc,start,binary_len
 except BaseException:
  raw.close();f.close();raise

def accessor(mm,doc,start,index):
 row=doc['accessors'][index];view=doc['bufferViews'][row['bufferView']]
 require(row['type']=='VEC4' and row['componentType']==5126 and row['count']>0 and 'sparse' not in row and 'byteStride' not in view,'unsafe rotation accessor')
 offset=view.get('byteOffset',0)+row.get('byteOffset',0)
 length=row['count']*16
 require(offset>=0 and row.get('byteOffset',0)+length<=view['byteLength'] and offset+length<=doc['buffers'][0]['byteLength'],'accessor bounds')
 return np.frombuffer(mm,dtype='<f4',count=row['count']*4,offset=start+offset).reshape(-1,4)

def build(path,destination,angle):
 require(isinstance(angle,(int,float)) and math.isfinite(angle) and 0.05<=angle<=0.35,'corrective angle out of reviewed bound')
 destination=Path(destination)
 require(destination.parent.is_dir() and not destination.parent.is_symlink() and not os.path.lexists(destination),'new file in trusted parent required')
 f,raw,doc,start,initial=read_source(path)
 try:
  d=copy.deepcopy(doc)
  ids=set(d['skins'][0]['joints'][i] for i in TARGET_RIG_IDS)
  names=[item['name'] for item in d['animations']]
  require(len(names)==len(set(names)) and names[-1]=='growth-scholar-to-pathfinder','growth source identity')
  original_views=len(d['bufferViews']);original_accessors=len(d['accessors'])
  additions=[];bytes_new=initial;edited_tracks=0;fixed_clips=0
  for anim in d['animations'][:380]:
   seen=set()
   for channel in anim['channels']:
    target=channel['target'];node=target['node'];prop=target['path']
    if node not in ids or prop!='rotation':continue
    require(node not in seen,'duplicate rotation for terminal joint')
    seen.add(node)
    sampler=anim['samplers'][channel['sampler']]
    old=accessor(raw,doc,start,sampler['output'])
    edited=quat_correct(old,angle)
    padding=(-bytes_new)%4
    additions.append(b'\0'*padding)
    bytes_new+=padding
    view=len(d['bufferViews']);d['bufferViews'].append({'buffer':0,'byteOffset':bytes_new,'byteLength':edited.nbytes})
    acc=len(d['accessors']);d['accessors'].append({'bufferView':view,'componentType':5126,'count':len(edited),'type':'VEC4'})
    sampler['output']=acc
    additions.append(edited.tobytes())
    bytes_new+=edited.nbytes
    edited_tracks+=1
    del old,edited
   require(seen==ids,'missing original terminal rotation in '+anim['name'])
   fixed_clips+=1
  require(fixed_clips==380 and edited_tracks==760,'incomplete source motion correction')
  require(d['animations'][-1]==doc['animations'][-1],'growth animation modified')
  d['buffers'][0]['byteLength']=bytes_new
  d['asset']['generator']='Emerald original-donor Scholar wing-fold candidate r1'
  d['extras']['wingFoldCorrection']={
   'kind':'experimental-terminal-joint-post-rotation',
   'joint_ids':list(TARGET_RIG_IDS),'local_z_radians':angle,
   'source_model_sha256':SCHOLAR_V4_SHA,
   'source_donor_sha256':DONOR_SHA,
   'original_tracks_modified':False,'original_growth_unchanged':True,
   'continuous_clearance_verified':False,'artist_approved':False,
   'physical_rtx_verified':False,'equipment_enabled':False,
   'release_qualified':False,
  }
  js=json.dumps(d,ensure_ascii=False,separators=(',',':')).encode('utf-8')
  js+=b' '*((-len(js))%4)
  padding=(-bytes_new)%4
  bytes_new+=padding
  total=28+len(js)+bytes_new
  require(total<512*1024**2,'safety cap')
  with destination.open('xb') as out:
   out.write(struct.pack('<4sIIII',b'glTF',2,total,len(js),0x4e4f534a))
   out.write(js)
   out.write(struct.pack('<II',bytes_new,0x004e4942))
   out.write(raw[start:start+initial])
   for a in additions:out.write(a)
   out.write(b'\0'*padding)
   out.flush();os.fsync(out.fileno())
  require(destination.stat().st_size==total,'output size mismatch')
  return {
   'schema':'skeleton.emerald.scholar-wingfold-candidate.v1',
   'stage':STAGE,'bytes':total,'sha256':sha(destination),
   'source_sha256':SCHOLAR_V4_SHA,'donor_sha256':DONOR_SHA,
   'radians':angle,'fixed_clips':fixed_clips,
   'appended_output_accessors':edited_tracks,
   'source_accessors':original_accessors,
   'original_buffer_views':original_views,
   'appended_bytes':bytes_new-initial,
   'original_mesh_and_material_bytes_exact':True,
   'growth_animation_reference_unchanged':True,
   'continuous_clearance_verified':False,'artist_approved':False,
   'equipment_enabled':False,'physical_rtx_verified':False,
   'release_qualified':False,
  }
 finally:
  raw.close();f.close()

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--source',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True)
 p.add_argument('--report',type=Path,required=True)
 p.add_argument('--radians',type=float,default=.18)
 args=p.parse_args()
 require(args.report.parent.is_dir() and not args.report.exists(),'new report required')
 result=build(args.source,args.output,args.radians)
 args.report.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
