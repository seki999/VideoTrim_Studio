from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit

def format_time(seconds):
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours:02}:{minutes:02}:{seconds:02}'

def parse_time(text):
    parts = text.split(':')
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError('时间格式应为 小时:分:秒，例如 01:23:45')
    hours, minutes, seconds = map(int, parts)
    if not 0 <= minutes <= 59 or not 0 <= seconds <= 59:
        raise ValueError('分和秒必须在 00–59 之间')
    return hours * 3600 + minutes * 60 + seconds

class TimeInput(QLineEdit):
    valueChanged = Signal(float)
    def __init__(self):
        super().__init__('00:00:00')
        self._seconds = 0
        self.setPlaceholderText('00:00:00')
        self.setToolTip('小时:分:秒，例如 01:23:45；小时可超过 24')
        self.editingFinished.connect(self.commit)

    def mousePressEvent(self, event):
        first_click = not self.hasFocus()
        super().mousePressEvent(event)
        if first_click: self.selectAll()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.selectAll()

    def is_valid(self):
        try: parse_time(self.text()); return True
        except ValueError: return False

    def commit(self):
        try: value = parse_time(self.text())
        except ValueError:
            self.setToolTip('格式不正确，请输入 小时:分:秒，例如 00:01:30（分、秒为 00–59）')
            return
        self.setValue(value)

    def value(self):
        # Read the pending valid text as well, for button clicks during editing.
        try: return parse_time(self.text())
        except ValueError: return self._seconds

    def setValue(self, seconds):
        self._seconds = max(0, int(seconds))
        self.setText(format_time(self._seconds))
        self.valueChanged.emit(float(self._seconds))
