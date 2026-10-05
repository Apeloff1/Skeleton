from __future__ import annotations
import hashlib
from skeleton.security.zero_trust import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
I=WorkloadIdentity("WORKLOAD.API","INSTANCE.1",S("attest"));G=InternalGrant("GRANT.1","WORKLOAD.API","INSTANCE.1",frozenset({"read"}),"tenant/a/",0,100)
def test_exact_workload_identity_and_least_privilege_grant():assert authorize(I,G,"read","tenant/a/item",10).allowed
def test_instance_identity_cannot_be_replayed():assert not authorize(WorkloadIdentity("WORKLOAD.API","INSTANCE.2",S("attest2")),G,"read","tenant/a/item",10).allowed
def test_action_and_resource_scope_fail_closed():assert not authorize(I,G,"write","tenant/a/item",10).allowed and not authorize(I,G,"read","tenant/b/item",10).allowed
def test_long_running_authority_has_revalidation_deadline():assert authorize(I,G,"read","tenant/a/item",10,revalidation_interval=7).revalidate_at==17
def test_expired_grant_denied():assert not authorize(I,G,"read","tenant/a/item",100).allowed
