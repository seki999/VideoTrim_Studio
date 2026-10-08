import os
import subprocess
import pytest
from core.ffprobe_service import locate
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

@pytest.fixture(autouse=True)
def isolate_gui_settings(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    import gui.main_window
    monkeypatch.setattr(gui.main_window, 'QSettings',
        lambda *args: QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat))

@pytest.fixture(scope='session')
def media(tmp_path_factory):
    try: ffmpeg = locate('ffmpeg'); locate('ffprobe')
    except FileNotFoundError: pytest.skip('需要真实 FFmpeg 和 FFprobe')
    root = tmp_path_factory.mktemp('真实 日本語 media')
    result = []
    for name, size, audio in [("中文 日本語 space ' & %.mp4", '320x240', True),
                              ('second.mp4', '320x240', True), ('silent.mp4', '640x360', False),
                              ('mono.mp4', '320x240', True)]:
        path = root / name
        args = [ffmpeg, '-v', 'error', '-y', '-f', 'lavfi', '-i', f'testsrc2=size={size}:rate=25']
        if audio: args += ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000']
        args += ['-t', '2', '-c:v', 'libx264', '-preset', 'ultrafast', '-g', '25', '-pix_fmt', 'yuv420p']
        if audio: args += ['-c:a', 'aac', '-ac', '1' if name == 'mono.mp4' else '2']
        args += [str(path)]
        subprocess.run(args, check=True, capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        result.append(path)
    return result
