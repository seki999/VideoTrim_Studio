import sys
from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('VideoTrim Studio')
    window = MainWindow(); window.show()
    return app.exec()

if __name__ == '__main__':
    sys.exit(main())
