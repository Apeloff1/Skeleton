from dataclasses import dataclass
@dataclass(frozen=True)
class SDKExport: public_name:str; target:str; since:str; deprecated_in:str|None=None
@dataclass(frozen=True)
class SDKCompatibility:
 version:str; exports:tuple[SDKExport,...]
 def __post_init__(self):
  names=[x.public_name for x in self.exports]
  if not self.version or len(names)!=len(set(names)):raise ValueError("SDK version and unique public names required")
@dataclass(frozen=True)
class InternalSDK:
 compatibility:SDKCompatibility
 def resolve(self,name):
  x=next((e for e in self.compatibility.exports if e.public_name==name),None)
  if not x:raise ImportError("unsupported SDK boundary")
  if name.startswith("_") or "._" in x.target or not x.target.startswith("skeleton.sdk."):raise ImportError("deep/private import forbidden")
  return x.target
