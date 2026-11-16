"""Actual image and PCM waveform classifier execution with tiny pinned ONNX graphs."""
from __future__ import annotations

import base64
from hashlib import sha256
from io import BytesIO
import json
import wave

import numpy as np
import onnx
import pytest
from onnx import helper,TensorProto
from PIL import Image

from skeleton.app.jeeves_native_media import LocalMediaRegistry,digest
from skeleton.app.offline_http import OfflineHTTPApplication,OfflineHTTPError
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.cortex.transformer import TinyTransformer


def _model(path,input_shape,output_count,nodes):
    graph=helper.make_graph(nodes,path.stem,
        [helper.make_tensor_value_info("media",TensorProto.FLOAT,input_shape)],
        [helper.make_tensor_value_info("logits",TensorProto.FLOAT,[1,output_count])])
    raw=helper.make_model(graph,opset_imports=[helper.make_opsetid("",17)],ir_version=9).SerializeToString()
    path.write_bytes(raw)
    return sha256(raw).hexdigest()


def registry(tmp_path):
    image=tmp_path/"rgb.onnx"
    audio=tmp_path/"wave.onnx"
    image_pin=_model(image,[1,3,16,16],3,[
        helper.make_node("ReduceMean",["media"],["logits"],axes=[2,3],keepdims=0)])
    audio_pin=_model(audio,[1,256],2,[
        helper.make_node("ReduceMean",["media"],["mean"],axes=[1],keepdims=1),
        helper.make_node("Neg",["mean"],["negative"]),
        helper.make_node("Concat",["mean","negative"],["logits"],axis=1)])
    profiles=[
        {"id":"rgb","modality":"image","model_path":image.name,"model_sha256":image_pin,
         "input_name":"media","output_name":"logits","labels":["red","green","blue"],
         "threads":1,"max_model_bytes":1024**2,
         "geometry":{"height":16,"width":16,"mean":[0,0,0],"std":[1,1,1]}},
        {"id":"wave","modality":"audio","model_path":audio.name,"model_sha256":audio_pin,
         "input_name":"media","output_name":"logits","labels":["positive","negative"],
         "threads":1,"max_model_bytes":1024**2,"geometry":{"sample_rate":8000,"samples":256}}]
    path=tmp_path/"media.json"
    raw=json.dumps({"schema":"skeleton.jeeves.media-config.v1","profiles":profiles}).encode()
    path.write_bytes(raw)
    return LocalMediaRegistry(path,sha256(raw).hexdigest())


def png(color):
    out=BytesIO()
    Image.new("RGB",(24,24),color).save(out,format="PNG")
    return out.getvalue()


def wav(value,*,rate=8000,count=256):
    out=BytesIO()
    with wave.open(out,"wb") as stream:
        stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(rate)
        stream.writeframes(np.full(count,value,dtype="<i2").tobytes())
    return out.getvalue()


def payload(raw,mime):
    return {"media_type":mime,"media_base64":base64.b64encode(raw).decode(),
            "source_sha256":sha256(raw).hexdigest()}


def test_image_classifier_observes_actual_pixels_and_source_identity(tmp_path):
    media=registry(tmp_path)
    red=media.infer("rgb",payload(png((255,0,0)),"image/png"),top_k=3)
    blue=media.infer("rgb",payload(png((0,0,255)),"image/png"),top_k=3)
    assert red["predictions"][0]["label"]=="red"
    assert blue["predictions"][0]["label"]=="blue"
    assert red["decoded_tensor_sha256"]!=blue["decoded_tensor_sha256"]
    assert red["native_classifier_executed"] and not red["scores_calibrated"]
    assert red["media_bytes_persisted"] is False and red["network_called"] is False
    assert red["receipt_sha256"]==digest({k:v for k,v in red.items() if k!="receipt_sha256"})


def test_audio_classifier_observes_actual_pcm_waveform(tmp_path):
    media=registry(tmp_path)
    pos=media.infer("wave",payload(wav(16000),"audio/wav"),top_k=2)
    neg=media.infer("wave",payload(wav(-16000),"audio/wav"),top_k=2)
    assert pos["predictions"][0]["label"]=="positive"
    assert neg["predictions"][0]["label"]=="negative"
    assert pos["metadata"]["original_samples"]==256
    assert pos["tensor_shape"]==[1,256]
    padded=media.infer("wave",payload(wav(16000,count=128),"audio/wav"),top_k=2)
    assert padded["metadata"]["padded_samples"]==128
    with pytest.raises(ValueError):
        media.infer("wave",payload(wav(1,rate=16000),"audio/wav"),top_k=2)
    with pytest.raises(ValueError):
        media.infer("wave",payload(wav(1,count=300),"audio/wav"),top_k=2)


def test_media_rejects_invalid_source_and_mutated_model(tmp_path):
    media=registry(tmp_path)
    data=payload(png((255,0,0)),"image/png")
    with pytest.raises(ValueError):
        media.infer("rgb",data|{"source_sha256":"0"*64},top_k=2)
    with pytest.raises(ValueError):
        media.infer("wave",data,top_k=2)
    path=tmp_path/"rgb.onnx"
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises((ValueError,OSError)):
        media.infer("rgb",data,top_k=2)


def test_authenticated_media_route_uses_classifier_without_transcript_write(tmp_path):
    media=registry(tmp_path)
    model=NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("system:","user:","assistant:","hello","world","answer","local","."," "),
        dim=8,ctx=256,seed=41,n_heads=2,n_layers=2,d_ff=16)))
    app=OfflineHTTPApplication(model,tmp_path/"chat.sqlite3",token="t"*64,media_registry=media)
    try:
        sid=app.dispatch("POST","/v1/sessions",{})[1]["session_id"]
        route="/v1/sessions/"+sid
        before=app.dispatch("GET",route)[1]
        args={"expected_revision":0,"profile":"rgb","approved":True,"top_k":2,
              **payload(png((0,255,0)),"image/png")}
        result=app.dispatch("POST",route+"/media-review",args)[1]
        assert result["predictions"][0]["label"]=="green"
        assert app.dispatch("GET",route)[1]==before
        assert app.knowledge.list_documents()==[]
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST",route+"/media-review",args|{"approved":False})
        assert exc.value.status==403
    finally:
        app.close()
