from pathlib import Path
from datetime import datetime
from dataclasses import replace
from PySide6.QtCore import Qt, QUrl, QSettings, QThread, Signal
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QListWidgetItem, QAbstractItemView, QFileDialog, QSplitter, QLabel,
    QDoubleSpinBox, QSpinBox, QComboBox, QCheckBox, QFormLayout, QProgressBar,
    QMessageBox, QLineEdit, QGroupBox, QScrollArea, QStackedWidget)
from models import Segment, OutputOptions
from core.ffprobe_service import probe
from core.ffmpeg_service import available_encoders
from core.merge_service import compatible
from core.task_manager import TaskManager, Job
from core.output_paths import default_output_path
from .timeline import Timeline
from .preview_worker import FrameWorker
from .time_input import TimeInput, format_time

EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.webm'}

class ImportWorker(QThread):
    loaded = Signal(object)
    failed = Signal(str)
    def __init__(self, paths):
        super().__init__(); self.paths = paths
    def run(self):
        for path in self.paths:
            if self.isInterruptionRequested(): break
            try: self.loaded.emit(probe(path))
            except Exception as exc: self.failed.emit(f'{path}: {exc}')

class EncoderWorker(QThread):
    loaded = Signal(object)
    def run(self):
        try: self.loaded.emit(available_encoders())
        except Exception: self.loaded.emit(['libx264', 'libx265'])

class FileList(QListWidget):
    files_dropped = Signal(object)
    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
        else: super().dragEnterEvent(event)
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
        else: super().dragMoveEvent(event)
    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self.files_dropped.emit([Path(u.toLocalFile()) for u in event.mimeData().urls()])
            event.acceptProposedAction()
        else: super().dropEvent(event)

def button(text, action):
    widget = QPushButton(text); widget.clicked.connect(action); return widget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('VideoTrim Studio'); self.resize(1450, 950)
        self.settings = QSettings('VideoTrim', 'Studio')
        self.infos = {}; self.importers = []; self.task = None; self.current = None; self.frame_worker = None
        self.frame_position = None
        root = QWidget(); self.setCentralWidget(root); layout = QVBoxLayout(root)
        top = QHBoxLayout(); layout.addLayout(top)
        top.addWidget(button('添加文件', self.add_files)); top.addWidget(button('添加文件夹', self.add_folder))
        top.addStretch(); self.theme = QCheckBox('深色主题'); top.addWidget(self.theme)
        self.theme.toggled.connect(self.set_theme)
        top.addWidget(button('关于 / 许可证', self.about))
        splitter = QSplitter(); layout.addWidget(splitter, 1)
        left = QWidget(); lv = QVBoxLayout(left)
        lv.addWidget(QLabel('源视频（拖动排序 / 拖入文件）'))
        self.files = FileList(); lv.addWidget(self.files)
        self.files.files_dropped.connect(self.import_paths)
        self.files.currentItemChanged.connect(self.select_file)
        lv.addWidget(button('移除选中文件', lambda: self.remove_items(self.files)))
        self.compatibility = QLabel(''); self.compatibility.setWordWrap(True); lv.addWidget(self.compatibility)
        splitter.addWidget(left)
        center = QWidget(); cv = QVBoxLayout(center)
        self.video = QVideoWidget(); self.video.setMinimumSize(400, 230)
        self.preview = QStackedWidget(); self.preview.addWidget(self.video)
        self.frame_image = QLabel(); self.frame_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.frame_image.setMinimumSize(400, 230); self.preview.addWidget(self.frame_image); cv.addWidget(self.preview, 1)
        self.player = QMediaPlayer(self); self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio); self.player.setVideoOutput(self.video)
        self.player.errorOccurred.connect(lambda error, text: self.statusBar().showMessage('预览错误：' + text))
        controls = QHBoxLayout(); cv.addLayout(controls)
        for text, action in [('播放', self.play), ('暂停', self.player.pause),
                             ('−5 秒', lambda: self.seek_relative(-5)), ('+5 秒', lambda: self.seek_relative(5)),
                             ('上一帧', lambda: self.frame(-1)), ('下一帧', lambda: self.frame(1))]:
            controls.addWidget(button(text, action))
        self.clock = QLabel('00:00:00'); cv.addWidget(self.clock)
        self.timeline = Timeline(); cv.addWidget(self.timeline)
        self.timeline.seek.connect(self.seek)
        self.timeline.range_changed.connect(self.set_range)
        self.player.positionChanged.connect(self.position_changed)
        ranges = QHBoxLayout(); cv.addLayout(ranges)
        self.start = TimeInput(); self.end = TimeInput()
        for label, spin in [('开始（时:分:秒）', self.start), ('结束（时:分:秒）', self.end)]:
            ranges.addWidget(QLabel(label)); ranges.addWidget(spin)
            spin.valueChanged.connect(self.range_changed)
        ranges.addWidget(button('添加片段', self.add_segment))
        markers = QHBoxLayout(); cv.addLayout(markers)
        markers.addWidget(button('当前位置设为开始', lambda: self.start.setValue(self.player.position() / 1000)))
        markers.addWidget(button('当前位置设为结束', lambda: self.end.setValue(self.player.position() / 1000)))
        cv.addWidget(QLabel('输出片段顺序（有片段时输出这些片段；否则输出全部源视频）'))
        self.segments = FileList(); self.segments.setMaximumHeight(170); cv.addWidget(self.segments)
        segment_buttons = QHBoxLayout(); cv.addLayout(segment_buttons)
        segment_buttons.addWidget(button('删除片段', lambda: self.remove_items(self.segments)))
        segment_buttons.addWidget(button('更新选中片段时间', self.update_segment))
        self.segments.currentItemChanged.connect(self.select_segment)
        splitter.addWidget(center)
        panel = QWidget(); form = QFormLayout(panel)
        self.mode = QComboBox()
        for label, value in [('极速无损 / 原始流复制', 'copy'), ('高画质 CRF 18', '18'),
            ('均衡 CRF 23', '23'), ('小体积 CRF 28', '28'), ('自定义 CRF', 'crf'),
            ('目标码率', 'bitrate'), ('目标大小（估算）', 'size')]: self.mode.addItem(label, value)
        self.mode.setCurrentIndex(2); form.addRow('剪切 / 压缩模式', self.mode)
        hint = QLabel('精确模式会重新编码。极速模式受关键帧限制，不能保证逐帧精确。\n不兼容的输入会自动重新编码。压缩可能损失画质，也可能增大文件。')
        hint.setWordWrap(True); form.addRow(hint)
        self.encoder = QComboBox(); self.encoder.addItems(['libx264', 'libx265']); form.addRow('编码器', self.encoder)
        self.crf = QSpinBox(); self.crf.setRange(0, 51); self.crf.setValue(23); form.addRow('自定义 CRF', self.crf)
        self.bitrate = QSpinBox(); self.bitrate.setRange(50, 200000); self.bitrate.setValue(2000); form.addRow('视频码率 kbps', self.bitrate)
        self.target = QDoubleSpinBox(); self.target.setRange(.1, 1e7); self.target.setValue(20); form.addRow('目标大小 MiB', self.target)
        self.two_pass = QCheckBox('libx264 码率 / 大小模式'); form.addRow('双遍编码', self.two_pass)
        self.resolution = QComboBox(); self.resolution.addItems(['保持原始', '1080p', '720p', '480p', '自定义']); form.addRow('输出分辨率', self.resolution)
        self.width = QSpinBox(); self.height = QSpinBox()
        for spin, value in [(self.width, 1920), (self.height, 1080)]: spin.setRange(2, 16384); spin.setValue(value)
        form.addRow('自定义宽', self.width); form.addRow('自定义高', self.height)
        self.pad = QCheckBox('保持比例并填充黑边'); self.pad.setChecked(True); form.addRow(self.pad)
        self.fps = QDoubleSpinBox(); self.fps.setRange(0, 240); self.fps.setValue(0); self.fps.setSpecialValueText('保持原始'); form.addRow('帧率', self.fps)
        self.suggested_output = ''
        self.output = QLineEdit(); self.output.setPlaceholderText('导入视频后自动生成同目录输出文件名')
        form.addRow('输出 MP4', self.output)
        form.addRow(button('选择输出位置', self.choose_output))
        self.batch = QCheckBox('每个源文件单独输出（忽略片段列表）'); form.addRow(self.batch)
        self.queue_label = QLabel(''); self.queue_label.setWordWrap(True); form.addRow(self.queue_label)
        scroll = QScrollArea(); scroll.setWidget(panel); scroll.setWidgetResizable(True); splitter.addWidget(scroll)
        splitter.setSizes([270, 770, 360])
        bottom = QHBoxLayout(); layout.addLayout(bottom)
        self.begin = button('开始处理', self.process); bottom.addWidget(self.begin)
        self.stop = button('停止', self.cancel); self.stop.setEnabled(False); bottom.addWidget(self.stop)
        self.progress = QProgressBar(); bottom.addWidget(self.progress, 1)
        self.eta = QLabel('等待任务'); bottom.addWidget(self.eta)
        self.encoder_worker = EncoderWorker(self)
        self.encoder_worker.loaded.connect(self.encoders_loaded); self.encoder_worker.start()
        self.mode.setCurrentIndex(int(self.settings.value('mode', 2)))
        self.saved_controls = [('crf', self.crf), ('bitrate', self.bitrate), ('target', self.target),
                               ('width', self.width), ('height', self.height), ('fps', self.fps)]
        for name, control in self.saved_controls:
            value = self.settings.value(name)
            if value is not None: control.setValue(float(value) if isinstance(control, QDoubleSpinBox) else int(value))
        self.resolution.setCurrentIndex(int(self.settings.value('resolution', 0)))
        self.pad.setChecked(self.settings.value('pad', True, type=bool))
        self.theme.setChecked(self.settings.value('dark', True, type=bool)); self.set_theme(self.theme.isChecked())

    def encoders_loaded(self, encoders):
        selected = self.encoder.currentText(); self.encoder.clear(); self.encoder.addItems(encoders)
        self.encoder.setCurrentText(selected)
        saved = self.settings.value('encoder', selected)
        if saved in encoders: self.encoder.setCurrentText(saved)
        self.statusBar().showMessage('编码器实际试编码检测完成：' + ', '.join(encoders))

    def set_theme(self, dark):
        self.setStyleSheet(('QWidget {background:#182234;color:#f0f3fa;} QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox,QListWidget {background:#26364d;} QPushButton {background:#345477;} ' if dark else '') +
            'QWidget {font-size:15px;} QPushButton {padding:8px;border-radius:4px;} QProgressBar {min-height:22px;}')

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '添加视频', '', '视频 (*.mp4 *.mov *.mkv *.avi *.webm)')
        self.import_paths([Path(p) for p in paths])

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '添加文件夹')
        if folder: self.import_paths(sorted(Path(folder).iterdir()))

    def import_paths(self, paths):
        expanded = []
        for p in paths:
            if p.is_dir(): expanded.extend(sorted(p.iterdir()))
            else: expanded.append(p)
        paths = [p.resolve() for p in expanded if p.suffix.lower() in EXTENSIONS and p.is_file()]
        worker = ImportWorker(paths); self.importers.append(worker)
        worker.loaded.connect(self.imported); worker.failed.connect(lambda msg: self.statusBar().showMessage(msg))
        worker.finished.connect(lambda: self.import_finished(worker)); worker.start()

    def import_finished(self, worker):
        self.importers.remove(worker); worker.deleteLater()

    def imported(self, info):
        if any(self.files.item(i).data(Qt.ItemDataRole.UserRole) == info.path for i in range(self.files.count())): return
        self.infos[info.path] = info
        item = QListWidgetItem(f'{info.path.name}\n{info.width}×{info.height} | {info.fps:.3f} fps | {info.codec}\n{info.duration:.3f} 秒 | {info.size / 1024**2:.2f} MiB | ' + ('有音轨' if info.audio else '无音轨'))
        item.setData(Qt.ItemDataRole.UserRole, info.path); item.setToolTip(str(info.path)); self.files.addItem(item)
        if self.files.count() == 1: self.files.setCurrentItem(item)
        infos = [self.infos[self.files.item(i).data(Qt.ItemDataRole.UserRole)] for i in range(self.files.count())]
        self.compatibility.setText('视频流兼容，可尝试无损合并' if compatible(infos) else '视频流不兼容，将标准化后重新编码')

    def select_file(self, item, previous=None):
        if item: self.load_media(item.data(Qt.ItemDataRole.UserRole))

    def load_media(self, path):
        self.suggest_output(path)
        self.preview.setCurrentIndex(0); self.frame_position = None
        self.current = self.infos[path]; self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.timeline.duration = self.current.duration; self.timeline.zoom = 1; self.timeline.offset = 0
        self.set_range(0, self.current.duration)

    def automatic_output(self):
        return not self.output.text().strip() or self.output.text() == self.suggested_output

    def suggest_output(self, source):
        if self.automatic_output():
            self.suggested_output = str(default_output_path(source))
            self.output.setText(self.suggested_output)

    def set_range(self, start, end):
        self.start.blockSignals(True); self.end.blockSignals(True)
        self.start.setValue(start); self.end.setValue(end)
        self.start.blockSignals(False); self.end.blockSignals(False); self.range_changed()

    def range_changed(self):
        self.timeline.start = self.start.value(); self.timeline.end = self.end.value(); self.timeline.update()

    def position_changed(self, milliseconds):
        self.timeline.position = milliseconds / 1000; self.timeline.update()
        self.clock.setText(format_time(milliseconds / 1000))

    def play(self):
        if self.frame_worker: self.frame_worker.requestInterruption()
        self.preview.setCurrentIndex(0); self.frame_position = None; self.player.play()

    def seek(self, seconds):
        if self.frame_worker: self.frame_worker.requestInterruption()
        self.preview.setCurrentIndex(0); self.frame_position = None
        self.player.setPosition(round(seconds * 1000))

    def seek_relative(self, seconds): self.seek(max(0, self.player.position() / 1000 + seconds))

    def frame(self, direction):
        self.player.pause()
        if not self.current or (self.frame_worker and self.frame_worker.isRunning()): return
        position = self.frame_position if self.frame_position is not None else self.player.position() / 1000
        self.frame_worker = FrameWorker(self.current.path, position, direction)
        self.frame_worker.ready.connect(self.show_frame)
        self.frame_worker.failed.connect(lambda text: self.statusBar().showMessage('逐帧解码：' + text))
        self.frame_worker.start()

    def show_frame(self, path, timestamp, image):
        if self.frame_worker and self.frame_worker.isInterruptionRequested(): return
        if not self.current or self.current.path != path: return
        self.frame_position = timestamp; self.player.setPosition(round(timestamp * 1000))
        self.frame_image.setPixmap(QPixmap.fromImage(image).scaled(self.preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.preview.setCurrentIndex(1); self.position_changed(round(timestamp * 1000))

    def add_segment(self):
        if not self.current: return
        if not self.start.is_valid() or not self.end.is_valid():
            QMessageBox.warning(self, '时间格式', '请输入 小时:分:秒，例如 00:01:30'); return
        if not 0 <= self.start.value() < self.end.value() <= self.current.duration + .001:
            QMessageBox.warning(self, '时间范围', '请设置有效的开始与结束时间'); return
        s = Segment(self.current.path, self.start.value(), self.end.value())
        item = QListWidgetItem(); item.setData(Qt.ItemDataRole.UserRole, s)
        item.setText(f'{s.path.name}  [{format_time(s.start)} → {format_time(s.end)}]'); self.segments.addItem(item)

    def select_segment(self, item, previous=None):
        if item:
            s = item.data(Qt.ItemDataRole.UserRole); self.load_media(s.path); self.set_range(s.start, s.end)

    def update_segment(self):
        item = self.segments.currentItem()
        if item and self.current:
            if not self.start.is_valid() or not self.end.is_valid():
                QMessageBox.warning(self, '时间格式', '请输入 小时:分:秒，例如 00:01:30'); return
            if not 0 <= self.start.value() < self.end.value() <= self.current.duration + .001:
                QMessageBox.warning(self, '时间范围', '请设置有效的开始与结束时间'); return
            s = Segment(self.current.path, self.start.value(), self.end.value())
            item.setData(Qt.ItemDataRole.UserRole, s); item.setText(f'{s.path.name}  [{format_time(s.start)} → {format_time(s.end)}]')

    def remove_items(self, listing):
        for item in listing.selectedItems(): listing.takeItem(listing.row(item))

    def choose_output(self):
        path, _ = QFileDialog.getSaveFileName(self, '输出文件', self.output.text(), 'MP4 (*.mp4)')
        if path: self.output.setText(path if path.lower().endswith('.mp4') else path + '.mp4')

    def options(self):
        mode = self.mode.currentData(); crf = int(mode) if mode in ('18', '23', '28') else self.crf.value()
        resolution = self.resolution.currentText()
        sizes = {'1080p': (1920, 1080), '720p': (1280, 720), '480p': (854, 480), '自定义': (self.width.value(), self.height.value())}
        w, h = sizes.get(resolution, (None, None))
        return OutputOptions(mode='crf' if mode in ('18', '23', '28') else mode,
            encoder=self.encoder.currentText(), crf=crf, bitrate_kbps=self.bitrate.value(),
            target_mb=self.target.value(), two_pass=self.two_pass.isChecked(), width=w, height=h,
            fps=self.fps.value() or None, pad=self.pad.isChecked())

    def process(self):
        paths = [self.files.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.files.count())]
        if not paths:
            QMessageBox.warning(self, '缺少输入', '请添加视频'); return
        segments = [self.segments.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.segments.count())]
        automatic = self.automatic_output()
        self.suggest_output(segments[0].path if segments and not self.batch.isChecked() else paths[0])
        output = Path(self.output.text()).expanduser().resolve()
        if output.suffix.lower() != '.mp4':
            QMessageBox.warning(self, '输出格式', '输出文件必须使用 .mp4 扩展名'); return
        options = self.options()
        jobs = [Job(segments or [Segment(p) for p in paths], output, options)]
        if self.batch.isChecked():
            jobs = []
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            for path in paths:
                destination = default_output_path(path, directory=None if automatic else output.parent,
                                                  timestamp=timestamp, reserved=[j.output for j in jobs])
                jobs.append(Job([Segment(path)], destination, replace(options)))
        if any(j.output in self.infos for j in jobs):
            QMessageBox.warning(self, '源文件保护', '不能覆盖任何导入的源视频'); return
        existing = [str(j.output) for j in jobs if j.output.exists()]
        if existing:
            if QMessageBox.question(self, '覆盖输出文件', '以下输出已存在，是否覆盖？\n' + '\n'.join(existing)) != QMessageBox.StandardButton.Yes: return
            for job in jobs: job.overwrite = job.output.exists()
        self.task = TaskManager(jobs, self); self.task.progress.connect(self.on_progress)
        self.task.completed.connect(self.on_complete); self.task.failed.connect(self.on_failed)
        self.task.finished.connect(self.on_finished)
        self.begin.setEnabled(False); self.stop.setEnabled(True); self.progress.setValue(0)
        self.queue_label.setText(f'队列：{len(jobs)} 个任务'); self.task.start()

    def on_progress(self, index, p, eta):
        self.progress.setValue(round((index + p) / len(self.task.jobs) * 100))
        self.eta.setText(f'任务 {index+1}/{len(self.task.jobs)} · 剩余 {eta:.0f} 秒' if eta is not None else '估算中…')

    def on_complete(self, index, info):
        job = self.task.jobs[index]
        source = sum(self.infos[s.path].size * ((s.end or self.infos[s.path].duration) - s.start) / self.infos[s.path].duration for s in job.segments)
        saved = source - info.size
        self.queue_label.setText(f'输出：{info.path}\n大小 {info.size/1024**2:.2f} MiB；节省 {saved/1024**2:.2f} MiB；输出/源大小 {info.size/source:.1%}\n片段源大小按时长估算。')

    def on_failed(self, index, message):
        self.queue_label.setText(f'任务 {index+1}：{message}')
        if message != '任务已取消': QMessageBox.warning(self, '处理失败', message)

    def on_finished(self):
        self.begin.setEnabled(True); self.stop.setEnabled(False); self.eta.setText('队列已结束')

    def cancel(self):
        if self.task: self.task.cancel()

    def about(self):
        QMessageBox.information(self, '关于 VideoTrim Studio', '完全本地的视频工具。\n使用 PySide6 / Qt（LGPLv3 / GPLv3 / 商业许可）和外部 FFmpeg / FFprobe。\nFFmpeg 许可证取决于构建配置，含 libx264/libx265 的构建通常适用 GPL。\n详细再分发义务见 README 和随包许可证。')

    def closeEvent(self, event):
        if self.frame_worker and self.frame_worker.isRunning():
            self.frame_worker.requestInterruption()
            if not self.frame_worker.wait(1000): event.ignore(); return
        if self.task and self.task.isRunning():
            self.task.cancel()
            if not self.task.wait(5000): event.ignore(); return
        for worker in list(self.importers):
            worker.requestInterruption()
            if not worker.wait(5000): event.ignore(); return
        if self.encoder_worker.isRunning() and not self.encoder_worker.wait(1000):
            self.statusBar().showMessage('正在完成编码器检测，请稍后关闭'); event.ignore(); return
        self.player.stop(); self.settings.setValue('dark', self.theme.isChecked()); self.settings.setValue('mode', self.mode.currentIndex())
        for name, control in self.saved_controls: self.settings.setValue(name, control.value())
        self.settings.setValue('encoder', self.encoder.currentText())
        self.settings.setValue('resolution', self.resolution.currentIndex()); self.settings.setValue('pad', self.pad.isChecked())
        super().closeEvent(event)
