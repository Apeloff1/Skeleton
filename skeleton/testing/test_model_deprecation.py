from skeleton.ai.providers.model_deprecation import *
def test_consumer_inventory_blocks_early_retirement():assert not retire(ModelDeprecation("m","n",10,(ModelConsumer("c",False),)),11).retired
def test_explicit_exception_allows_retirement_after_deadline():assert retire(ModelDeprecation("m","n",10,(ModelConsumer("c",False,"approved"),)),11).retired

def test_duplicate_consumer_inventory_blocks_retirement():
 c=ModelConsumer("c",True);d=ModelDeprecation("m","n",0,(c,c));assert not retire(d,1).retired
