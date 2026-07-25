"""
gameforge.media.studio — Jeeves in-game media production.

Turns a ``GameWorld`` into real deliverables:
  * IMAGE SET — main character, cast, promo 1-3, extended promo 4-10,
    landscapes 10-20 (each a real captured in-game frame).
  * VIDEOS — streamed frame-by-frame to the bundled static ffmpeg (imageio):
    30s clip, 120s clip, 2-min trailer, 1-min showcase, and a 5-min let's-play
    with generated TTS commentary muxed onto the gameplay footage.
"""
from __future__ import annotations

import base64
import io
import os
import subprocess
import time
from typing import Dict, List, Optional

import imageio.v2 as iio
import imageio_ffmpeg
import numpy as np

from gameforge.media.renderer import GameWorld

_MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "artifacts_media")
os.makedirs(_MEDIA_DIR, exist_ok=True)

# name → (duration_s, fps, mode, label)
VIDEO_TYPES = {
    "clip30":    (30,  15, "gameplay",  "30s Gameplay"),
    "clip120":   (120, 12, "gameplay",  "120s Gameplay"),
    "trailer":   (120, 12, "trailer",   "2-min Trailer"),
    "showcase":  (60,  15, "showcase",  "1-min Showcase"),
    "letsplay":  (300, 8,  "letsplay",  "5-min Let's Play w/ Commentary"),
}
_VW, _VH = 1024, 576      # cinematic video resolution (16:9, /8 aligned)
_IW, _IH = 1280, 720      # HD still resolution


def _img_b64(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ── IMAGE SET ──────────────────────────────────────────────────
def render_image_set(world: GameWorld) -> List[Dict]:
    out: List[Dict] = []

    def push(key, title, img):
        out.append({"key": key, "title": title, "mime": "image/png", "base64": _img_b64(img)})

    # main character — portrait close-up
    push("main_character", f"{world.name} — Protagonist",
         world.render_frame(3.0, _IW, _IH, camera_x=world.player_pos(3.0)[0] - _IW / 2,
                            hud=False, portrait=0))
    # cast — a lineup of every cast member
    push("cast", f"{world.name} — Cast",
         world.render_frame(8.0, _IW, _IH, hud=False, label="THE CAST"))
    # promos 1-3 — dramatic hero shots
    for i in range(1, 4):
        push(f"promo_{i}", f"{world.name} — Promo {i}",
             world.render_frame(6.0 * i + 2, _IW, _IH, hud=False,
                                label=f"{world.name.upper()}"))
    # extended promos 4-10 — varied scenes
    for i in range(4, 11):
        push(f"promo_{i}", f"{world.name} — Extended Promo {i}",
             world.render_frame(11.0 * i, _IW, _IH, hud=False,
                                portrait=(i % len(world.cast))))
    # landscapes 10-20 — wide world regions (no player/HUD)
    for i in range(10, 21):
        cam = (world.world_len / 11) * (i - 10)
        push(f"landscape_{i}", f"{world.name} — Landscape {i}",
             world.render_frame(i * 1.7, _IW, _IH, camera_x=cam, hud=False))
    return out


# ── VIDEO ──────────────────────────────────────────────────────
def _frames(world: GameWorld, vtype: str, W: int, H: int):
    dur, fps, mode, _label = VIDEO_TYPES[vtype]
    total = int(dur * fps)
    for n in range(total):
        t = n / fps
        if mode == "trailer":
            # montage: title cards every ~5s, else gameplay
            seg = int(t) % 6
            if seg == 0:
                img = world.render_frame(t, W, H, hud=False, portrait=int(t / 6) % len(world.cast),
                                         label=f"{world.name.upper()}")
            else:
                img = world.render_frame(t, W, H, hud=False)
        elif mode == "showcase":
            img = world.render_frame(t, W, H, hud=False,
                                     label="SHOWCASE" if int(t) % 8 < 2 else None)
        elif mode == "letsplay":
            img = world.render_frame(t, W, H, hud=True)
        else:
            img = world.render_frame(t, W, H, hud=True)
        yield np.asarray(img.convert("RGB"))


def _commentary_script(world: GameWorld) -> str:
    beats = [
        f"Hey everyone, welcome back! Today we're diving into {world.name}.",
        f"Right off the bat you can see our hero moving through this world.",
        f"The cast here is wild — we've got {', '.join(world.cast[:3])} and more.",
        "Watch how the parallax terrain gives it real depth as we travel.",
        "The pacing feels great, and there's a ton to explore out here.",
        f"If you're enjoying this look at {world.name}, you know what to do.",
        "Let's keep pushing forward and see what the world has in store.",
    ]
    return " ".join(beats)


def _tts_mp3(text: str, path: str) -> bool:
    """Generate a commentary voice track via OpenAI TTS (Emergent key).
    Always invoked from a worker thread (no running loop), so asyncio.run is safe."""
    key = os.getenv("EMERGENT_LLM_KEY", "")
    if not key:
        return False
    try:
        import asyncio
        from emergentintegrations.llm.openai.text_to_speech import OpenAITextToSpeech

        async def _run():
            tts = OpenAITextToSpeech(api_key=key)
            audio = await tts.generate_speech(text=text[:4000], voice="onyx")
            data = audio if isinstance(audio, (bytes, bytearray)) else bytes(audio)
            with open(path, "wb") as f:
                f.write(data)

        asyncio.run(_run())
        return os.path.exists(path) and os.path.getsize(path) > 200
    except Exception as e:  # noqa: BLE001
        print(f"[media] TTS failed: {type(e).__name__}: {e}", flush=True)
        return False


def produce_video(world: GameWorld, vtype: str, job_id: str,
                  progress: Optional[Dict] = None) -> Dict:
    dur, fps, mode, label = VIDEO_TYPES[vtype]
    W, H = (_VW, _VH)
    raw_path = os.path.join(_MEDIA_DIR, f"{job_id}.mp4")
    total = int(dur * fps)
    writer = iio.get_writer(raw_path, fps=fps, codec="libx264", quality=6,
                            macro_block_size=8, ffmpeg_log_level="error")
    try:
        for i, frame in enumerate(_frames(world, vtype, W, H)):
            writer.append_data(frame)
            if progress is not None and i % 30 == 0:
                progress["rendered"] = i
                progress["percent"] = round(100.0 * i / max(1, total), 1)
    finally:
        writer.close()
    if progress is not None:
        progress["rendered"] = total
        progress["percent"] = 100.0

    final_path = raw_path
    has_audio = False
    if mode == "letsplay":
        mp3 = os.path.join(_MEDIA_DIR, f"{job_id}.mp3")
        script = _commentary_script(world)
        if _tts_mp3(script, mp3):
            muxed = os.path.join(_MEDIA_DIR, f"{job_id}_av.mp4")
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            try:
                subprocess.run([exe, "-y", "-i", raw_path, "-i", mp3,
                                "-c:v", "copy", "-c:a", "aac", "-shortest", muxed],
                               check=True, capture_output=True, timeout=120)
                final_path = muxed
                has_audio = True
            except Exception:  # noqa: BLE001
                final_path = raw_path

    size = os.path.getsize(final_path) if os.path.exists(final_path) else 0
    return {"ok": True, "job_id": job_id, "type": vtype, "label": label,
            "duration_s": dur, "fps": fps, "frames": total, "has_commentary": has_audio,
            "size_bytes": size, "path": final_path,
            "download_url": f"/api/jeeves/media/download/{job_id}"}


def media_path(job_id: str) -> Optional[str]:
    for suffix in ("_av.mp4", ".mp4"):
        p = os.path.join(_MEDIA_DIR, f"{job_id}{suffix}")
        if os.path.exists(p):
            return p
    return None


def _factsheet_pdf(world: GameWorld, path: str):
    """Jeeves-written one-page press fact-sheet."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    doc = SimpleDocTemplate(path, pagesize=LETTER, title=f"{world.name} Press Kit")
    ss = getSampleStyleSheet()
    h = ParagraphStyle("H", parent=ss["Title"], textColor=colors.HexColor("#7c3aed"))
    sub = ParagraphStyle("S", parent=ss["Heading2"], textColor=colors.HexColor("#22c55e"))
    story = [Paragraph(f"{world.name} — Official Press Kit", h), Spacer(1, 0.2 * inch),
             Paragraph("Overview", sub),
             Paragraph(f"{world.name} is a cinematic adventure through a hand-crafted world. "
                       f"Featuring a cast of {len(world.cast)} — {', '.join(world.cast[:5])} — "
                       f"across sprawling, atmospheric landscapes.", ss["BodyText"]),
             Spacer(1, 0.15 * inch), Paragraph("Included Assets", sub),
             Paragraph("23 hi-res stills (protagonist, cast, 10 promos, 11 landscapes), "
                       "a 2-minute trailer and a 1-minute showcase — all rendered in-engine.",
                       ss["BodyText"]),
             Spacer(1, 0.15 * inch), Paragraph("Contact", sub),
             Paragraph("Produced by Jeeves · GameForge Zaibatsu CNS", ss["BodyText"])]
    doc.build(story)


def produce_presskit(world: GameWorld, job_id: str, progress: Optional[Dict] = None) -> Dict:
    """Bundle a store-ready ZIP: 23 stills + trailer + showcase + fact-sheet PDF."""
    import zipfile
    if progress is not None:
        progress["stage"] = "images"; progress["percent"] = 5.0
    imgs = render_image_set(world)
    if progress is not None:
        progress["stage"] = "trailer"; progress["percent"] = 30.0
    produce_video(world, "trailer", f"{job_id}_trailer", None)
    if progress is not None:
        progress["stage"] = "showcase"; progress["percent"] = 65.0
    produce_video(world, "showcase", f"{job_id}_showcase", None)
    if progress is not None:
        progress["stage"] = "packaging"; progress["percent"] = 90.0
    pdf_path = os.path.join(_MEDIA_DIR, f"{job_id}_factsheet.pdf")
    _factsheet_pdf(world, pdf_path)

    zip_path = os.path.join(_MEDIA_DIR, f"{job_id}_presskit.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for im in imgs:
            z.writestr(f"images/{im['key']}.png", base64.b64decode(im["base64"]))
        for tag in ("trailer", "showcase"):
            mp = media_path(f"{job_id}_{tag}")
            if mp:
                z.write(mp, f"video/{tag}.mp4")
        z.write(pdf_path, "factsheet.pdf")
        z.writestr("README.txt", f"{world.name} Press Kit — produced by Jeeves / GameForge.\n"
                   f"{len(imgs)} stills, trailer, showcase, fact-sheet.\n")
    if progress is not None:
        progress["percent"] = 100.0; progress["stage"] = "done"
    return {"ok": True, "job_id": job_id, "images": len(imgs),
            "size_bytes": os.path.getsize(zip_path),
            "download_url": f"/api/jeeves/media/presskit/download/{job_id}"}


def presskit_path(job_id: str) -> Optional[str]:
    p = os.path.join(_MEDIA_DIR, f"{job_id}_presskit.zip")
    return p if os.path.exists(p) else None


__all__ = ["GameWorld", "render_image_set", "produce_video", "media_path",
           "produce_presskit", "presskit_path", "VIDEO_TYPES"]
