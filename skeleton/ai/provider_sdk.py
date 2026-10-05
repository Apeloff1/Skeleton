from dataclasses import dataclass
@dataclass(frozen=True)
class ProviderAdapterSpec: provider:str; capabilities:tuple[str,...]; contract_version:str
@dataclass(frozen=True)
class ProviderConformance: provider:str; passed:bool; failures:tuple[str,...]
@dataclass(frozen=True)
class ProviderSDK: spec:ProviderAdapterSpec
def check_provider(spec,adapter):
 failures=[]
 for cap in spec.capabilities:
  if not adapter.supports(cap):failures.append("missing:"+cap)
 sample=adapter.normalize(adapter.probe())
 if not isinstance(sample,dict) or any(k.startswith("provider_") for k in sample):failures.append("provider-native-leak")
 if sample.get("contract_version")!=spec.contract_version:failures.append("contract-version")
 return ProviderConformance(spec.provider,not failures,tuple(sorted(failures)))
