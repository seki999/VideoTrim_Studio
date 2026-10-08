import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
import psutil
from .ffprobe_service import locate, probe

class Cancelled(Exception):
    pass

class FFmpegService:
    def __init__(self, log_dir=None):
        self.cancel_event = threading.Event()
        self.process = None
        self.lock = threading.Lock()
        self.log_dir = Path(log_dir or Path.home() / '.videotrim' / 'logs')

    def cancel(self):
        self.cancel_event.set()
        with self.lock:
            process = self.process
            if process and process.poll() is None:
                try:
                    parent = psutil.Process(process.pid)
                    for child in parent.children(recursive=True):
                        try: child.kill()
                        except psutil.NoSuchProcess: pass
                    parent.kill()
                except psutil.NoSuchProcess:
                    pass

    def run(self, args, duration, progress=lambda *a: None):
        if self.cancel_event.is_set(): raise Cancelled('任务已取消')
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log = self.log_dir / f'{time.time_ns()}.log'
        command = [locate('ffmpeg'), '-hide_banner', '-nostdin', '-y', '-progress', 'pipe:1', '-nostats'] + args
        started = time.monotonic()
        with log.open('w', encoding='utf-8') as err:
            err.write(repr(command) + '\n'); err.flush()
            with self.lock:
                if self.cancel_event.is_set(): raise Cancelled('任务已取消')
                self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=err,
                    text=True, encoding='utf-8', errors='replace',
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                process = self.process
            for line in process.stdout:
                if line.startswith('out_time_us='):
                    try:
                        fraction = min(.999, max(0, int(line.split('=')[1]) / 1e6 / max(duration, .001)))
                        elapsed = time.monotonic() - started
                        progress(fraction, elapsed * (1 / fraction - 1) if fraction > .01 else None)
                    except ValueError: pass
            code = process.wait()
        with self.lock: self.process = None
        if self.cancel_event.is_set(): raise Cancelled('任务已取消')
        if code:
            detail = log.read_text(encoding='utf-8')[-5000:]
            raise RuntimeError(f'FFmpeg 失败（{code}），日志：{log}\n{detail}')

    def transactional(self, output, sources, operation, overwrite=False):
        output = Path(output).resolve()
        if any(output == Path(p).resolve() or (output.exists() and Path(p).exists()
               and output.samefile(p)) for p in sources):
            raise ValueError('禁止覆盖源视频，请选择其他输出路径')
        if output.exists() and not overwrite: raise FileExistsError('输出文件已存在')
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.videotrim-', dir=output.parent) as folder:
            temporary = Path(folder) / 'output.mp4'
            operation(temporary, Path(folder))
            if self.cancel_event.is_set(): raise Cancelled('任务已取消')
            info = probe(temporary)
            if info.duration <= 0 or temporary.stat().st_size < 100:
                raise RuntimeError('输出验证失败')
            if overwrite: os.replace(temporary, output)
            elif os.name == 'nt': os.rename(temporary, output)
            else:
                os.link(temporary, output); temporary.unlink()
        return probe(output)

def available_encoders():
    available = []
    for encoder in ('libx264', 'libx265', 'h264_qsv', 'hevc_qsv', 'h264_nvenc', 'hevc_nvenc', 'h264_amf', 'hevc_amf'):
        result = subprocess.run([locate('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i',
            'color=s=128x128:r=25', '-frames:v', '1', '-c:v', encoder, '-f', 'null', '-'],
            capture_output=True, timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode == 0: available.append(encoder)
    return available
