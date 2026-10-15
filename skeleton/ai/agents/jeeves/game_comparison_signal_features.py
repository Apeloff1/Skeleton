"""Bounded, non-reconstructive audiovisual descriptors of actual libretro output.

Extracts finite structural measurements for user/Dragon cross-game comparison.
No raw image, PCM or copyrighted expressive content is written into a feature
record; game mechanics, narrative quality and music meaning are not inferred.
"""
from __future__ import annotations

import math
import struct
from collections.abc import Mapping

SCHEMA = "skeleton.game.comparison_signal_features.v1"
MAX_PIXELS_SAMPLED = 8192
MAX_AUDIO_FRAMES_SAMPLED = 4096
LUMA_BINS = 16


def _entropy(histogram: list[int]) -> float:
    total=sum(histogram)
    return round(-sum(
        (x/total)*math.log2(x/total) for x in histogram if x
    ), 6) if total else 0.0


def describe_native_frame(pixels: bytes, width: int, height: int) -> dict[str, object]:
    if (type(pixels) is not bytes or type(width) is not int or type(height) is not int
        or not 1 <= width <= 4096 or not 1 <= height <= 4096
        or len(pixels) != width*height*3):
        raise ValueError("RGB24 frame structure or dimensions are invalid")
    stride=max(1,math.ceil((width*height)/MAX_PIXELS_SAMPLED))
    count=0
    hist=[0]*LUMA_BINS
    channel_sums=[0,0,0]
    spread=0.0
    adjacent=0
    edges=0
    occupied=0
    last_luma=None
    for i in range(0,width*height,stride):
        r,g,b=pixels[i*3:i*3+3]
        lum=(54*r+183*g+19*b)//256
        hist[min(15,lum//16)]+=1
        channel_sums[0]+=r
        channel_sums[1]+=g
        channel_sums[2]+=b
        spread+=max(r,g,b)-min(r,g,b)
        occupied+=int(lum>24)
        if last_luma is not None:
            adjacent+=1
            edges+=int(abs(lum-last_luma)>=28)
        last_luma=lum
        count+=1
    if not count:
        raise ValueError("Native RGB frame has no pixels")
    return {
        "schema_version":SCHEMA,
        "analysis_kind":"decimated_rgb24_texture_not_semantic_vision",
        "pixels_sampled":count,
        "luminance_histogram_16":hist,
        "luminance_entropy_bits":_entropy(hist),
        "bright_pixel_fraction":round(sum(hist[11:])/count,6),
        "dark_pixel_fraction":round(sum(hist[:3])/count,6),
        "occupied_pixel_fraction":round(occupied/count,6),
        "scan_edge_ratio":round(edges/max(1,adjacent),6),
        "mean_rgb": [round(v/count/255,6) for v in channel_sums],
        "mean_channel_range":round(spread/count/255,6),
        "camera_motion_detected":False,
        "gameplay_semantics_inferred":False,
    }


def describe_native_audio(pcm: bytes, sample_rate: float | int | None) -> dict[str, object]:
    if type(pcm) is not bytes or len(pcm)%4 or len(pcm)>131072*4:
        raise ValueError("Native stereo PCM buffer has an invalid bounded length")
    if sample_rate is not None and (
        type(sample_rate) not in (int,float) or not math.isfinite(sample_rate)
        or not 0<sample_rate<=384000
    ):
        raise ValueError("Native sample rate is not a finite declared value")
    total=len(pcm)//4
    stride=max(1,math.ceil(total/MAX_AUDIO_FRAMES_SAMPLED))
    count=0
    sum_mono_sq=0
    sum_left_sq=0
    sum_right_sq=0
    delta_sum=0
    diff_count=0
    sign_changes=0
    silence=0
    peaks=0
    prev=None
    for index in range(0,total,stride):
        left,right=struct.unpack_from("<hh",pcm,index*4)
        mono=(left+right)/2
        sum_mono_sq+=mono*mono
        sum_left_sq+=left*left
        sum_right_sq+=right*right
        silence+=int(abs(left)<32 and abs(right)<32)
        peaks+=int(max(abs(left),abs(right))>=30000)
        if prev is not None:
            diff_count+=1
            delta_sum+=abs(mono-prev)
            sign_changes+=int((mono>=0)!=(prev>=0))
        prev=mono
        count+=1
    if not count:
        return {
            "schema_version":SCHEMA,
            "analysis_kind":"bounded_native_stereo_pcm_texture",
            "sampled_frames":0,
            "sample_rate":sample_rate,
            "rms_mono":0.0,
            "rms_left":0.0,
            "rms_right":0.0,
            "stereo_energy_imbalance":0.0,
            "zero_crossing_fraction":0.0,
            "mean_normalized_step_change":0.0,
            "silence_fraction":1.0,
            "peak_fraction":0.0,
            "audio_emitted":False,
            "music_style_or_emotion_recognized":False,
        }
    left_rms=math.sqrt(sum_left_sq/count)/32768
    right_rms=math.sqrt(sum_right_sq/count)/32768
    return {
        "schema_version":SCHEMA,
        "analysis_kind":"bounded_native_stereo_pcm_texture",
        "sampled_frames":count,
        "sample_rate":sample_rate,
        "rms_mono":round(math.sqrt(sum_mono_sq/count)/32768,6),
        "rms_left":round(left_rms,6),
        "rms_right":round(right_rms,6),
        "stereo_energy_imbalance":round(abs(left_rms-right_rms),6),
        "zero_crossing_fraction":round(sign_changes/max(1,diff_count),6),
        "mean_normalized_step_change":round(delta_sum/max(1,diff_count)/32768,6),
        "silence_fraction":round(silence/count,6),
        "peak_fraction":round(peaks/count,6),
        "audio_emitted":True,
        "music_style_or_emotion_recognized":False,
    }


def compare_native_texture(a: Mapping[str, object], b: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(a,Mapping) or not isinstance(b,Mapping):
        raise ValueError("Native texture comparison requires feature objects")
    keys=("luminance_entropy_bits","dark_pixel_fraction","scan_edge_ratio","mean_channel_range")
    audio=("rms_mono","stereo_energy_imbalance","zero_crossing_fraction","silence_fraction")
    for x in (a,b):
        if not isinstance(x.get("video"),Mapping) or not isinstance(x.get("audio"),Mapping):
            raise ValueError("Native texture record lacks video or PCM features")
    output={}
    for group,fields in (("video",keys),("audio",audio)):
        for field in fields:
            left=a[group][field]
            right=b[group][field]
            if type(left) not in (int,float) or type(right) not in (int,float) or not (
                math.isfinite(left) and math.isfinite(right)
            ):
                raise ValueError("Comparative texture metrics require finite actual observations")
            output[group+"_"+field+"_absolute_difference"]=round(abs(left-right),6)
    output["quality_or_music_style_winner"]=None
    output["semantic_training_labels_generated"]=False
    return output
