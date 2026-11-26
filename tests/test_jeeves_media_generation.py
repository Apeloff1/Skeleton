"""Real conditional ONNX encoder/decoder qualification (synthetic weights)."""
import base64
from hashlib import sha256
from io import BytesIO
import json
import wave

import numpy as np
import pytest
import onnx
from onnx import TensorProto,helper,numpy_helper
from PIL import Image
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

from skeleton.app.jeeves_media_generation import GenerationMediaRegistry,logmel
from skeleton.app.offline_http import OfflineHTTPApplication,OfflineHTTPError
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.cortex.transformer import TinyTransformer


def pin(path):
    raw=path.read_bytes()
    return {"path":path.name,"sha256":sha256(raw).hexdigest(),"max_bytes":len(raw)}


def graph(path,nodes,inputs,outputs,initializers=()):
    g=helper.make_graph(nodes,path.stem,inputs,outputs,list(initializers))
    path.write_bytes(helper.make_model(g,opset_imports=[helper.make_opsetid("",17)],
                                       ir_version=9).SerializeToString())
    return pin(path)


def fixtures(tmp_path):
    token=Tokenizer(WordLevel({"[UNK]":0,"begin":1,"red":2,"blue":3,
                               "end":4,"question":5},unk_token="[UNK]"))
    token.pre_tokenizer=Whitespace()
    token_path=tmp_path/"tokenizer.json";token.save(str(token_path))
    profiles=[]
    for mode in ("image","audio"):
        image=mode=="image"
        shape=[1,3,16,16] if image else [1,256]
        nodes=([helper.make_node("ReduceMean",["features"],["pooled"],axes=[2,3],keepdims=0),
                helper.make_node("Unsqueeze",["pooled","axis"],["hidden"])] if image else
               [helper.make_node("ReduceMean",["features"],["mean"],axes=[1],keepdims=1),
                helper.make_node("Neg",["mean"],["negative"]),
                helper.make_node("Sub",["mean","mean"],["zero"]),
                helper.make_node("Concat",["mean","zero","negative"],["pooled"],axis=1),
                helper.make_node("Unsqueeze",["pooled","axis"],["hidden"])])
        enc=graph(tmp_path/(mode+"-encoder.onnx"),nodes,
                  [helper.make_tensor_value_info("features",TensorProto.FLOAT,shape)],
                  [helper.make_tensor_value_info("hidden",TensorProto.FLOAT,[1,1,3])],
                  [numpy_helper.from_array(np.array([1],np.int64),name="axis")])
        # At the initial prefix, choose red/blue according to actual context.
        # On subsequent decoder calls, choose EOS. IDs affect the branch.
        matrix=np.array([[0,0,10,0,0,0],[0,0,0,0,0,0],[0,0,0,10,0,0]],np.float32)
        initializers=[numpy_helper.from_array(matrix,name="matrix"),
            numpy_helper.from_array(np.array([1],np.int64),name="axis"),
            numpy_helper.from_array(np.array(1,np.int64),name="index"),
            numpy_helper.from_array(np.array(2,np.int64),name="initial_length"),
            numpy_helper.from_array(np.array([[0,0,0,0,100,0]],np.float32),name="end_logits")]
        decoder=graph(tmp_path/(mode+"-decoder.onnx"),[
            helper.make_node("Squeeze",["context","axis"],["vector"]),
            helper.make_node("MatMul",["vector","matrix"],["media_logits"]),
            helper.make_node("Shape",["ids"],["shape"]),
            helper.make_node("Gather",["shape","index"],["length"],axis=0),
            helper.make_node("Less",["length","initial_length"],["initial"]),
            helper.make_node("Where",["initial","media_logits","end_logits"],["logits"])
        ],[helper.make_tensor_value_info("ids",TensorProto.INT64,[1,"length"]),
           helper.make_tensor_value_info("context",TensorProto.FLOAT,[1,1,3])],
          [helper.make_tensor_value_info("logits",TensorProto.FLOAT,[1,6])],initializers)
        geometry=({"width":16,"height":16,"mean":[0,0,0],"std":[1,1,1]} if image else
                  {"kind":"waveform","sample_rate":8000,"samples":256})
        profiles.append({"id":mode,"modality":mode,"encoder":enc,"decoder":decoder,
            "tokenizer":pin(token_path),"geometry":geometry,"encoder_input":"features",
            "encoder_output":"hidden","decoder_ids":"ids","decoder_context":"context",
            "decoder_output":"logits","decoder_mask":None,"prefix_ids":[1],"eos_ids":[4],
            "max_context":16,"max_output":8,"threads":1})
    cfg=tmp_path/"generation.json"
    cfg.write_text(json.dumps({"schema":"skeleton.jeeves.media-generation-config.v1","profiles":profiles}))
    return GenerationMediaRegistry(cfg,sha256(cfg.read_bytes()).hexdigest())


def image(color):
    stream=BytesIO();Image.new("RGB",(24,24),color).save(stream,format="PNG")
    return stream.getvalue()


def audio(value):
    stream=BytesIO()
    with wave.open(stream,"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000)
        f.writeframes(np.full(256,value,dtype="<i2").tobytes())
    return stream.getvalue()


def media(raw,mime):
    return {"media_type":mime,"media_base64":base64.b64encode(raw).decode(),
            "source_sha256":sha256(raw).hexdigest()}


def test_real_vision_and_speech_decoder_tokens_depend_on_media(tmp_path):
    reg=fixtures(tmp_path)
    for mode,positive,negative,mime in [
        ("image",image((255,0,0)),image((0,0,255)),"image/png"),
        ("audio",audio(20000),audio(-20000),"audio/wav")]:
        a=reg.generate(mode,media(positive,mime),max_output=4)
        b=reg.generate(mode,media(negative,mime),max_output=4)
        assert a["generated_ids"]==[2,4] and b["generated_ids"]==[3,4]
        assert a["text"]=="red" and b["text"]=="blue"
        assert a["encoder_context_sha256"]!=b["encoder_context_sha256"]
        assert a["encoder_calls"]==1 and a["decoder_calls"]==2
        assert a["native_generation_performed"] and not a["semantic_accuracy_certified"]
        assert not a["media_bytes_persisted"]


def test_logmel_frontend_is_finite_and_signal_dependent():
    t=np.arange(512,dtype=np.float32)
    first=np.sin(2*np.pi*t/8)[None,:].astype(np.float32)
    second=np.sin(2*np.pi*t/32)[None,:].astype(np.float32)
    filters=np.full((16,65),.001,dtype=np.float32)
    filters[:8,2:8]=1
    filters[8:,12:20]=1
    geo={"n_fft":128,"hop":64,"mel_bins":16}
    a=logmel(first,geo,filters);b=logmel(second,geo,filters)
    assert a.shape==b.shape==(1,16,8)
    assert np.isfinite(a).all() and not np.allclose(a,b)


def test_conditional_http_guard_and_media_pin(tmp_path):
    reg=fixtures(tmp_path)
    runtime=NativeLLMRuntime(TinyTransformer(vocab=("system:","user:","assistant:",
        "hello","world","answer","local","."," "),dim=8,ctx=256,seed=41,n_heads=2,n_layers=2,d_ff=16))
    app=OfflineHTTPApplication(NativeRuntimeLocalModel(runtime),tmp_path/"chat.sqlite3",
                               token="t"*64,media_generator=reg)
    try:
        sid=app.dispatch("POST","/v1/sessions",{})[1]["session_id"];route="/v1/sessions/"+sid
        before=app.dispatch("GET",route)[1]
        body={"expected_revision":0,"profile":"image","max_output_tokens":4,"approved":True,
              **media(image((255,0,0)),"image/png")}
        result=app.dispatch("POST",route+"/media-generate",body)[1]
        assert result["text"]=="red" and result["transcript_committed"] is False
        assert app.dispatch("GET",route)[1]==before
        assert app.knowledge.list_documents()==[]
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST",route+"/media-generate",body|{"approved":False})
        assert exc.value.status==403
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST",route+"/media-generate",body|{"source_sha256":"0"*64})
        assert exc.value.status==422
        with pytest.raises(ValueError):
            reg.generate("audio",media(audio(1),"audio/wav"),question="unapproved instruction")
        path=tmp_path/"image-decoder.onnx"
        path.write_bytes(path.read_bytes()+b"x")
        with pytest.raises(ValueError):
            reg.generate("image",media(image((255,0,0)),"image/png"),max_output=4)
    finally:
        app.close()
