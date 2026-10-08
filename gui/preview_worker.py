"""Decode adjacent frames by their actual timestamps rather than average frame rate."""
import bisect
import json
import os
import subprocess
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
from core.ffprobe_service import locate

def capture(args):
    return subprocess.run(args, capture_output=True, check=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0).stdout

class FrameWorker(QThread):
    ready = Signal(object, float, object)
    failed = Signal(str)
    def __init__(self, path, position, direction):
        super().__init__(); self.path = path; self.position = position; self.direction = direction

    def run(self):
        try:
            # Seeking ffprobe begins at the previous keyframe; the absolute end ensures
            # the read reaches the current position even on long GOP material.
            data = json.loads(capture([locate('ffprobe'), '-v', 'error', '-select_streams', 'v:0',
                '-read_intervals', f'{max(0, self.position-2):.6f}%{self.position+3:.6f}',
                '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(self.path)]))
            times = sorted(float(f['best_effort_timestamp_time']) for f in data['frames']
                           if 'best_effort_timestamp_time' in f)
            if not times: raise RuntimeError('无法读取相邻帧时间戳')
            if self.direction > 0:
                index = min(len(times)-1, bisect.bisect_right(times, self.position + .0005))
            else:
                index = max(0, bisect.bisect_left(times, self.position - .0005) - 1)
            timestamp = times[index]
            if self.isInterruptionRequested(): return
            png = capture([locate('ffmpeg'), '-v', 'error', '-nostdin', '-ss', f'{timestamp:.6f}',
                '-i', str(self.path), '-frames:v', '1', '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease',
                '-f', 'image2pipe', '-c:v', 'png', 'pipe:1'])
            image = QImage.fromData(png)
            if image.isNull(): raise RuntimeError('帧解码失败')
            if not self.isInterruptionRequested(): self.ready.emit(self.path, timestamp, image)
        except Exception as exc: self.failed.emit(str(exc))
