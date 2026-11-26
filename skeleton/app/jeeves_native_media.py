"""Native local media decoding and pinned CPU ONNX image/audio inference.

Actual decoded pixels and PCM samples enter the configured classifier, not
human-written captions. Labels are explicit operator-provisioned model
metadata. This is classification, not general-purpose vision-language
generation, transcription, biometric identification, or video decoding.
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
import warnings
import wave

from skeleton.app.jeeves_media_advisory import MAX_MEDIA_BYTES, verify_transient_media
from skeleton.retrieval.learned_embeddings import _read_pinned, _validate_graph

SCHEMA="skeleton.jeeves.local-media-inference.v1"
MAX_MODELS=2
MAX_PIXELS=8_000_000
MAX_SAMPLES=480_000
MAX_LABELS=2048
MAX_MODEL_BYTES=512*1024**2
_PIN=re.compile(r"[0-9a-f]{64}\Z")
_ID=re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_MIME={"image/png":"image-caption","image/jpeg":"image-caption","image/webp":"image-caption",
       "audio/wav":"audio-transcript"}


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=True,
        separators=(",",":"),allow_nan=False).encode()).hexdigest()


def _unique(pairs):
    result={}
    for k,v in pairs:
        if k in result:
            raise ValueError("duplicate media configuration field")
        result[k]=v
    return result


def _int(v,lo,hi):
    if type(v) is not int or not lo<=v<=hi:
        raise ValueError("invalid local media geometry")
    return v


def _normalization(value):
    if (type(value) is not list or len(value)!=3 or any(
            type(x) not in (int,float) or not math.isfinite(x) or abs(x)>16 for x in value)):
        raise ValueError("explicit bounded channel normalization required")
    return value


def normalize_profile(row):
    fields={"id","modality","model_path","model_sha256","input_name","output_name",
            "labels","threads","max_model_bytes","geometry"}
    if type(row) is not dict or set(row)!=fields:
        raise ValueError("invalid native media profile")
    if (type(row["id"]) is not str or not _ID.fullmatch(row["id"]) or
            row["modality"] not in ("image","audio") or type(row["model_sha256"]) is not str or
            not _PIN.fullmatch(row["model_sha256"])):
        raise ValueError("invalid native media profile identity")
    for key in ("input_name","output_name"):
        if type(row[key]) is not str or not 1<=len(row[key])<=128:
            raise ValueError("explicit model tensor names required")
    path=row["model_path"]
    if type(path) is not str or not path or Path(path).is_absolute() or ".." in Path(path).parts:
        raise ValueError("media model must be relative to configuration")
    _int(row["threads"],1,16);_int(row["max_model_bytes"],1,MAX_MODEL_BYTES)
    labels=row["labels"]
    if (type(labels) is not list or not 2<=len(labels)<=MAX_LABELS or any(
            type(x) is not str or not x.strip() or len(x.encode())>120 or
            any(ord(c)<32 for c in x) for x in labels) or len(set(labels))!=len(labels)):
        raise ValueError("explicit unique bounded classifier labels required")
    geometry=row["geometry"]
    if type(geometry) is not dict:
        raise ValueError("explicit media tensor geometry required")
    if row["modality"]=="image":
        if set(geometry)!={"width","height","mean","std"}:
            raise ValueError("explicit RGB normalization required")
        _int(geometry["width"],16,512);_int(geometry["height"],16,512)
        _normalization(geometry["mean"]);_normalization(geometry["std"])
        if any(x<=0 for x in geometry["std"]):
            raise ValueError("image standard deviations must be positive")
    else:
        if set(geometry)!={"sample_rate","samples"}:
            raise ValueError("explicit PCM waveform geometry required")
        _int(geometry["sample_rate"],8000,48000);_int(geometry["samples"],256,MAX_SAMPLES)
    return json.loads(json.dumps(row,allow_nan=False))


def decode_image(raw,mime,geometry):
    import numpy as np
    from PIL import Image, ImageOps
    formats={"image/png":"PNG","image/jpeg":"JPEG","image/webp":"WEBP"}
    if mime not in formats:
        raise ValueError("unsupported image container")
    with warnings.catch_warnings():
        warnings.simplefilter("error",Image.DecompressionBombWarning)
        with Image.open(BytesIO(raw),formats=[formats[mime]]) as image:
            if image.format!=formats[mime] or getattr(image,"n_frames",1)!=1:
                raise ValueError("image format mismatch or animated input")
            width,height=image.size
            if not 1<=width*height<=MAX_PIXELS:
                raise ValueError("decoded image pixel ceiling exceeded")
            image.load()
            oriented=ImageOps.exif_transpose(image)
            rgb=oriented.convert("RGB").resize(
                (geometry["width"],geometry["height"]),Image.Resampling.BILINEAR)
            pixels=np.asarray(rgb,dtype=np.float32)/np.float32(255.0)
    mean=np.asarray(geometry["mean"],dtype=np.float32)
    std=np.asarray(geometry["std"],dtype=np.float32)
    result=np.ascontiguousarray(((pixels-mean)/std).transpose(2,0,1)[None,...])
    return result,{"original_width":width,"original_height":height,"channels":3,
                   "resized_width":geometry["width"],"resized_height":geometry["height"]}


def decode_wave(raw,geometry):
    import numpy as np
    with wave.open(BytesIO(raw),"rb") as data:
        channels,rate,frames,depth=data.getnchannels(),data.getframerate(),data.getnframes(),data.getsampwidth()
        if (data.getcomptype()!="NONE" or channels not in (1,2) or depth!=2
                or rate!=geometry["sample_rate"] or not 1<=frames<=geometry["samples"]):
            raise ValueError("only admitted fixed-rate bounded PCM16 WAV supported")
        payload=data.readframes(frames)
        if len(payload)!=frames*channels*2 or data.readframes(1):
            raise ValueError("PCM length mismatch")
    pcm=np.frombuffer(payload,dtype="<i2").astype(np.float32).reshape(frames,channels)
    mono=pcm.mean(axis=1,dtype=np.float32)/np.float32(32768)
    signal=np.zeros((1,geometry["samples"]),dtype=np.float32)
    signal[0,:frames]=mono
    return signal,{"original_samples":frames,"sample_rate":rate,"channels":channels,
                   "padded_samples":geometry["samples"]-frames,"sample_width_bits":16}


class LocalMediaRegistry:
    def __init__(self,path,expected_sha256):
        path=Path(path)
        data=json.loads(_read_pinned(path,expected_sha256,512*1024),
                        object_pairs_hook=_unique)
        if (type(data) is not dict or set(data)!={"schema","profiles"} or
                data["schema"]!="skeleton.jeeves.media-config.v1" or type(data["profiles"]) is not list or
                not 1<=len(data["profiles"])<=MAX_MODELS):
            raise ValueError("explicit media registry required")
        profiles=[normalize_profile(row) for row in data["profiles"]]
        if len({r["id"] for r in profiles})!=len(profiles) or len({r["modality"] for r in profiles})!=len(profiles):
            raise ValueError("duplicate local media profile")
        self._profiles={r["id"]:r for r in profiles}
        self._root=path.parent
        self.identity=expected_sha256
        self._lock=threading.RLock()

    def inventory(self):
        return [{"id":r["id"],"modality":r["modality"],"model_sha256":r["model_sha256"],
                 "label_count":len(r["labels"])} for r in self._profiles.values()]

    def infer(self,profile,body,*,top_k=5):
        import numpy as np
        import onnxruntime as ort
        if type(profile) is not str or profile not in self._profiles:
            raise ValueError("unknown local media classifier")
        if type(body) is not dict or set(body)!={"media_type","media_base64","source_sha256"}:
            raise ValueError("explicit transient media bytes required")
        row=self._profiles[profile]
        mime=body["media_type"]
        if type(mime) is not str or mime not in _MIME or not mime.startswith(row["modality"]+"/"):
            raise ValueError("media modality mismatch")
        _int(top_k,1,min(10,len(row["labels"])))
        attested=verify_transient_media(body|{"modality":_MIME[mime]})
        raw=base64.b64decode(body["media_base64"],validate=True)
        if len(raw)>MAX_MEDIA_BYTES:
            raise ValueError("native media byte ceiling exceeded")
        with self._lock:
            if row["modality"]=="image":
                tensor,metadata=decode_image(raw,mime,row["geometry"])
            else:
                tensor,metadata=decode_wave(raw,row["geometry"])
            del raw
            if not np.isfinite(tensor).all():
                raise ValueError("invalid decoded media tensor")
            model=_read_pinned(self._root/row["model_path"],row["model_sha256"],row["max_model_bytes"])
            _validate_graph(model)
            options=ort.SessionOptions()
            options.intra_op_num_threads=row["threads"]
            options.inter_op_num_threads=1
            options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
            options.enable_mem_pattern=False
            session=ort.InferenceSession(model,sess_options=options,providers=["CPUExecutionProvider"])
            inputs=session.get_inputs()
            outputs={out.name:out for out in session.get_outputs()}
            out=outputs.get(row["output_name"])
            if (len(inputs)!=1 or inputs[0].name!=row["input_name"] or inputs[0].type!="tensor(float)"
                    or tuple(inputs[0].shape)!=tensor.shape or out is None or
                    out.type not in ("tensor(float)","tensor(float16)") or
                    tuple(out.shape)!=(1,len(row["labels"])) or session.get_providers()!=["CPUExecutionProvider"]):
                raise ValueError("media classifier graph tensor geometry mismatch")
            logits=session.run([row["output_name"]],{row["input_name"]:tensor})[0]
            if logits.shape!=(1,len(row["labels"])) or not np.isfinite(logits).all():
                raise ValueError("invalid native media logits")
            values=logits[0].astype(np.float64)
            weights=np.exp(values-values.max())
            probabilities=weights/weights.sum()
            indices=sorted(range(len(values)),key=lambda i:(-float(probabilities[i]),i))[:top_k]
            result={"schema":SCHEMA,"registry_sha256":self.identity,"profile":profile,
                    "modality":row["modality"],"model_sha256":row["model_sha256"],
                    "profile_sha256":digest(row),"media_type":mime,
                    "source_sha256":attested["source_sha256"],"media_size_bytes":attested["media_size_bytes"],
                    "decoded_tensor_sha256":sha256(tensor.tobytes()).hexdigest(),
                    "tensor_shape":list(tensor.shape),"metadata":metadata,
                    "runtime":ort.__version__,"predictions":[{"label_index":i,
                        "label":row["labels"][i],"score_ppm":round(float(probabilities[i])*1_000_000)}
                        for i in indices],
                    "native_classifier_executed":True,"scores_calibrated":False,
                    "primary_model_changed":False,"media_bytes_persisted":False,
                    "network_called":False,"transcript_committed":False,
                    "general_vision_language_reasoning":False}
            result["receipt_sha256"]=digest(result)
            return result
