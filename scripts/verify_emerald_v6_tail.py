"""Independent V6 candidate inspection against exact original V5 model bytes."""
from __future__ import annotations
import argparse,hashlib,json,mmap,struct
from pathlib import Path
import numpy as np
from emerald_v6_tail_clearance import PINNED,OUTPUTS,DONOR,CLIPS,ANGLE,JOINT,open_exact,digest,quat_post_y,rotation_accessor,require

def read_doc(raw):
 magic,ver,total,jslen,tag=struct.unpack_from('<4sIIII',raw)
 require((magic,ver,total,tag)==(b'glTF',2,len(raw),0x4e4f534a) and
         0<jslen<=32*1024**2 and jslen%4==0,'unsupported candidate GLB')
 n,kind=struct.unpack_from('<II',raw,20+jslen)
 start=28+jslen
 require(kind==0x004e4942 and start+n==len(raw),'candidate binary mismatch')
 return json.loads(raw[20:20+jslen]),start,n

def verify(stage,src,out):
 require(stage in PINNED and stage in OUTPUTS,'unknown stage')
 source_file,old_raw,old,old_start,old_bin=open_exact(src,stage)
 expected_size,expected_sha=OUTPUTS[stage]
 out=Path(out)
 require(out.is_file() and not out.is_symlink() and
         out.stat().st_size==expected_size and digest(out)==expected_sha,
         'new model hash or byte count mismatch')
 stream=out.open('rb');raw=mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ)
 try:
  doc,start,binlen=read_doc(raw)
  require(raw[start:start+old_bin]==old_raw[old_start:old_start+old_bin],
          'source mesh, textures or motion binary prefix changed')
  preserved=set(old)-{'asset','extras','buffers','accessors','bufferViews','animations'}
  require(all(doc[k]==old[k] for k in preserved) and
          doc['asset']['version']==old['asset']['version'],
          'source topology, skin, nodes or material declarations modified')
  require(len(doc['animations'])==len(old['animations'])==381 and
          doc['animations'][-1]==old['animations'][-1],
          'next-form growth clip is not bit-identical')
  require(len(doc['accessors'])==len(old['accessors'])+2 and
          len(doc['bufferViews'])==len(old['bufferViews'])+2,
          'exactly two new quaternion streams required')
  require(doc['accessors'][:len(old['accessors'])]==old['accessors']
          and doc['bufferViews'][:len(old['bufferViews'])]==old['bufferViews'],
          'original buffer views or accessors modified')
  require(all(doc['extras'][k]==v for k,v in old['extras'].items()),
          'original metadata changed')
  correction=doc['extras']['tailClearanceCorrection']
  require(correction['source_v5_sha256']==PINNED[stage][1] and
          correction['original_hoarder_donor_sha256']==DONOR and
          correction['joint_index']==JOINT and
          correction['local_y_radians']==ANGLE and
          correction['clips']==list(CLIPS) and
          all(correction[k] is False for k in (
              'equipment_enabled','cross_clip_transition_qualified',
              'full_continuous_collision_qualified','artist_approved',
              'physical_rtx_verified','release_qualified')),
          'unreviewed correction metadata or false qualification')
  target=old['skins'][0]['joints'][JOINT]
  corrected=[];unchanged=0;maximum_error=0.
  for before,after in zip(old['animations'],doc['animations']):
   require(before['name']==after['name'] and before['channels']==after['channels']
           and len(before['samplers'])==len(after['samplers']),
           'original animation name, channels or topology modified')
   seen=0
   for channel in before['channels']:
    index=channel['sampler'];b=before['samplers'][index];a=after['samplers'][index]
    special=(before['name'] in CLIPS and
             channel['target']['node']==target and
             channel['target']['path']=='rotation')
    if special:
     require(a['input']==b['input'] and a['interpolation']==b['interpolation']=='LINEAR',
             'source timebase changed')
     expected=quat_post_y(rotation_accessor(old_raw,old,old_start,b['output']))
     actual=rotation_accessor(raw,doc,start,a['output'])
     require(actual.shape==expected.shape,'corrected keyframe count changed')
     err=float(np.max(np.abs(expected-actual)))
     require(err<=4e-7,'candidate quaternion value does not match local-Y correction')
     maximum_error=max(maximum_error,err);seen+=1
     corrected.append({'clip':before['name'],'keys':len(expected)})
    else:
     require(a==b,'unapproved animation sampler changed')
     unchanged+=1
   if before['name'] in CLIPS:require(seen==1,'missing original tail-root track')
  require(len(corrected)==2 and sum(x['keys'] for x in corrected)==278,
          'incomplete orbit/landing correction')
  return {'schema':'skeleton.emerald.v6.independent-byte-verification.v1',
          'stage':stage,'source_sha256':PINNED[stage][1],
          'candidate_sha256':expected_sha,'candidate_bytes':expected_size,
          'corrected_tracks':corrected,'other_unchanged_channels':unchanged,
          'max_rotation_error':maximum_error,
          'original_mesh_skin_materials_exact':True,'growth_clip_exact':True,
          'original_embedded_binary_prefix_exact':True,
          'cross_clip_transition_qualified':False,
          'continuous_collision_qualified':False,
          'artist_approved':False,'physical_rtx_verified':False,
          'release_qualified':False}
 finally:
  raw.close();stream.close();old_raw.close();source_file.close()

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('stage',choices=PINNED)
 p.add_argument('--source',required=True,type=Path)
 p.add_argument('--candidate',required=True,type=Path)
 a=p.parse_args()
 print(json.dumps(verify(a.stage,a.source,a.candidate),indent=2))
