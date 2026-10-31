"""
Media processing with ffmpeg/ffprobe — inspect, convert, trim, resize, compress, extract frames/audio, replace audio, mute, make GIFs, add subtitles/overlays, and combine videos.
"""
def process(cmd: str) -> str:
    return f"ffmpeg {cmd}"
