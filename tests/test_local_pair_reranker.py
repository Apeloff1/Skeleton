import hashlib
import numpy as np
try:
    import onnx
except ImportError:
    onnx = None
try:
    from onnx import helper,TensorProto,numpy_helper
except ImportError:
    helper = TensorProto = numpy_helper = None
try:
    from tokenizers import Tokenizer
except ImportError:
    Tokenizer = None
try:
    from tokenizers.models import WordLevel
except ImportError:
    WordLevel = None
try:
    from tokenizers.pre_tokenizers import Whitespace
except ImportError:
    Whitespace = None
from tokenizers.processors import TemplateProcessing
from skeleton.retrieval.learned_embeddings import LocalPairReranker,PairRerankerPolicy


def test_local_cross_encoder_executes_joint_query_passage_graph(tmp_path):
    vocab={"[UNK]":0,"[SEP]":1,"cat":2,"feline":3,"motor":4}
    tokenizer=Tokenizer(WordLevel(vocab,unk_token="[UNK]"))
    tokenizer.pre_tokenizer=Whitespace()
    tokenizer.post_processor=TemplateProcessing(single="$A [SEP]",pair="$A [SEP] $B:1 [SEP]:1",special_tokens=[("[SEP]",1)])
    path=tmp_path/"tokenizer.json"
    tokenizer.save(str(path))
    weights=np.asarray([[0],[0],[1],[1],[-1]],np.float32)
    graph=helper.make_graph([
        helper.make_node("Gather",["weights","input_ids"],["hidden"],axis=0),
        helper.make_node("ReduceSum",["hidden","axis"],["logits"],keepdims=0)
    ],"synthetic-pair-classifier",[helper.make_tensor_value_info("input_ids",TensorProto.INT64,[1,"length"])],
        [helper.make_tensor_value_info("logits",TensorProto.FLOAT,[1,1])],
        [numpy_helper.from_array(weights,"weights"),numpy_helper.from_array(np.asarray([1],np.int64),"axis")])
    model=tmp_path/"pair.onnx"
    model.write_bytes(helper.make_model(graph,opset_imports=[helper.make_opsetid("",17)],ir_version=9).SerializeToString())
    pin=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    reranker=LocalPairReranker(model,pin(model),path,pin(path),PairRerankerPolicy())
    scores=reranker.score("feline",["cat","motor"])
    assert len(scores)==2 and scores[0]>scores[1]
