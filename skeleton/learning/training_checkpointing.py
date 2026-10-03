"""Semantically complete, compatibility-checked training checkpoint manifests."""
from dataclasses import dataclass
import hashlib,json
class CheckpointError(ValueError): pass
@dataclass(frozen=True, slots=True)
class TrainingCheckpoint:
    run_id:str; step:int; dataset_cursor_digest:str; model_digest:str; optimizer_digest:str; rng_digest:str; code_digest:str; config_digest:str; content_digest:str
    def semantic_identity(self):
        return (self.run_id,self.step,self.dataset_cursor_digest,self.model_digest,self.optimizer_digest,self.rng_digest,self.code_digest,self.config_digest)
class CheckpointBuilder:
    @staticmethod
    def build(*,run_id,step,dataset_cursor_digest,model_digest,optimizer_digest,rng_digest,code_digest,config_digest)->TrainingCheckpoint:
        values=(dataset_cursor_digest,model_digest,optimizer_digest,rng_digest,code_digest,config_digest)
        if not run_id or step<0 or any(len(x)!=64 for x in values): raise CheckpointError("invalid checkpoint inputs")
        payload=[run_id,step,*values]; digest=hashlib.sha256(json.dumps(payload,separators=(",",":")).encode()).hexdigest()
        return TrainingCheckpoint(run_id,step,*values,digest)
    @staticmethod
    def verify_restore(checkpoint:TrainingCheckpoint,*,expected_run_id:str,expected_code_digest:str,expected_config_digest:str)->None:
        rebuilt=CheckpointBuilder.build(run_id=checkpoint.run_id,step=checkpoint.step,dataset_cursor_digest=checkpoint.dataset_cursor_digest,model_digest=checkpoint.model_digest,optimizer_digest=checkpoint.optimizer_digest,rng_digest=checkpoint.rng_digest,code_digest=checkpoint.code_digest,config_digest=checkpoint.config_digest)
        if rebuilt.content_digest!=checkpoint.content_digest: raise CheckpointError("checkpoint digest mismatch")
        if checkpoint.run_id!=expected_run_id or checkpoint.code_digest!=expected_code_digest or checkpoint.config_digest!=expected_config_digest: raise CheckpointError("checkpoint compatibility mismatch")
