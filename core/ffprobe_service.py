import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from models import MediaInfo

def locate(name):
    roots = [Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])),
             Path(sys.executable).parent]
    env = os.environ.get('VIDEOTRIM_FFMPEG_DIR')
    candidates = ([Path(env) / (name + '.exe')] if env else [])
    for root in roots:
        candidates.extend([root / 'assets' / 'ffmpeg' / (name + '.exe'), root / (name + '.exe')])
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if not found:
        raise FileNotFoundError(f'找不到 {name}，请安装 FFmpeg 8.x 并加入 PATH。')
    return found

def probe(path):
    path = Path(path).resolve()
    result = subprocess.run([locate('ffprobe'), '-v', 'error', '-show_streams',
                             '-show_format', '-show_data_hash', 'sha256', '-of', 'json', str(path)],
                            capture_output=True, encoding='utf-8', errors='replace',
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        raise RuntimeError(result.stderr)
    data = json.loads(result.stdout)
    video = next((s for s in data['streams'] if s['codec_type'] == 'video'
                  and not s.get('disposition', {}).get('attached_pic')), None)
    if not video:
        raise ValueError('文件没有可用视频流')
    n, d = video.get('avg_frame_rate', '0/1').split('/')
    return MediaInfo(path, float(data['format'].get('duration', video.get('duration', 0))),
                     video['width'], video['height'], float(n) / float(d or 1),
                     video['codec_name'], data['streams'], path.stat().st_size)
