import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow
from core.ffprobe_service import probe

def test_window_import_and_segment(media):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.imported(probe(media[0]))
    assert window.files.count() == 1
    default = __import__('pathlib').Path(window.output.text())
    assert default.parent == media[0].parent
    assert default.stem.startswith(media[0].stem + '_')
    assert default != media[0]
    custom = media[0].parent / 'custom-result.mp4'; window.output.setText(str(custom))
    window.imported(probe(media[1])); window.files.setCurrentRow(1)
    assert window.output.text() == str(custom)
    window.files.setCurrentRow(0)
    window.set_range(.2, 1.2); window.add_segment()
    assert window.segments.count() == 1
    assert window.options().encoder == 'libx264'
    window.encoder_worker.wait(60000)
    window.close()
    app.processEvents()

def test_real_adjacent_frame_decode(media):
    from gui.preview_worker import FrameWorker
    result = []; errors = []
    worker = FrameWorker(media[0], .4, 1)
    worker.ready.connect(lambda path, timestamp, image: result.append((timestamp, image)))
    worker.failed.connect(errors.append)
    worker.run()
    assert not errors
    assert abs(result[0][0] - .44) < .001
    assert not result[0][1].isNull()
    result.clear()
    worker = FrameWorker(media[0], .4, -1)
    worker.ready.connect(lambda path, timestamp, image: result.append((timestamp, image)))
    worker.failed.connect(errors.append)
    worker.run()
    assert abs(result[0][0] - .36) < .001

def test_gui_async_output(media, tmp_path):
    import time
    from core.ffprobe_service import probe
    app = QApplication.instance() or QApplication([])
    window = MainWindow(); window.imported(probe(media[0]))
    window.set_range(.24, 1.24); window.add_segment()
    output = tmp_path / 'gui-output.mp4'; window.output.setText(str(output))
    window.process()
    deadline = time.monotonic() + 15
    while window.task.isRunning() and time.monotonic() < deadline:
        app.processEvents(); time.sleep(.01)
    if window.task.isRunning(): window.task.cancel(); window.task.wait(5000)
    app.processEvents()
    assert output.exists()
    assert abs(probe(output).duration - 1) < .15
    assert window.begin.isEnabled()
    window.encoder_worker.wait(60000); window.close(); app.processEvents()
