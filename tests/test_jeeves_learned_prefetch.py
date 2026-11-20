"""Real local cross-encoder prediction ranking and observed cache utility."""
from hashlib import sha256
import json

import numpy as np
import onnx
from onnx import TensorProto,helper,numpy_helper
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace
from tokenizers.processors import TemplateProcessing

from skeleton.app.jeeves_learned_prefetch import load_predictor,learned_rank
from skeleton.app.jeeves_prefetch import rank_questions
from skeleton.app.offline_http import OfflineHTTPApplication
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.cortex.transformer import TinyTransformer


def predictor(tmp_path):
    vocab={"[UNK]":0,"[SEP]":1,"harbor":2,"signal":3,"violet":4,"weather":5}
    tokenizer=Tokenizer(WordLevel(vocab,unk_token="[UNK]"))
    tokenizer.pre_tokenizer=Whitespace()
    tokenizer.post_processor=TemplateProcessing(single="$A [SEP]",pair="$A [SEP] $B:1 [SEP]:1",
                                                special_tokens=[("[SEP]",1)])
    tok=tmp_path/"tokenizer.json";tokenizer.save(str(tok))
    # Independent token weights emphasize violet over lexical overlap.
    # Synthetic qualification weights, not a pretrained next-query model.
    weights=np.asarray([0,0,0,0,10,-10],np.float32)
    graph=helper.make_graph([
        helper.make_node("Gather",["weights","input_ids"],["values"]),
        helper.make_node("ReduceSum",["values","axis"],["logits"],keepdims=1)
    ],"predictor",[helper.make_tensor_value_info("input_ids",TensorProto.INT64,[1,"length"])],
      [helper.make_tensor_value_info("logits",TensorProto.FLOAT,[1,1])],
      [numpy_helper.from_array(weights,name="weights"),numpy_helper.from_array(np.array([1],np.int64),name="axis")])
    model=tmp_path/"predictor.onnx";model.write_bytes(helper.make_model(graph,
        opset_imports=[helper.make_opsetid("",17)],ir_version=9).SerializeToString())
    cfg=tmp_path/"forecast.json"
    cfg.write_text(json.dumps({"schema":"skeleton.jeeves.next-query-config.v1",
      "tokenizer_path":tok.name,"tokenizer_sha256":sha256(tok.read_bytes()).hexdigest(),
      "model_path":model.name,"model_sha256":sha256(model.read_bytes()).hexdigest(),
      "policy":{"max_pairs":12,"threads":1}}))
    return load_predictor(cfg,sha256(cfg.read_bytes()).hexdigest())


def test_learned_selection_differs_from_lexical_and_warms_actual_grounded_turn(tmp_path):
    model=NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("system:","user:","assistant:","harbor","signal","violet","weather","hello","answer","."," "),
        dim=8,ctx=512,seed=41,n_heads=2,n_layers=2,d_ff=16)))
    ranker=predictor(tmp_path)
    app=OfflineHTTPApplication(model,tmp_path/"chat.sqlite3",token="t"*64,prefetch_predictor=ranker)
    try:
        sid=app.dispatch("POST","/v1/sessions",{})[1]["session_id"]
        route="/v1/sessions/"+sid
        app.dispatch("POST",route+"/turn",{"message":"harbor signal","request_id":"prior","max_output_tokens":2})
        messages=app._session(sid).transcript.to_list()
        queries=["harbor signal","violet","weather"]
        assert rank_questions(messages,queries)[0][2]=="harbor signal"
        ranked,receipt=learned_rank(messages,queries,ranker)
        assert ranked[0][2]=="violet"
        assert receipt["learned_inference_performed"] is True
        doc=app.knowledge.add_text("reference","The harbor signal is violet.")
        before=app.dispatch("GET",route)[1]
        result=app.dispatch("POST",route+"/predictive-prefetch",{
            "expected_revision":1,"candidates":queries,"document_ids":[doc["document_id"]],
            "maximum_queries":1,"learned":True,"approved":True})[1]
        assert result["learned_forecast"]["predictor_identity"]==ranker.identity
        assert result["warmed"][0]["query_sha256"]==sha256(b"violet").hexdigest()
        assert app.dispatch("GET",route)[1]==before
        app.dispatch("POST",route+"/turn",{"message":"violet","request_id":"warm",
            "max_output_tokens":4,"grounded":True,"document_ids":[doc["document_id"]]})
        stats=app.competitive.prefetch.stats()
        assert stats["verified_consumptions"]==1 and stats["warmups"]==1
        assert stats["predictions_certified"] is False
    finally:
        app.close()
