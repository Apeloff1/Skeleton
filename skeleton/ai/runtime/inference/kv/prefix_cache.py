from dataclasses import dataclass
@dataclass(frozen=True)
class PrefixCacheKey: instruction_digest:str; prompt_digest:str; model:str; tokenizer:str; version:str; scope:str
@dataclass(frozen=True)
class PrefixArtifact: key:PrefixCacheKey; sensitive:bool
@dataclass(frozen=True)
class PrefixReuseDecision: reusable:bool; reason:str
def can_reuse(a,key,authorized_scopes):
 if any(not x for x in (key.instruction_digest,key.prompt_digest,key.model,key.tokenizer,key.version,key.scope)):return PrefixReuseDecision(False,"incomplete cache identity")
 if a.key!=key:return PrefixReuseDecision(False,"identity mismatch")
 if key.scope not in authorized_scopes:return PrefixReuseDecision(False,"scope denied")
 return PrefixReuseDecision(True,"exact identity and scope")
