"""All-or-none Git-bound approval and source indexing into native inference."""
from __future__ import annotations
from hashlib import sha256
from itertools import islice
from pathlib import Path
from .contracts import GitIndexItem,GitSourceError,git_path,document_for_path
from .git_objects import GitSource
from .sensitivity import require_publicly_indexable
from . import schema
from .. import ingest
from ..contracts import KnowledgeError


def kind_for(path:str)->str:
    suffix=Path(git_path(path)).suffix.lower()
    if suffix=='.py':return 'text/x-python'
    if suffix=='.md':return 'text/markdown'
    if suffix=='.json':return 'application/json'
    return 'text/plain'


def index_repository(plane, *, repo_root, commit:str, items,
                     approved:bool=False, maximum:int=32)->tuple[dict,...]:
    if approved is not True:
        raise GitSourceError('independent Git source ingestion approval required')
    if type(maximum)is not int or not 1<=maximum<=64:
        raise GitSourceError('invalid finite Git source ingestion ceiling')
    entries=tuple(islice(iter(items),maximum+1))
    if not entries or len(entries)>maximum or any(not isinstance(x,GitIndexItem) for x in entries):
        raise GitSourceError('empty, unbounded or malformed Git source batch')
    if len({x.path for x in entries})!=len(entries):
        raise GitSourceError('duplicate Git path in import batch')
    source=GitSource(repo_root,commit=commit)
    inventory=source.inventory()
    prepared=[];total=0
    for item in entries:
        blob=source.read(item.path,inventory,maximum_bytes=plane.policy.max_document_bytes)
        require_publicly_indexable(blob.raw)
        total+=len(blob.raw)
        if total>min(plane.policy.max_total_bytes,32*1024*1024):
            raise GitSourceError('Git import batch byte budget exceeded')
        prepared.append((item,blob))
    schema.install(plane.db)
    with plane.db.transaction() as conn:
        schema.verify(conn)
        records=[]
        for item,blob in prepared:
            doc_id=document_for_path(blob.path)
            record,replayed=ingest.ingest(conn,plane.identity,blob.raw,
                    doc_id=doc_id,title=blob.path[:plane.policy.max_title_chars],
                    rights=item.rights,kind=kind_for(blob.path),approved=True,
                    expected_revision=item.expected_revision,policy=plane.policy)
            recorded=conn.execute('SELECT path,commit_sha,blob_oid,raw_sha256 '
                'FROM ai_kb_git_lineage WHERE principal=? AND doc_id=? AND revision=?',
                (plane.identity.key(),doc_id,record.revision)).fetchone()
            proof=(blob.path,source.commit,blob.oid,blob.sha256)
            if recorded is not None and tuple(recorded)!=proof:
                raise GitSourceError('Git source replay conflicts with pinned provenance')
            if recorded is None:
                if replayed:raise GitSourceError('existing unprovenanced source requires explicit migration')
                conn.execute('INSERT INTO ai_kb_git_lineage VALUES (?,?,?,?,?,?,?)',
                  (plane.identity.key(),doc_id,record.revision,*proof))
            records.append(record.to_dict()|{'git_path':blob.path,'commit_sha':source.commit,
                        'blob_oid':blob.oid,'replayed':replayed})
        return tuple(records)
