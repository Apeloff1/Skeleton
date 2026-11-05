"""Independent Git-tree source proof, not a signature or model quality claim."""
from __future__ import annotations
from hashlib import sha256
from .contracts import GitSourceError,document_for_path,git_path
from .git_objects import GitSource
from .schema import verify
from ..decode import decode_source


def inspect_repository(plane,*,repo_root,maximum:int=32)->dict:
    if type(maximum)is not int or not 1<=maximum<=128:
        raise GitSourceError('bounded Git provenance inventory required')
    plane.doctor(maximum=65536)
    with plane.db.snapshot() as conn:
        verify(conn)
        rows=conn.execute('''SELECT r.doc_id,r.revision,r.path,r.commit_sha,r.blob_oid,
            r.raw_sha256,d.normalized_sha256,d.content_type,d.raw_sha256
            FROM ai_kb_git_lineage r JOIN ai_kb_documents d
            ON d.principal=r.principal AND d.doc_id=r.doc_id AND d.revision=r.revision
            WHERE r.principal=? ORDER BY r.doc_id,r.revision LIMIT ?''',
            (plane.identity.key(),maximum+1)).fetchall()
        if len(rows)>maximum:raise GitSourceError('Git provenance inventory exceeds finite review')
    sources={};proved=[]
    for doc_id,revision,path,commit,oid,digest,normalized,kind,recorded in rows:
        if document_for_path(path)!=doc_id or digest!=recorded:
            raise GitSourceError('indexed document is not bound to expected Git path')
        if commit not in sources:
            root=GitSource(repo_root,commit=commit)
            sources[commit]=(root,root.inventory())
        root,inventory=sources[commit]
        blob=root.read(path,inventory,maximum_bytes=plane.policy.max_document_bytes)
        if blob.oid!=oid or blob.sha256!=digest:
            raise GitSourceError('Git object has changed from indexed source proof')
        normalized_actual=sha256(decode_source(blob.raw,kind).encode('utf8')).hexdigest()
        if normalized_actual!=normalized:
            raise GitSourceError('Git object normalized text is not the admitted revision')
        proved.append({'doc_id':doc_id,'revision':revision,'commit_sha':commit,
                       'blob_oid':oid,'raw_sha256':digest})
    from ....orchestration.execution_spine.contracts import canonical
    return {'status':'exact-Git-objects-verified-no-signature','verified':len(proved),
            'inventory_sha256':sha256(canonical(proved)).hexdigest(),
            'remote_fetches':0}
