"""Non-reconstructive multispectral native-game observation features.

CPU-bounded spatial RGB24 change measurements (4x4 coarse tile energy),
plus decimated stereo PCM spectral-energy fingerprints (8 fixed DFT bins).
No pixel map, game frame, waveform, character, music notes, lyrics or
mechanics labels leave this extractor; it does not learn model weights.
"""
from __future__ import annotations

import math
import struct
from typing import Any

SCHEMA="skeleton.game.native_multispectral_observation.v1"
MAX_PIXELS=4_194_304
MAX_VISUAL_SAMPLE=8192
MAX_AUDIO_FRAMES=131072
MAX_SPECTRAL_SAMPLE=512
TILE_AXIS=4
FREQUENCY_BINS=(1,2,3,4,6,8,12,16)


def describe_native_spatial_change(
    before:bytes,after:bytes,width:int,height:int
)->dict[str,Any]:
    if (type(width) is not int or type(height) is not int
        or not 1<=width<=4096 or not 1<=height<=4096
        or width*height>MAX_PIXELS or type(before) is not bytes
        or type(after) is not bytes
        or len(before)!=width*height*3 or len(after)!=len(before)):
        raise ValueError("Native 4×4 motion descriptor needs two equal bounded RGB24 frames")
    count=width*height
    stride=max(1,math.ceil(count/MAX_VISUAL_SAMPLE))
    totals=[0]*16
    energy=[0.0]*16
    changed=[0]*16
    signed_luma=0.0
    all_energy=0.0
    for index in range(0,count,stride):
        y=index//width
        x=index%width
        tile=min(3,x*4//width)+4*min(3,y*4//height)
        pos=index*3
        br,bg,bb=before[pos:pos+3]
        ar,ag,ab=after[pos:pos+3]
        rgb_delta=(abs(ar-br)+abs(ag-bg)+abs(ab-bb))/(3*255)
        lum_before=(54*br+183*bg+19*bb)/256
        lum_after=(54*ar+183*ag+19*ab)/256
        signed_luma+=(lum_after-lum_before)/255
        totals[tile]+=1
        energy[tile]+=rgb_delta
        all_energy+=rgb_delta
        changed[tile]+=int(rgb_delta>0.065)
    samples=sum(totals)
    motion_count=sum(changed)
    if samples<1:
        raise ValueError("A native spatial-change descriptor needs pixels")
    tile_energy=[
        round(energy[i]/totals[i],6) if totals[i] else 0.0
        for i in range(16)
    ]
    tile_changed=[
        round(changed[i]/totals[i],6) if totals[i] else 0.0
        for i in range(16)
    ]
    result={
        "schema_version":SCHEMA,
        "analysis_kind":"coarse_rgb24_change_not_optical_flow_or_semantic_vision",
        "samples":samples,
        "coarse_grid_rows":4,
        "coarse_grid_columns":4,
        "tile_mean_rgb_differences":tile_energy,
        "tile_changed_pixel_fractions":tile_changed,
        "overall_mean_rgb_change":round(all_energy/samples,6),
        "overall_changed_pixel_fraction":round(motion_count/samples,6),
        "mean_signed_luminance_shift":round(signed_luma/samples,6),
        "zero_visual_change_observed":motion_count==0 and all_energy==0,
        "camera_motion_or_player_movement_inferred":False,
        "native_frame_pixels_or_assets_copied":False,
        "model_weights_changed":False,
    }
    return result


def describe_native_spectral_audio(pcm:bytes,sample_rate:int|float|None)->dict[str,Any]:
    if (type(pcm) is not bytes or len(pcm)%4!=0
        or len(pcm)>MAX_AUDIO_FRAMES*4):
        raise ValueError("Audio spectral feature requires bounded stereo s16le PCM")
    if (sample_rate is not None and (
        type(sample_rate) not in (int,float)
        or not math.isfinite(sample_rate) or not 0<sample_rate<=384000
    )):
        raise ValueError("Native spectral audio sample rate invalid")
    frames=len(pcm)//4
    stride=max(1,math.ceil(frames/MAX_SPECTRAL_SAMPLE))
    values=[]
    for index in range(0,frames,stride):
        l,r=struct.unpack_from("<hh",pcm,index*4)
        values.append((l+r)/65536)
        if len(values)>=MAX_SPECTRAL_SAMPLE:
            break
    n=len(values)
    if n<2 or all(v==0 for v in values):
        powers=[0.0]*len(FREQUENCY_BINS)
        emitted=False
    else:
        # Hann-windowed, bounded discrete Fourier samples; FFT dependency
        # and raw PCM persistence are deliberately unnecessary.
        hann=[
            values[i]*(0.5-0.5*math.cos(2*math.pi*i/(n-1)))
            for i in range(n)
        ]
        powers=[]
        for k in FREQUENCY_BINS:
            real=imag=0.0
            for i,v in enumerate(hann):
                angle=(2*math.pi*k*i)/n
                real+=v*math.cos(angle)
                imag-=v*math.sin(angle)
            powers.append(real*real+imag*imag)
        emitted=sum(powers)>1e-12
    total=sum(powers)
    normalized=[
        round(value/total,6) if total>0 else 0.0 for value in powers
    ]
    centroid=(
        sum(i*value for i,value in enumerate(powers))/(max(1,len(powers)-1)*total)
        if total>0 else 0.0
    )
    return {
        "schema_version":SCHEMA,
        "analysis_kind":"decimated_hann_window_eight_dft_bins_not_music_transcription",
        "sampled_stereo_frames":n,
        "sample_stride":stride,
        "declared_sample_rate":sample_rate,
        "normalized_spectral_bin_energy":normalized,
        "normalized_bin_index_centroid":round(centroid,6),
        "sample_emits_frequency_energy":emitted,
        "sound_effect_music_or_voice_recognized":False,
        "original_audio_or_music_copied":False,
        "llm_weights_changed":False,
    }


def summarize_multispectral_change(
    baseline:dict[str,Any],variant:dict[str,Any]
)->dict[str,Any]:
    """Measure feature deltas only; native control group must be checked elsewhere."""
    if (baseline.get("spatial",{}).get("schema_version")!=SCHEMA
        or variant.get("spatial",{}).get("schema_version")!=SCHEMA
        or baseline.get("spectral_audio",{}).get("schema_version")!=SCHEMA
        or variant.get("spectral_audio",{}).get("schema_version")!=SCHEMA):
        raise ValueError("Paired native multispectral descriptors need approved schema")
    a=baseline["spatial"];b=variant["spatial"]
    ca=baseline["spectral_audio"];cb=variant["spectral_audio"]
    if (len(a["tile_mean_rgb_differences"])!=16
        or len(b["tile_mean_rgb_differences"])!=16
        or len(ca["normalized_spectral_bin_energy"])!=8
        or len(cb["normalized_spectral_bin_energy"])!=8):
        raise ValueError("Native multispectral feature arrays differ in shape")
    return {
        "schema_version":SCHEMA,
        "analysis_kind":"paired_abstract_native_signal_differences",
        "mean_rgb_motion_absolute_difference":round(
            abs(a["overall_mean_rgb_change"]-b["overall_mean_rgb_change"]),6),
        "spatial_tile_energy_l1_mean_difference":round(
            sum(abs(x-y) for x,y in zip(
                a["tile_mean_rgb_differences"],
                b["tile_mean_rgb_differences"],strict=True,
            ))/16,6),
        "spectral_energy_l1_mean_difference":round(
            sum(abs(x-y) for x,y in zip(
                ca["normalized_spectral_bin_energy"],
                cb["normalized_spectral_bin_energy"],strict=True,
            ))/8,6),
        "spectral_centroid_absolute_difference":round(
            abs(ca["normalized_bin_index_centroid"]-cb["normalized_bin_index_centroid"]),6),
        "meaningful_gameplay_mechanic_inferred":False,
        "visual_content_or_audio_reconstructable_from_report":False,
        "model_weights_promoted":False,
    }


def native_step_multispectral_receipt(
    prior_frame:dict[str,Any]|None,
    prior_pixels:bytes|None,
    current_frame:dict[str,Any],
    current_pixels:bytes,
    current_pcm:bytes,
)->dict[str,Any]:
    """Bind source RGB/PCM hashes to ephemeral abstract audio/visual features."""
    import hashlib

    if (not isinstance(current_frame,dict)
        or type(current_pixels) is not bytes
        or type(current_pcm) is not bytes):
        raise ValueError("Native multispectral receipt needs actual worker audiovisual bytes")
    frame_hash=hashlib.sha256(current_pixels).hexdigest()
    pcm_hash=hashlib.sha256(current_pcm).hexdigest()
    if (frame_hash!=current_frame.get("pixel_sha256")
        or pcm_hash!=current_frame.get("audio_sha256")):
        raise ValueError("Native multispectral input no longer matches the worker frame/PCM SHA-256")
    w=current_frame.get("width")
    h=current_frame.get("height")
    if (type(w) is not int or type(h) is not int
        or not 1<=w<=4096 or not 1<=h<=4096
        or len(current_pixels)!=w*h*3):
        raise ValueError("Native spatial feature frame shape is invalid")
    if (prior_frame is not None and type(prior_pixels) is bytes
        and prior_frame.get("width")==w and prior_frame.get("height")==h
        and len(prior_pixels)==len(current_pixels)):
        spatial=describe_native_spatial_change(prior_pixels,current_pixels,w,h)
        spatial_status="measured_same_geometry_native_frame_delta"
    else:
        spatial=None
        spatial_status="not_comparable_before_frame_or_geometry_changed"
    spectral=describe_native_spectral_audio(
        current_pcm,current_frame.get("sample_rate"),
    )
    result={
        "schema_version":SCHEMA,
        "source_frame_sha256":frame_hash,
        "source_pcm_sha256":pcm_hash,
        "spatial_status":spatial_status,
        "spatial":spatial,
        "spectral_audio":spectral,
        "visual_frames_copied":False,
        "audio_samples_copied":False,
        "physical_camera_motion_qualified":False,
        "gameplay_mechanics_or_music_transcribed":False,
        "ai_model_weights_modified":False,
    }
    return result
