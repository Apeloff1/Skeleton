"""Local conditional vision-language generation and speech transcription.

Pinned encoder/decoder/tokenizer bundles execute actual ONNX graphs. The
encoder sees real RGB pixels or WAV features; every next token is generated
by a decoder attending to the encoder's hidden states. No raw media is saved,
no model is downloaded, and no caption/transcript template substitutes for
inference. Only explicitly compatible exported model geometries are admitted.
"""
from __future__ import annotations

import base64
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import re
import threading
import time

from skeleton.app.jeeves_native_media import decode_image,decode_wave,_normalization,digest
from skeleton.app.jeeves_media_advisory import verify_transient_media
from skeleton.retrieval.learned_embeddings import _read_pinned,_validate_graph

MAX_GRAPH_BYTES=768*1024**2
MAX_TOTAL_GRAPH_BYTES=1024**3
MAX_CONTEXT=1024
MAX_GENERATED=256
MAX_FEATURE_CELLS=2_000_000
MAX_VOCAB=150_000
_PIN=re.compile(r"[0-9a-f]{64}\Z")
_ID=re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_MIME={"image/png":"image-caption","image/jpeg":"image-caption","image/webp":"image-caption",
       "audio/wav":"audio-transcript"}


def _require_int(v,lo,hi):
    if type(v) is not int or not lo<=v<=hi:
        raise ValueError("invalid media generation geometry or budget")
    return v


def _unique(rows):
    result={}
    for k,v in rows:
        if k in result:
            raise ValueError("duplicate media bundle key")
        result[k]=v
    return result


def _artifact(row):
    if (type(row) is not dict or set(row)!={"path","sha256","max_bytes"} or
            type(row["path"]) is not str or not row["path"] or
            Path(row["path"]).is_absolute() or ".." in Path(row["path"]).parts or
            type(row["sha256"]) is not str or not _PIN.fullmatch(row["sha256"])):
        raise ValueError("relative pinned media artifact required")
    _require_int(row["max_bytes"],1,MAX_GRAPH_BYTES)
    return row


def normalize_profile(row):
    if type(row) is not dict or set(row)!={"id","modality","encoder","decoder","tokenizer",
            "geometry","encoder_input","encoder_output","decoder_ids","decoder_context",
            "decoder_output","decoder_mask","prefix_ids","eos_ids","max_context","max_output","threads"}:
        raise ValueError("explicit conditional generation profile required")
    if type(row["id"]) is not str or not _ID.fullmatch(row["id"]) or row["modality"] not in ("image","audio"):
        raise ValueError("invalid media generation identity")
    for k in ("encoder","decoder","tokenizer"):
        _artifact(row[k])
    if (row["encoder"]["max_bytes"]+row["decoder"]["max_bytes"]>MAX_TOTAL_GRAPH_BYTES
            or row["tokenizer"]["max_bytes"]>32*1024**2):
        raise ValueError("media artifact allocation limit")
    for key in ("encoder_input","encoder_output","decoder_ids","decoder_context","decoder_output"):
        if type(row[key]) is not str or not 1<=len(row[key])<=128:
            raise ValueError("explicit tensor name required")
    if row["decoder_mask"] is not None and (type(row["decoder_mask"]) is not str or not 1<=len(row["decoder_mask"])<=128):
        raise ValueError("invalid decoder mask name")
    if len({row["decoder_ids"],row["decoder_context"],row["decoder_mask"]})!=3:
        raise ValueError("decoder tensor names alias")
    _require_int(row["threads"],1,8);_require_int(row["max_context"],4,MAX_CONTEXT)
    _require_int(row["max_output"],1,min(MAX_GENERATED,row["max_context"]-1))
    for k in ("prefix_ids","eos_ids"):
        ids=row[k]
        if type(ids) is not list or not 1<=len(ids)<=32:
            raise ValueError("explicit decoder prefix and stop ids required")
        for token in ids:
            _require_int(token,0,MAX_VOCAB-1)
    if len(set(row["eos_ids"]))!=len(row["eos_ids"]):
        raise ValueError("duplicate EOS ids")
    geometry=row["geometry"]
    if type(geometry) is not dict:
        raise ValueError("explicit media preprocessing geometry required")
    if row["modality"]=="image":
        if set(geometry)!={"width","height","mean","std"}:
            raise ValueError("explicit RGB geometry required")
        _require_int(geometry["width"],16,512);_require_int(geometry["height"],16,512)
        _normalization(geometry["mean"]);_normalization(geometry["std"])
        if any(x<1e-6 for x in geometry["std"]):
            raise ValueError("invalid image standard deviation")
    else:
        if geometry.get("kind")=="waveform" and set(geometry)=={"kind","sample_rate","samples"}:
            pass
        elif geometry.get("kind")=="logmel" and set(geometry)=={"kind","sample_rate","samples",
                "n_fft","hop","mel_bins","mel_filters"}:
            _require_int(geometry["n_fft"],128,1024);_require_int(geometry["hop"],32,512)
            _require_int(geometry["mel_bins"],16,128)
            _artifact(geometry["mel_filters"])
            if geometry["mel_filters"]["max_bytes"]>2*1024**2:
                raise ValueError("mel filter artifact exceeds limit")
        else:
            raise ValueError("explicit waveform or log-mel preprocessing required")
        _require_int(geometry["sample_rate"],8000,48000)
        _require_int(geometry["samples"],256,480000)
        if geometry["kind"]=="logmel" and geometry["samples"]<geometry["n_fft"]:
            raise ValueError("insufficient waveform geometry")
    return json.loads(json.dumps(row,allow_nan=False))


def logmel(waveform,geometry,filters):
    """Centered periodic Hann STFT, power, pinned mel matrix, Whisper scaling.

    Model exporters must supply the exact mel bank used in training.
    """
    import numpy as np
    n=geometry["n_fft"];hop=geometry["hop"];bins=geometry["mel_bins"]
    if (filters.shape!=(bins,n//2+1) or not np.isfinite(filters).all() or
            np.any(filters<0) or np.any(filters.sum(axis=1)<=0)):
        raise ValueError("invalid pinned mel filter geometry")
    signal=np.pad(waveform[0],(n//2,n//2),mode="reflect")
    frames=(len(signal)-n)//hop
    if not 1<=frames or frames*(n//2+1)>MAX_FEATURE_CELLS:
        raise ValueError("spectrogram workspace exceeded")
    view=np.lib.stride_tricks.sliding_window_view(signal,n)[::hop][:frames]
    hann=(.5-.5*np.cos(2*np.pi*np.arange(n)/n)).astype(np.float32)
    power=(np.abs(np.fft.rfft(view*hann,axis=-1))**2).astype(np.float32)
    mel=np.maximum(filters.astype(np.float32)@power.T,1e-10)
    log=np.log10(mel)
    log=np.maximum(log,log.max()-8.0)
    return np.ascontiguousarray(((log+4.0)/4.0)[None,...],dtype=np.float32)


def _shape_matches(expected,actual):
    return len(expected)==len(actual) and all(
        not isinstance(e,int) or e==a for e,a in zip(expected,actual))


class GenerationMediaRegistry:
    def __init__(self,path,expected_sha256):
        path=Path(path)
        data=json.loads(_read_pinned(path,expected_sha256,65536),object_pairs_hook=_unique)
        if (type(data) is not dict or set(data)!={"schema","profiles"}
                or data["schema"]!="skeleton.jeeves.media-generation-config.v1"
                or type(data["profiles"]) is not list or not 1<=len(data["profiles"])<=2):
            raise ValueError("explicit vision and speech generation registry required")
        profiles=[normalize_profile(row) for row in data["profiles"]]
        if len({x["id"] for x in profiles})!=len(profiles) or len({x["modality"] for x in profiles})!=len(profiles):
            raise ValueError("duplicate media generation profile")
        self._profiles={x["id"]:x for x in profiles}
        self._root=path.parent
        self.identity=expected_sha256
        self._lock=threading.RLock()

    def inventory(self):
        return [{"id":r["id"],"modality":r["modality"],"encoder_sha256":r["encoder"]["sha256"],
                 "decoder_sha256":r["decoder"]["sha256"],"tokenizer_sha256":r["tokenizer"]["sha256"],
                 "max_output":r["max_output"]} for r in self._profiles.values()]

    def _bytes(self,spec):
        return _read_pinned(self._root/spec["path"],spec["sha256"],spec["max_bytes"])

    def _open(self,spec,threads):
        import onnxruntime as ort
        raw=self._bytes(spec)
        _validate_graph(raw)
        options=ort.SessionOptions()
        options.intra_op_num_threads=threads
        options.inter_op_num_threads=1
        options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        options.enable_mem_pattern=False
        session=ort.InferenceSession(raw,sess_options=options,providers=["CPUExecutionProvider"])
        if session.get_providers()!=["CPUExecutionProvider"]:
            raise ValueError("media generator provider drift")
        return session

    def generate(self,profile,body,*,question="",max_output=64,interrupt=None):
        import numpy as np
        from tokenizers import Tokenizer
        if type(profile) is not str or profile not in self._profiles:
            raise ValueError("unknown media generator")
        row=self._profiles[profile];mode=row["modality"]
        if type(body) is not dict or set(body)!={"media_type","media_base64","source_sha256"}:
            raise ValueError("explicit transient media bytes required")
        mime=body["media_type"]
        if type(mime) is not str or mime not in _MIME or not mime.startswith(mode+"/"):
            raise ValueError("wrong media modality")
        _require_int(max_output,1,row["max_output"])
        if type(question) is not str or len(question.encode())>2048 or "\x00" in question:
            raise ValueError("bounded vision question required")
        if mode=="audio" and question:
            raise ValueError("speech transcript path does not accept text instructions")
        attested=verify_transient_media(body|{"modality":_MIME[mime]})
        started=time.monotonic()
        def poll():
            if interrupt is not None:
                interrupt()
            if time.monotonic()-started>60:
                raise TimeoutError("cooperative media generation deadline exceeded")
        with self._lock:
            poll()
            raw=base64.b64decode(body["media_base64"],validate=True)
            if mode=="image":
                features,meta=decode_image(raw,mime,row["geometry"])
            else:
                features,meta=decode_wave(raw,row["geometry"])
                if row["geometry"]["kind"]=="logmel":
                    filters=np.load(BytesIO(self._bytes(row["geometry"]["mel_filters"])),allow_pickle=False)
                    features=logmel(features,row["geometry"],filters)
            del raw
            if features.size>MAX_FEATURE_CELLS or not np.isfinite(features).all():
                raise ValueError("invalid encoder feature tensor")
            feature_pin=sha256(features.tobytes()).hexdigest()
            encoder=self._open(row["encoder"],row["threads"])
            inputs=encoder.get_inputs()
            if (len(inputs)!=1 or inputs[0].name!=row["encoder_input"] or inputs[0].type!="tensor(float)"
                    or not _shape_matches(inputs[0].shape,features.shape)):
                raise ValueError("encoder input geometry mismatch")
            output={item.name:item for item in encoder.get_outputs()}.get(row["encoder_output"])
            if output is None or output.type!="tensor(float)" or len(output.shape)!=3:
                raise ValueError("explicit rank-three encoder context required")
            hidden=encoder.run([row["encoder_output"]],{row["encoder_input"]:features})[0]
            del encoder,features
            poll()
            if (hidden.ndim!=3 or hidden.shape[0]!=1 or hidden.size>MAX_FEATURE_CELLS
                    or not np.isfinite(hidden).all()):
                raise ValueError("invalid encoder context")
            hidden_pin=sha256(hidden.tobytes()).hexdigest()
            tok=Tokenizer.from_str(self._bytes(row["tokenizer"]).decode("utf-8"))
            tok.no_truncation();tok.no_padding()
            vocab=tok.get_vocab_size()
            if not 2<=vocab<=MAX_VOCAB:
                raise ValueError("invalid decoder vocabulary size")
            ids=list(row["prefix_ids"])
            if mode=="image" and question.strip():
                encoded=tok.encode(question.strip(),add_special_tokens=False).ids
                if not encoded:
                    raise ValueError("vision question lost during tokenization")
                ids.extend(encoded)
            if (len(ids)+max_output>row["max_context"] or any(
                    not 0<=x<vocab for x in ids+row["eos_ids"])):
                raise ValueError("decoder token budget exceeded")
            initial=list(ids)
            decoder=self._open(row["decoder"],row["threads"])
            inputs={item.name:item for item in decoder.get_inputs()}
            expected={row["decoder_ids"]:"tensor(int64)",row["decoder_context"]:"tensor(float)"}
            if row["decoder_mask"] is not None:
                expected[row["decoder_mask"]]="tensor(int64)"
            if set(inputs)!=set(expected) or any(inputs[k].type!=kind for k,kind in expected.items()):
                raise ValueError("conditional decoder input mismatch")
            out={item.name:item for item in decoder.get_outputs()}.get(row["decoder_output"])
            if out is None or out.type!="tensor(float)" or len(out.shape) not in (2,3):
                raise ValueError("conditional decoder logits required")
            generated=[];finish="length"
            for _ in range(max_output):
                poll()
                data={row["decoder_ids"]:np.asarray([ids],dtype=np.int64),row["decoder_context"]:hidden}
                if row["decoder_mask"] is not None:
                    data[row["decoder_mask"]]=np.ones((1,len(ids)),dtype=np.int64)
                if any(not _shape_matches(inputs[k].shape,v.shape) for k,v in data.items()):
                    raise ValueError("decoder admitted geometry mismatch")
                if len(ids)*vocab>MAX_FEATURE_CELLS:
                    raise ValueError("decoder logits workspace ceiling")
                values=decoder.run([row["decoder_output"]],data)[0]
                poll()
                if values.shape==(1,len(ids),vocab):
                    logits=values[0,-1]
                elif values.shape==(1,vocab):
                    logits=values[0]
                else:
                    raise ValueError("conditional decoder logits shape mismatch")
                if not np.isfinite(logits).all():
                    raise ValueError("nonfinite generated logits")
                token=int(np.argmax(logits));generated.append(token);ids.append(token)
                if token in row["eos_ids"]:
                    finish="eos";break
            visible=generated[:-1] if finish=="eos" else generated
            text=tok.decode(visible,skip_special_tokens=True)
            if len(text.encode())>32768:
                raise ValueError("media generated output exceeds byte limit")
            report={"schema":"skeleton.jeeves.conditional-media-generation.v1",
                "profile":profile,"modality":mode,"registry_sha256":self.identity,
                "encoder_sha256":row["encoder"]["sha256"],"decoder_sha256":row["decoder"]["sha256"],
                "tokenizer_sha256":row["tokenizer"]["sha256"],"source_sha256":attested["source_sha256"],
                "feature_sha256":feature_pin,"encoder_context_sha256":hidden_pin,"encoder_context_shape":list(hidden.shape),
                "question_sha256":sha256(question.encode()).hexdigest(),"prefix_ids":initial,
                "generated_ids":generated,"text":text,"finish_reason":finish,"metadata":meta,
                "encoder_calls":1,"decoder_calls":len(generated),"native_generation_performed":True,
                "media_bytes_persisted":False,"network_called":False,"transcript_committed":False,
                "primary_model_changed":False,"semantic_accuracy_certified":False}
            report["receipt_sha256"]=digest(report)
            return report
