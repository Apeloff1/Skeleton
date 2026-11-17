"""Exact original Emerald transfer. No repository checkout, ref writes or app release."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import urllib.request
from contextlib import contextmanager

REPO = 'https://github.com/Apeloff1/Skeleton.git'
COMMIT = 'd82d61541bc7ae3cb4bd2599b5836431828f79d7'
MEDIA = 'https://media.githubusercontent.com/media/Apeloff1/Skeleton/' + COMMIT + '/artifacts/emerald/original-r1/'
ASSETS = (
    ('emerald_continuum.glb',463149740,'c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a'),
    ('emerald-atelier-fold-source.zip',194733639,'093feccb25846b39eefe94a4385873e25df125371544545042c3d34b3fe879f5'),
    ('emerald-skeleton-web-assets.zip',48249605,'354b7d1dadc02f7919aa6b9b802f949894d2cb6ea0e0e493db9ba9d819d22851'),
)
PARTS = (
    ('emerald_continuum.glb.part01',231574870,'db8a76f932dfc5db50f5097c1850d9e23a80d62810812962bd352d9b560329b0'),
    ('emerald_continuum.glb.part02',231574870,'52594a7e9246d55dc610b262a2524b2e5a41709d1162dfdb359b40cea2415466'),
)
CHUNK = 1024*1024


def identity(s):
    return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns


@contextmanager
def ordinary(path):
    before=path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('Not an ordinary file: '+path.name)
    flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0)|getattr(os,'O_BINARY',0)
    with os.fdopen(os.open(path,flags),'rb') as src:
        opened=os.fstat(src.fileno())
        if identity(before)!=identity(opened) or not stat.S_ISREG(opened.st_mode):
            raise ValueError('File replaced: '+path.name)
        yield src,opened
        if identity(opened)!=identity(os.fstat(src.fileno())):
            raise ValueError('File changed while reading: '+path.name)


def consume(stream,size,sha,destination=None,combined=None):
    h=hashlib.sha256(); remaining=size
    while remaining:
        block=stream.read(min(CHUNK,remaining))
        if not block: raise ValueError('Truncated payload')
        h.update(block);remaining-=len(block)
        if combined is not None: combined.update(block)
        if destination is not None: destination.write(block)
    if stream.read(1) or h.hexdigest()!=sha:
        raise ValueError('Pinned length or digest mismatch')


def verify_local(directory,row,destination=None):
    name,size,sha=row
    path=directory/name
    if os.path.lexists(path):
        with ordinary(path) as (src,st):
            if st.st_size!=size: raise ValueError('Wrong file length: '+name)
            consume(src,size,sha,destination)
    elif name==ASSETS[0][0]:
        combined=hashlib.sha256()
        if sum(p[1] for p in PARTS)!=size: raise ValueError('Invalid part lengths')
        for part,n,digest in PARTS:
            with ordinary(directory/part) as (src,st):
                if st.st_size!=n: raise ValueError('Wrong part length: '+part)
                consume(src,n,digest,destination,combined)
        if combined.hexdigest()!=sha: raise ValueError('Joined model digest mismatch')
    else:
        raise FileNotFoundError(path)


class HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not newurl.startswith('https://'):
            raise ValueError('Remote redirect is not HTTPS')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def verify_remote(row,destination=None):
    name,size,sha=row
    opener=urllib.request.build_opener(HttpsOnlyRedirect())
    request=urllib.request.Request(MEDIA+name,headers={'Accept-Encoding':'identity','User-Agent':'Skeleton-Emerald-Custody/1'})
    with opener.open(request,timeout=90) as src:
        if src.status!=200: raise ValueError('Remote did not return a complete object')
        length=src.headers.get('Content-Length')
        if length is not None and int(length)!=size:
            raise ValueError('Remote object is missing or has wrong length: '+name)
        consume(src,size,sha,destination)


def publish_download(directory):
    if not directory.is_dir() or directory.is_symlink(): raise ValueError('Use an existing trusted output directory')
    for name,_,_ in ASSETS:
        if os.path.lexists(directory/name): raise FileExistsError(directory/name)
    with tempfile.TemporaryDirectory(prefix='.emerald-download-',dir=directory) as tmp:
        staging=Path(tmp)
        for row in ASSETS:
            with (staging/row[0]).open('xb') as out:
                verify_remote(row,out);out.flush();os.fsync(out.fileno())
        created=[]
        try:
            for name,_,_ in ASSETS:
                target=directory/name;os.link(staging/name,target);created.append(target)
        except OSError:
            for target in reversed(created):
                if os.path.samefile(staging/target.name,target): target.unlink()
            raise


def git_run(root,*args):
    subprocess.run(['git','-C',str(root),*args],check=True)


def upload(directory):
    # A private temporary repository holds only the three pinned objects, not Skeleton's Git tree.
    # The installed Git credential helper is responsible for authentication. No token is requested or stored here.
    with tempfile.TemporaryDirectory(prefix='emerald-lfs-') as tmp:
        root=Path(tmp)
        git_run(root,'init','--quiet')
        git_run(root,'lfs','version')
        git_run(root,'remote','add','origin',REPO)
        storage=root/'storage'
        git_run(root,'config','--local','lfs.storage',str(storage))
        git_run(root,'config','--local','lfs.url',REPO+'/info/lfs')
        git_run(root,'config','--local','lfs.pushurl',REPO+'/info/lfs')
        for row in ASSETS:
            _,_,sha=row
            target=storage/'objects'/sha[:2]/sha[2:4]/sha
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as out:
                verify_local(directory,row,out)
        git_run(root,'lfs','push','--object-id','origin',*(row[2] for row in ASSETS))
    # Upload success alone is not remote byte custody. Read the exact pointer commit independently.
    for row in ASSETS: verify_remote(row)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,default=Path.cwd())
    mode=p.add_mutually_exclusive_group()
    mode.add_argument('--upload',action='store_true',help='explicit authenticated upload, then full remote readback')
    mode.add_argument('--verify-remote',action='store_true',help='read exact remote objects without writing')
    mode.add_argument('--download',action='store_true',help='download all three verified bytesets, never overwrite')
    a=p.parse_args();directory=a.directory.absolute()
    try:
        if a.upload: upload(directory)
        elif a.download: publish_download(directory)
        elif a.verify_remote:
            for row in ASSETS: verify_remote(row)
        else:
            for row in ASSETS: verify_local(directory,row)
    except (OSError,ValueError,subprocess.CalledProcessError) as exc:
        p.exit(2,'Custody not established: '+str(exc)+'\n')
    print(json.dumps({'schema':'skeleton.emerald.lfs-transfer.v1','pointer_commit':COMMIT,
                      'assets':[{'name':n,'bytes':s,'sha256':h} for n,s,h in ASSETS],
                      'local_verified':not a.verify_remote,'remote_verified':a.upload or a.verify_remote or a.download,
                      'application_release':False,'physical_rtx_verified':False},indent=2))


if __name__=='__main__': main()
