from __future__ import annotations
import hashlib,pytest
from skeleton.ai.governance.cards import GovernanceCardError,ToolCard
def d(x): return hashlib.sha256(x.encode()).hexdigest()
def test_tool_card_binds_definition_security_and_scope():
    card=ToolCard("c","git.write","c"*40,d("def"),d("sec"),("repo:write",),"write",True)
    assert card.approval_required is True and len(card.digest)==64
def test_privileged_tool_requires_approval():
    with pytest.raises(GovernanceCardError,match="requires approval"):
        ToolCard("c","admin","c"*40,d("d"),d("s"),("admin",),"privileged",False)
def test_unknown_side_effect_class_rejected():
    with pytest.raises(GovernanceCardError,match="unknown"):
        ToolCard("c","x","c"*40,d("d"),d("s"),("x",),"magic",True)
