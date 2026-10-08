import pytest
from gui.time_input import format_time, parse_time, TimeInput

def test_time_format():
    assert format_time(5025) == '01:23:45'
    assert parse_time('01:23:45') == 5025
    assert format_time(360000) == '100:00:00'
    assert parse_time('100:00:00') == 360000
    assert format_time(1.999) == '00:00:01'
    with pytest.raises(ValueError): parse_time('00:60:00')
    with pytest.raises(ValueError): parse_time('00:00:01.250')

def test_time_widget():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    widget = TimeInput(); widget.setValue(5025)
    assert widget.text() == '01:23:45'
    widget.setText('100:00:01'); widget.commit()
    assert widget.value() == 360001

def test_keyboard_editing():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    app = QApplication.instance() or QApplication([])
    widget = TimeInput(); widget.show(); widget.setFocus(); app.processEvents()
    widget.selectAll(); QTest.keyClicks(widget, '00:01:30')
    QTest.keyClick(widget, Qt.Key.Key_Return)
    assert widget.text() == '00:01:30' and widget.value() == 90
    widget.selectAll(); QTest.keyClick(widget, Qt.Key.Key_Backspace)
    QTest.keyClicks(widget, '01:02:03'); QTest.keyClick(widget, Qt.Key.Key_Return)
    assert widget.value() == 3723
    widget.selectAll(); QTest.keyClicks(widget, '00:00:01.250')
    assert not widget.is_valid()
    widget.close()
