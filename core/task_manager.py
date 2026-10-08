from dataclasses import dataclass
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from models import Segment, OutputOptions
from .ffmpeg_service import FFmpegService, Cancelled
from .merge_service import process_segments

@dataclass
class Job:
    segments: list[Segment]
    output: Path
    options: OutputOptions
    overwrite: bool = False

class TaskManager(QThread):
    progress = Signal(int, float, object)
    completed = Signal(int, object)
    failed = Signal(int, str)
    def __init__(self, jobs, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.service = FFmpegService()

    def cancel(self): self.service.cancel()

    def run(self):
        for index, job in enumerate(self.jobs):
            if self.service.cancel_event.is_set(): break
            try:
                result = process_segments(self.service, job.segments, job.output, job.options,
                    lambda p, eta: self.progress.emit(index, p, eta), job.overwrite)
                self.completed.emit(index, result)
            except Cancelled:
                self.failed.emit(index, '任务已取消'); break
            except Exception as exc:
                self.failed.emit(index, str(exc))
