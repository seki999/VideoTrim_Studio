from pathlib import Path
import pytest
from models import Segment, OutputOptions
from core.ffmpeg_service import FFmpegService
from core.merge_service import process_segments

def test_bad_segment_bounds(media, tmp_path):
    for start, end in [(-1, 1), (1, 0), (0, 3)]:
        with pytest.raises(ValueError):
            process_segments(FFmpegService(), [Segment(media[0], start, end)], tmp_path / 'bad.mp4')

def test_copy_transform_rejected(media, tmp_path):
    with pytest.raises(ValueError, match='流复制'):
        process_segments(FFmpegService(), [Segment(media[0])], tmp_path / 'bad.mp4', OutputOptions(mode='copy', fps=30))

def test_hardlink_source_protected(media, tmp_path):
    alias = tmp_path / 'alias.mp4'
    try: alias.hardlink_to(media[0])
    except OSError: pytest.skip('文件系统不支持此硬链接')
    with pytest.raises(ValueError, match='源视频'):
        process_segments(FFmpegService(), [Segment(media[0])], alias, overwrite=True)

def test_gui_reimport_removed(media):
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow
    from core.ffprobe_service import probe
    app = QApplication.instance() or QApplication([])
    window = MainWindow(); info = probe(media[0]); window.imported(info)
    window.files.takeItem(0); window.imported(info)
    assert window.files.count() == 1
    window.encoder_worker.wait(60000); window.close(); app.processEvents()
