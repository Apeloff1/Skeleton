import pytest
from skeleton.persistence.workspace import *
def test_resources_are_links_not_copies():assert Workspace("w",(),()).link(WorkspaceResource("res1:t:p:v1:x")).resources[0].ref.startswith("res1:")
def test_membership_change_invalidates_active_operation():
 w=Workspace("w",(WorkspaceMember("u",("read",),0),),());assert w.authorize("u","read",0)
 w=w.update_member(WorkspaceMember("u",(),1))
 with pytest.raises(PermissionError):w.authorize("u","read",0)
 with pytest.raises(PermissionError):w.authorize("u","read",w.revision)

def test_stale_member_revision_rejected():
 import pytest
 w=Workspace("w",(),(),2)
 with pytest.raises(ValueError):w.update_member(WorkspaceMember("u",("read",),2))
