from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget

class Timeline(QWidget):
    range_changed = Signal(float, float)
    seek = Signal(float)
    def __init__(self):
        super().__init__()
        self.duration = 1
        self.start = 0
        self.end = 1
        self.position = 0
        self.zoom = 1
        self.offset = 0
        self.handle = None
        self.setMinimumHeight(85)
        self.setToolTip('拖动两端手柄设置片段；点击定位；滚轮缩放；按住 Shift 滚轮平移')

    def x(self, seconds):
        return 16 + (seconds - self.offset) / (self.duration / self.zoom) * max(1, self.width() - 32)

    def seconds(self, x):
        return min(self.duration, max(0, self.offset + (x - 16) / max(1, self.width() - 32) * self.duration / self.zoom))

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#25334a'))
        p.fillRect(int(self.x(self.start)), 30, int(self.x(self.end) - self.x(self.start)), 30, QColor('#427bb3'))
        p.setPen(QColor('white'))
        for i in range(11):
            t = self.offset + i * self.duration / self.zoom / 10
            x = int(self.x(t))
            p.drawLine(x, 60, x, 66)
            p.drawText(x - 12, 80, f'{t:.1f}')
        for t in (self.start, self.end):
            p.fillRect(int(self.x(t)) - 4, 24, 8, 40, QColor('#ffc857'))
        p.setPen(QPen(QColor('#ff7070'), 2))
        p.drawLine(int(self.x(self.position)), 5, int(self.x(self.position)), 65)

    def mousePressEvent(self, event):
        x = event.position().x()
        if abs(x - self.x(self.start)) < 12: self.handle = 'start'
        elif abs(x - self.x(self.end)) < 12: self.handle = 'end'
        else: self.seek.emit(self.seconds(x))

    def mouseMoveEvent(self, event):
        value = self.seconds(event.position().x())
        if self.handle == 'start': self.start = min(value, self.end - .001)
        elif self.handle == 'end': self.end = max(value, self.start + .001)
        else: return
        self.range_changed.emit(self.start, self.end); self.update()

    def mouseReleaseEvent(self, event): self.handle = None

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.offset += (-1 if delta > 0 else 1) * self.duration / self.zoom / 10
        else:
            self.zoom = min(100, max(1, self.zoom * (1.3 if delta > 0 else 1 / 1.3)))
        self.offset = max(0, min(self.offset, self.duration - self.duration / self.zoom))
        self.update()
