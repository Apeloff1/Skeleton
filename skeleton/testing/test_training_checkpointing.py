import pytest
from skeleton.learning.training_checkpointing import *
def test_semantically_complete_checkpoint_and_restore_compatibility():
 c=CheckpointBuilder.build(run_id="r",step=4,dataset_cursor_digest="a"*64,model_digest="b"*64,optimizer_digest="c"*64,rng_digest="d"*64,code_digest="e"*64,config_digest="f"*64); CheckpointBuilder.verify_restore(c,expected_run_id="r",expected_code_digest="e"*64,expected_config_digest="f"*64)
 with pytest.raises(CheckpointError): CheckpointBuilder.verify_restore(c,expected_run_id="r",expected_code_digest="0"*64,expected_config_digest="f"*64)
