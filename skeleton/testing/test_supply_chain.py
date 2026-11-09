import pytest
from skeleton.ai.runtime.deferred.supply_chain import *
D="a"*64; B="b"*64
def test_hermetic_identity_binds_toolchain_and_inputs():
 a=HermeticBuild(D,D,(BuildInput("dep",D,"vendor"),),HermeticPolicy(False,()))
 b=HermeticBuild(D,B,a.inputs,a.policy); assert a.identity!=b.identity
def test_network_build_must_declare_vendored_or_cached_inputs():
 with pytest.raises(ValueError): HermeticBuild(D,D,(),HermeticPolicy(True,()))
def test_shared_cache_rejects_sensitive_or_tenant_data():
 with pytest.raises(ValueError): CachePolicy(True,True,None)
 with pytest.raises(ValueError): CachePolicy(True,False,"tenant")
def test_cache_key_binds_config_and_dependencies():
 a=BuildCacheKey(D,D,D,D); b=BuildCacheKey(D,D,B,D); assert a.key!=b.key
def test_binary_attestation_rejects_signature_for_other_artifact():
 with pytest.raises(ValueError): BinaryAttestation(D,BuildIdentity(D,D,D),ArtifactSignature(B,"signer",D))
def test_attestation_requires_trusted_signer():
 a=BinaryAttestation(D,BuildIdentity(D,D,D),ArtifactSignature(D,"signer",B))
 assert not verify_attestation(a,("other",)) and verify_attestation(a,("signer",))
def test_installer_rejects_traversal_absolute_and_symlink_paths():
 for p in ("../evil","a/../../evil","/absolute"):
  with pytest.raises(ValueError): InstallPath("/safe",p)
 with pytest.raises(ValueError): InstallPath("/safe","ok",True)
def test_privileged_install_requires_signature_and_path_verification():
 assert not InstallVerification(D,True,False).privileged_write_allowed
 assert InstallVerification(D,True,True).privileged_write_allowed
def test_update_signature_binds_metadata():
 with pytest.raises(ValueError): UpdateMetadata(2,D,D,UpdateSignature(B,"s"))
def test_update_blocks_downgrade_unless_explicitly_authorized():
 sig=UpdateSignature(D,"s")
 assert not admit_update(UpdateMetadata(1,D,D,sig),VersionFloor(2),("s",))
 assert admit_update(UpdateMetadata(1,D,D,sig,True),VersionFloor(2),("s",))
def test_update_rejects_untrusted_signer_even_for_newer_version():
 assert not admit_update(UpdateMetadata(3,D,D,UpdateSignature(D,"evil")),VersionFloor(2),("trusted",))


def test_supply_chain_depth_invariants_fail_closed():
 import pytest
 d="a"*64
 bi=BuildInput("x",d,"src")
 with pytest.raises(ValueError):HermeticBuild(d,d,(bi,bi),HermeticPolicy(False,()))
 with pytest.raises(ValueError):HermeticBuild(d,d,(BuildInput("x","bad","src"),),HermeticPolicy(False,()))
 sig=ArtifactSignature(d,"signer",d)
 with pytest.raises(ValueError):BinaryAttestation(d,BuildIdentity("bad",d,d),sig)
 a=BinaryAttestation(d,BuildIdentity(d,d,d),sig);assert not verify_attestation(a,("signer","signer"))
 with pytest.raises(ValueError):InstallPath("","x")
 with pytest.raises(ValueError):VersionFloor(-1)
 with pytest.raises(ValueError):UpdateMetadata(-1,d,d,UpdateSignature(d,"s"))
 m=UpdateMetadata(1,d,d,UpdateSignature(d,"s"));assert not admit_update(m,VersionFloor(0),("s","s"))
