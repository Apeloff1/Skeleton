from dataclasses import dataclass
@dataclass(frozen=True)
class ProviderAdapterSpec: provider:str; capabilities:tuple[str,...]; contract_version:str
@dataclass(frozen=True)
class ProviderConformance: provider:str; passed:bool; failures:tuple[str,...]
@dataclass(frozen=True)
class ProviderSDK: spec:ProviderAdapterSpec
def _native_leak(x):
 if isinstance(x,dict):return any(str(k).startswith("provider_") or _native_leak(v) for k,v in x.items())
 if isinstance(x,(list,tuple)):return any(_native_leak(v) for v in x)
 return False
def check_provider(spec,adapter):
 failures=[]
 if not spec.provider or not spec.contract_version or not spec.capabilities or len(set(spec.capabilities))!=len(spec.capabilities) or any(not isinstance(x,str) or not x for x in spec.capabilities):failures.append("invalid-spec")
 if failures:return ProviderConformance(spec.provider,False,tuple(sorted(set(failures))))
 try:
  for cap in spec.capabilities:
   if not adapter.supports(cap):failures.append("missing:"+cap)
  sample=adapter.normalize(adapter.probe())
 except Exception:
  return ProviderConformance(spec.provider,False,tuple(sorted(set(failures+["adapter-error"]))))
 if not isinstance(sample,dict) or _native_leak(sample):failures.append("provider-native-leak")
 if isinstance(sample,dict) and sample.get("contract_version")!=spec.contract_version:failures.append("contract-version")
 return ProviderConformance(spec.provider,not failures,tuple(sorted(set(failures))))
