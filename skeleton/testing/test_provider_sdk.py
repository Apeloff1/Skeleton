from skeleton.ai.provider_sdk import *
class A:
 def __init__(self,leak=False):self.leak=leak
 def supports(self,c):return c=="chat"
 def probe(self):return object()
 def normalize(self,x):return {"contract_version":"v1",**({"provider_native":"x"} if self.leak else {})}
def test_conforming_adapter_passes_shared_contract():assert check_provider(ProviderAdapterSpec("p",("chat",),"v1"),A()).passed
def test_missing_capability_and_native_leak_fail(): 
 r=check_provider(ProviderAdapterSpec("p",("chat","embed"),"v1"),A(True));assert not r.passed and "missing:embed" in r.failures and "provider-native-leak" in r.failures

def test_nested_provider_native_leak_fails():
 class A:
  def supports(self,c):return True
  def probe(self):return {}
  def normalize(self,x):return {"contract_version":"v1","nested":{"provider_raw":"x"}}
 assert not check_provider(ProviderAdapterSpec("p",("x",),"v1"),A()).passed
def test_adapter_exception_becomes_conformance_failure():
 class A:
  def supports(self,c):raise RuntimeError()
 assert "adapter-error" in check_provider(ProviderAdapterSpec("p",("x",),"v1"),A()).failures

def test_invalid_spec_does_not_call_adapter():
 class A:
  def supports(self,x):raise AssertionError("must not call")
 assert not check_provider(ProviderAdapterSpec("p",("","x"),"v"),A()).passed
