"""Measure real rendered original audio and vector output quality signals."""
from __future__ import annotations

from math import sqrt
from pathlib import Path
import struct
import wave
import xml.etree.ElementTree as ET

from .studio_ecosystem_offline_verify import verify_studio_bundle
from .studio_ecosystem_quest import StudioQuestError

SVG="{http://www.w3.org/2000/svg}"


def inspect_rendered_media(bundle: Path, *, authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("media metrics require operator authorization")
    bundle=Path(bundle)
    verified=verify_studio_bundle(bundle,authorized=True)
    xml=(bundle/"environment.svg").read_bytes()
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise StudioQuestError("external or declared XML entities forbidden")
    try:
        root=ET.fromstring(xml)
    except ET.ParseError as exc:
        raise StudioQuestError("rendered SVG is not well-formed") from exc
    if root.tag!=SVG+"svg":
        raise StudioQuestError("rendered environment has wrong media root")
    tags=[element.tag for element in root.iter()]
    disallowed={SVG+"script",SVG+"foreignObject"}
    if any(tag in disallowed for tag in tags) or any(
        "href" in key.lower() or key.lower().startswith("on")
        for node in root.iter() for key in node.attrib
    ):
        raise StudioQuestError("active or externally linked SVG content")
    count=0
    square=0
    peak=0
    try:
        with wave.open(str(bundle/"soundscape.wav"),"rb") as stream:
            if (stream.getnchannels()!=1 or stream.getsampwidth()!=2
                    or stream.getframerate()!=16000):
                raise StudioQuestError("unexpected original audio PCM format")
            total=stream.getnframes()
            while chunk:=stream.readframes(4096):
                if len(chunk)%2:
                    raise StudioQuestError("invalid PCM frame alignment")
                for (sample,) in struct.iter_unpack("<h",chunk):
                    count+=1
                    square+=sample*sample
                    peak=max(peak,abs(sample))
    except (wave.Error, EOFError) as exc:
        raise StudioQuestError("damaged local audio payload") from exc
    if count!=total or count==0:
        raise StudioQuestError("incomplete or empty original PCM waveform")
    rms=sqrt(square/count)/32768
    return {"schema":"skeleton.game_builder.studio_media_metrics.v1",
            "project_id":verified["project_id"],
            "svg_geometry_elements":sum(tag in {SVG+"path",SVG+"polygon",
                                               SVG+"circle"} for tag in tags),
            "audio_frame_count":count,
            "audio_peak_fraction":round(peak/32768,6),
            "audio_rms_fraction":round(rms,6),
            "audio_duration_seconds":count/16000,
            "measured_local_content":True,
            "artistic_quality_verified":False,"rights_verified":False,
            "native_gameplay_qualified":False,"release_certified":False}
