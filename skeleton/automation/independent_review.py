"""Independent review routing for repository workspace proposals."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import hmac, json
from typing import Iterable
from .transactional_workspace import WorkspaceReceipt, WorkspaceError

MAX_FINDINGS=256
MAX_ID_BYTES=256
_DECISIONS=frozenset({"approve","reject"})

def _id(v:str)->str:
    if not isinstance(v,str) or not v or len(v.encode())>MAX_ID_BYTES: raise WorkspaceError("invalid identity")
    return v

def _hex(v:str)->str:
    if not isinstance(v,str) or len(v)!=64 or v.lower()!=v:
        raise WorkspaceError("invalid digest")
    try: bytes.fromhex(v)
    except ValueError as e: raise WorkspaceError("invalid digest") from e
    return v

def _digest(v:object)->str:
    return sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

@dataclass(frozen=True)
class ReviewFinding:
    code:str
    evidence_digest:str
    blocking:bool
    def __post_init__(self):
        _id(self.code); _hex(self.evidence_digest)
        if not isinstance(self.blocking,bool): raise WorkspaceError("blocking must be bool")

@dataclass(frozen=True)
class ReviewReceipt:
    workspace_result_digest:str
    workspace_operation_digest:str
    proposer_id:str
    reviewer_id:str
    decision:str
    findings:tuple[ReviewFinding,...]
    authority_scope:str="review-evidence-only"
    def __post_init__(self):
        _hex(self.workspace_result_digest); _hex(self.workspace_operation_digest)
        _id(self.proposer_id); _id(self.reviewer_id)
        if hmac.compare_digest(self.proposer_id,self.reviewer_id): raise WorkspaceError("reviewer must be independent")
        if self.decision not in _DECISIONS: raise WorkspaceError("invalid decision")
        if not isinstance(self.findings,tuple) or len(self.findings)>MAX_FINDINGS: raise WorkspaceError("finding budget exceeded")
        if any(not isinstance(x,ReviewFinding) for x in self.findings): raise WorkspaceError("invalid finding")
        if self.decision=="approve" and any(x.blocking for x in self.findings): raise WorkspaceError("approval cannot contain blocking findings")
        if self.authority_scope!="review-evidence-only": raise WorkspaceError("review cannot grant execution authority")
    @property
    def review_digest(self)->str:
        return _digest({"workspace_result_digest":self.workspace_result_digest,"workspace_operation_digest":self.workspace_operation_digest,"proposer_id":self.proposer_id,"reviewer_id":self.reviewer_id,"decision":self.decision,"findings":[{"code":x.code,"evidence_digest":x.evidence_digest,"blocking":x.blocking} for x in self.findings],"authority_scope":self.authority_scope})

def review_workspace(receipt:WorkspaceReceipt,*,proposer_id:str,reviewer_id:str,decision:str,findings:Iterable[ReviewFinding]=())->ReviewReceipt:
    if not isinstance(receipt,WorkspaceReceipt): raise WorkspaceError("typed workspace receipt required")
    if receipt.authority_scope!="workspace-proposal-only": raise WorkspaceError("invalid workspace authority")
    fs=tuple(findings)
    return ReviewReceipt(receipt.result_digest,receipt.operation_digest,proposer_id,reviewer_id,decision,fs)

def verify_review(workspace:WorkspaceReceipt,review:ReviewReceipt)->bool:
    if not isinstance(workspace,WorkspaceReceipt) or not isinstance(review,ReviewReceipt): return False
    if review.decision != "approve" or any(finding.blocking for finding in review.findings): return False
    return hmac.compare_digest(workspace.result_digest,review.workspace_result_digest) and hmac.compare_digest(workspace.operation_digest,review.workspace_operation_digest)
