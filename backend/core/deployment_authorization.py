"""Single-use deployment authorizations bound to a stable preflight and plan digest.

Preflight proves a deploy was safe at one state root; authorization prevents that
proof from being replayed after state or plan mutation. Issue/consume events form an
append-only hash chain under a cross-process lease. Consumption is exactly-once.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
from datetime import UTC,datetime,timedelta
import hashlib,hmac,json,os,uuid
from pathlib import Path
from typing import Any
from core.control_plane_deployment import ControlPlaneDeploymentPreflight,verify_control_plane_deployment_preflight
from core.file_lease import FileLease
AUTH_VERSION=1
class DeploymentAuthorizationError(RuntimeError):pass
@dataclass(frozen=True,slots=True)
class DeploymentAuthorization:
    id:str; system_root_sha256:str; preflight_sha256:str; plan_sha256:str; issued_at:str; expires_at:str; issue_event_sha256:str
@dataclass(frozen=True,slots=True)
class DeploymentConsumption:
    authorization_id:str; consumed_at:str; system_root_sha256:str; plan_sha256:str; consume_event_sha256:str
def _canonical(v:Any)->bytes:return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode()
def _sha(v:Any)->str:return hashlib.sha256(_canonical(v)).hexdigest()
def plan_digest(plan:dict[str,Any])->str:
    if not isinstance(plan,dict) or not plan:raise ValueError("deployment plan must be a non-empty object")
    return _sha(plan)
def _parse(v:str)->datetime:
    d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if d.tzinfo is None:raise ValueError("authorization timestamps must be timezone-aware")
    return d.astimezone(UTC)
class DeploymentAuthorizationLedger:
    def __init__(self,root:str|Path)->None:
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.path=self.root/"deployment-authorizations.jsonl";self._lease=FileLease(self.root/".deployment-authorizations.lock")
        with self._lease.acquire():
            if not self.path.exists():self.path.touch()
            self._load_verified()
    def _load_verified(self)->list[dict[str,Any]]:
        try:lines=self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:raise DeploymentAuthorizationError("authorization ledger unreadable") from exc
        rows=[];previous=""
        for seq,line in enumerate(lines,start=1):
            if not line.strip():continue
            try:row=json.loads(line)
            except json.JSONDecodeError as exc:raise DeploymentAuthorizationError("authorization ledger malformed") from exc
            if row.get("version")!=AUTH_VERSION or int(row.get("sequence",0))!=seq or row.get("previous_sha256","")!=previous:raise DeploymentAuthorizationError("authorization ledger ancestry/version mismatch")
            claimed=str(row.get("sha256",""));payload={k:v for k,v in row.items() if k!="sha256"}
            if not hmac.compare_digest(_sha(payload),claimed):raise DeploymentAuthorizationError("authorization event hash mismatch")
            if row.get("kind") not in {"issue","consume"}:raise DeploymentAuthorizationError("unknown authorization event")
            previous=claimed;rows.append(row)
        return rows
    def _append(self,payload:dict[str,Any],rows:list[dict[str,Any]])->dict[str,Any]:
        event={"version":AUTH_VERSION,"sequence":len(rows)+1,**payload,"previous_sha256":rows[-1]["sha256"] if rows else ""};event["sha256"]=_sha(event)
        with self.path.open("a",encoding="utf-8") as h:h.write(json.dumps(event,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n");h.flush();os.fsync(h.fileno())
        return event
    def issue(self,*,preflight:ControlPlaneDeploymentPreflight,plan:dict[str,Any],ttl_seconds:int=300,issued_at:str|None=None)->DeploymentAuthorization:
        if not verify_control_plane_deployment_preflight(preflight) or not preflight.allowed or not preflight.stable:raise DeploymentAuthorizationError("deployment preflight is not authorizing/stable")
        if ttl_seconds<1 or ttl_seconds>3600:raise ValueError("authorization ttl must be between 1 and 3600 seconds")
        stamp=issued_at or datetime.now(UTC).isoformat();issued=_parse(stamp);expires=(issued+timedelta(seconds=ttl_seconds)).isoformat();pid=plan_digest(plan);auth_id=uuid.uuid4().hex
        with self._lease.acquire():
            rows=self._load_verified();event=self._append({"kind":"issue","authorization_id":auth_id,"system_root_sha256":preflight.root_after_sha256,"preflight_sha256":preflight.attestation_sha256,"plan_sha256":pid,"issued_at":stamp,"expires_at":expires},rows)
        return DeploymentAuthorization(auth_id,preflight.root_after_sha256,preflight.attestation_sha256,pid,stamp,expires,event["sha256"])
    def _state(self,authorization_id:str,rows:list[dict[str,Any]])->tuple[dict[str,Any]|None,dict[str,Any]|None]:
        issue=next((x for x in rows if x.get("kind")=="issue" and x.get("authorization_id")==authorization_id),None);consume=next((x for x in rows if x.get("kind")=="consume" and x.get("authorization_id")==authorization_id),None);return issue,consume
    def consume(self,authorization_id:str,*,current_system_root_sha256:str,plan:dict[str,Any],consumed_at:str|None=None)->DeploymentConsumption:
        stamp=consumed_at or datetime.now(UTC).isoformat();now=_parse(stamp);pid=plan_digest(plan)
        with self._lease.acquire():
            rows=self._load_verified();issue,prior=self._state(authorization_id,rows)
            if issue is None:raise DeploymentAuthorizationError("authorization not found")
            if prior is not None:raise DeploymentAuthorizationError("authorization already consumed")
            if now>_parse(str(issue["expires_at"])):raise DeploymentAuthorizationError("authorization expired")
            if not hmac.compare_digest(str(issue["system_root_sha256"]),str(current_system_root_sha256)):raise DeploymentAuthorizationError("system root changed after preflight")
            if not hmac.compare_digest(str(issue["plan_sha256"]),pid):raise DeploymentAuthorizationError("deployment plan changed after authorization")
            event=self._append({"kind":"consume","authorization_id":authorization_id,"system_root_sha256":current_system_root_sha256,"plan_sha256":pid,"consumed_at":stamp,"issue_event_sha256":issue["sha256"]},rows)
        return DeploymentConsumption(authorization_id,stamp,current_system_root_sha256,pid,event["sha256"])
    def status(self)->dict[str,Any]:
        with self._lease.acquire():rows=self._load_verified()
        issues=[x for x in rows if x.get("kind")=="issue"];consumed={x.get("authorization_id") for x in rows if x.get("kind")=="consume"}
        return {"version":AUTH_VERSION,"issued":len(issues),"consumed":len(consumed),"outstanding":sum(x.get("authorization_id") not in consumed for x in issues),"head_sha256":rows[-1]["sha256"] if rows else "","cross_process_locking":True,"lock_backend":self._lease.backend,"verified":True}
