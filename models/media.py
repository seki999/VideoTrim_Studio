from dataclasses import dataclass
from pathlib import Path

@dataclass
class MediaInfo:
    path: Path
    duration: float
    width: int
    height: int
    fps: float
    codec: str
    streams: list
    size: int

    @property
    def audio(self):
        return next((s for s in self.streams if s['codec_type'] == 'audio'), None)

    @property
    def signature(self):
        fields = ('codec_type', 'codec_name', 'profile', 'level', 'width', 'height',
                  'pix_fmt', 'time_base', 'r_frame_rate', 'sample_rate', 'channels',
                  'channel_layout', 'extradata_hash', 'sample_aspect_ratio')
        return tuple(tuple(s.get(k) for k in fields) for s in self.streams
                     if s['codec_type'] in ('video', 'audio'))

@dataclass
class Segment:
    path: Path
    start: float = 0
    end: float | None = None

@dataclass
class OutputOptions:
    mode: str = 'crf'  # copy, crf, bitrate, size
    encoder: str = 'libx264'
    crf: int = 23
    bitrate_kbps: int = 2000
    target_mb: float = 20
    two_pass: bool = False
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    pad: bool = True
