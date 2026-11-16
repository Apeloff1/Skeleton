"""Real ONNX graph execution with synthetic weights; not a semantic benchmark."""
import hashlib
import pytest
from pathlib import Path
from skeleton.retrieval.learned_embeddings import EncoderPolicy,LocalContextEncoder


def build_encoder(root):
    import numpy as np
    import onnx
    from onnx import helper,TensorProto,numpy_helper
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    vocab={"[UNK]":0,"cat":1,"feline":2,"engine":3,"motor":4,"near":5,"other":6}
    tok=Tokenizer(WordLevel(vocab,unk_token="[UNK]"))
    tok.pre_tokenizer=Whitespace()
    token=root/"tokenizer.json"
    tok.save(str(token))
    matrix=np.asarray([[1,1,1],[1,0.1,0.1],[1,0.1,0.1],[0.1,1,0.1],[0.1,1,0.1],[0.1,0.1,1],[0.1,0.1,1]],np.float32)
    # Context-sensitive output: per-token lookup plus surrounding mean.
    graph=helper.make_graph([
        helper.make_node("Gather",["weights","input_ids"],["tokens"],axis=0),
        helper.make_node("ReduceMean",["tokens"],["context"],axes=[1],keepdims=1),
        helper.make_node("Mul",["context","scale"],["shift"]),
        helper.make_node("Add",["tokens","shift"],["last_hidden_state"]),
    ],"synthetic-context",[
        helper.make_tensor_value_info("input_ids",TensorProto.INT64,[1,"length"])
    ],[helper.make_tensor_value_info("last_hidden_state",TensorProto.FLOAT,[1,"length",3])],
      [numpy_helper.from_array(matrix,"weights"),numpy_helper.from_array(np.asarray(0.25,np.float32),"scale")])
    model=helper.make_model(graph,opset_imports=[helper.make_opsetid("",17)],ir_version=9)
    model_path=root/"encoder.onnx"
    model_path.write_bytes(model.SerializeToString())
    pin=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    return LocalContextEncoder(model_path,pin(model_path),token,pin(token),EncoderPolicy(3,max_tokens=64))


def test_real_context_encoder_distinguishes_synonym_and_context(tmp_path):
    encoder=build_encoder(tmp_path)
    import numpy as np
    query=np.asarray(encoder.query("feline").dense)
    cat=encoder.spans("cat",[(0,3)])[0]
    motor=encoder.spans("motor",[(0,5)])[0]
    assert query@cat.dense>query@motor.dense
    contextual=encoder.spans("cat engine engine",[(0,3)])[0]
    assert contextual.dense!=cat.dense
    with pytest.raises(ValueError,match="token limit"):
        encoder.query("cat "*65)
