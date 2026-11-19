"""Publish verified experimental Scholar wingfold bytes to its review-only draft.

Authorizes only an exact, original-donor-SHA-pinned, fast-forward Git commit.
Never edits main, alters the validated Hoarder, merges, releases, enables
equipment, or asserts continuous collision or artistic acceptance.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PIN=ROOT/'frontend/src/features/Jeeves/companion/atelier/scholarWingfoldPin.json'
MANIFEST=ROOT/'assets/emerald/evolution-v5/scholar-wingfold-r1/publication-manifest.json'
BRANCH='refs/heads/assets/emerald-scholar-wingfold-r1-20261117'
REMOTE={
 'https://github.com/Apeloff1/Skeleton',
 'https://github.com/Apeloff1/Skeleton.git',
 'git@github.com:Apeloff1/Skeleton.git',
 'ssh://git@github.com/Apeloff1/Skeleton.git',
}
MAX=32*1024**2

def require(value,reason):
 if not value: raise ValueError(reason)

def digest(data):return hashlib.sha256(data).hexdigest()

def load():
 pin=json.loads(PIN.read_bytes())
 raw=MANIFEST.read_bytes()
 require(len(raw)<=32768,'oversize exact manifest')
 m=json.loads(raw)
 require((m['schema'],m['stage'],m['candidate'])==(
  'skeleton.emerald.scholar-wingfold-publication.v1','scholar','scholar-wingfold-r1'),
  'unrecognized publication identity')
 require((m['bytes'],m['sha256'],m['source_sha256'],m['donor_sha256'],m['radians'])==(
  pin['bytes'],pin['sha256'],pin['sourceSha256'],pin['donorSha256'],pin['angleRadians']),
  'unauthorized model or source repin')
 for flag in ('automaticAdoption','hardwareQualified','artisticApproved',
              'continuousCollisionQualified','optionalEquipmentEnabled','releaseQualified'):
  require(pin[flag] is False,'candidate trust hold lifted: '+flag)
 require(m['automatic_adoption'] is False and m['artist_approved'] is False
         and m['continuous_clearance_qualified'] is False
         and m['physical_rtx_verified'] is False and m['release_qualified'] is False,
         'manifest falsely implies accepted model')
 total=0
 for i,row in enumerate(m['parts']):
  chunk=min(MAX,m['bytes']-total)
  require(chunk>0 and row=={
   'path':f'assets/emerald/evolution-v5/scholar-wingfold-r1/scholar.glb.part{i+1:03}',
   'offset':total,'bytes':chunk,'sha256':row['sha256'],
  } and re.fullmatch('[0-9a-f]{64}',row['sha256']),
  'missing, reordered or unpinned chunk')
  total+=chunk
 require(len(m['parts'])==4 and total==m['bytes'],'incomplete 113MB model')
 return m,raw

def chunks(bundle,m):
 bundle=Path(bundle)
 require(bundle.is_file() and not bundle.is_symlink(),'trusted existing ZIP required')
 with zipfile.ZipFile(bundle) as z:
  entries=z.infolist()
  require(0<len(entries)<=24 and sum(x.file_size for x in entries)<=200*1024**2,
          'unbounded archive expansion')
  seen=set()
  for e in entries:
   segments=e.filename.split('/')
   require(not e.is_dir() and not e.flag_bits&1 and
           not e.filename.startswith('/') and '\\' not in e.filename and
           all(x not in ('.','..','') for x in segments) and
           e.filename.casefold() not in seen,'unsafe ZIP member')
   seen.add(e.filename.casefold())
  entry=z.getinfo('scholar.glb')
  require(entry.file_size==m['bytes'],'wrong model size')
  a=json.loads(z.read('admission.json'))
  require(a['schema']=='skeleton.dragon.evolution.experimental-admission.v1'
          and a['stage']=='scholar' and a['candidate']=='scholar-wingfold-r1'
          and a['bytes']==m['bytes'] and a['sha256']==m['sha256']
          and a['source_sha256']==m['donor_sha256']
          and a['parent_model_sha256']==m['source_sha256']
          and a['local_z_radians']==m['radians']
          and a['preliminary_clearance_only'] is True
          and a['artist_approved'] is False
          and a['continuous_collision_qualified'] is False
          and a['equipment_enabled'] is False
          and a['release_qualified'] is False,
          'admission source or authority mismatch')
  sha=hashlib.sha256()
  with z.open(entry) as stream:
   for row in m['parts']:
    block=stream.read(row['bytes'])
    require(len(block)==row['bytes'] and digest(block)==row['sha256'],
            'changed or truncated model chunk '+row['path'])
    sha.update(block)
    yield row,block
   require(not stream.read(1),'unexpected model trailing bytes')
  require(sha.hexdigest()==m['sha256'],'whole corrected model digest mismatch')

def git(repo,*args,data=None,env=None):
 p=subprocess.run(['git','-C',str(repo),*args],input=data,stdout=subprocess.PIPE,
                  stderr=subprocess.PIPE,check=True,env=env)
 return p.stdout

def oid(data):
 val=data.decode('ascii').strip()
 require(re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})',val),'invalid Git object')
 return val

def check_remote(repo):
 for args in (('remote','get-url','origin'),('remote','get-url','--push','origin')):
  require(git(repo,*args).decode().strip() in REMOTE,'remote not authorized')

def fetch(repo,manifest):
 git(repo,'fetch','--no-tags','origin',BRANCH)
 head=oid(git(repo,'rev-parse','FETCH_HEAD'))
 relative=str(MANIFEST.relative_to(ROOT))
 require(git(repo,'show',head+':'+relative)==manifest,
         'review-only head no longer carries exact manifest')
 return head

def publish(repo,bundle,m,raw):
 head=fetch(repo,raw)
 with tempfile.TemporaryDirectory(prefix='scholar-custody-index-') as temp:
  env=dict(os.environ,GIT_INDEX_FILE=str(Path(temp)/'index'))
  git(repo,'read-tree',head,env=env)
  for row,block in chunks(bundle,m):
   blob=oid(git(repo,'hash-object','-w','--no-filters','--stdin',data=block))
   present=git(repo,'ls-tree',head,'--',row['path']).decode().strip()
   if present:
    require(present==f"100644 blob {blob}\t{row['path']}",
            'refuse to overwrite different model chunk')
   else:
    git(repo,'update-index','--add','--cacheinfo',
        f"100644,{blob},{row['path']}",env=env)
  tree=oid(git(repo,'write-tree',env=env))
 if tree!=oid(git(repo,'rev-parse',head+'^{tree}')):
  head=oid(git(repo,'commit-tree',tree,'-p',head,'-m',
               'assets(dragon): verified experimental Scholar wingfold binary'))
  git(repo,'push','origin',head+':'+BRANCH)
 require(git(repo,'ls-remote','--exit-code','origin',BRANCH).decode().split()==[
  head,BRANCH],'remote changed before complete publication')
 return head

def verify_tree(repo,m):
 sha=hashlib.sha256()
 for row in m['parts']:
  path=repo/row['path']
  require(path.is_file() and not path.is_symlink()
          and path.stat().st_size==row['bytes'],
          'required binary chunk absent: '+row['path'])
  with path.open('rb') as stream: block=stream.read()
  require(digest(block)==row['sha256'],'published chunk digest mismatch')
  sha.update(block)
 require(sha.hexdigest()==m['sha256'],'published complete GLB SHA mismatch')
 return {'stage':'scholar','bytes':m['bytes'],'sha256':m['sha256'],
         'chunks':len(m['parts']),'binary_integrity_qualified':True,
         'collision_qualified':False,'artist_approved':False,
         'physical_rtx_verified':False,'release_qualified':False}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('action',choices=('verify-bundle','publish','verify-tree'))
 p.add_argument('--bundle',type=Path)
 p.add_argument('--repo',type=Path,default=ROOT)
 a=p.parse_args()
 m,raw=load()
 if a.action=='verify-tree':
  print(json.dumps(verify_tree(a.repo,m),indent=2))
  return
 require(a.bundle is not None,'--bundle mandatory')
 for _ in chunks(a.bundle,m):pass
 if a.action=='verify-bundle':
  print(json.dumps({'exact_original_scholar_candidate':True,
                    'remote_published':False,'collision_qualified':False,
                    'release_qualified':False},indent=2))
  return
 check_remote(a.repo)
 head=publish(a.repo,a.bundle,m,raw)
 print(json.dumps({'branch':BRANCH,'verified_remote_sha':head},indent=2))

if __name__=='__main__':main()
