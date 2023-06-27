import sys
import os
import pathlib
from qtpy import QtWidgets

from .. import MyMainWindow

CWD = pathlib.Path(os.path.abspath(__file__)).parent

def main():
    app = QtWidgets.QApplication(sys.argv)
    with open(CWD.parent / "data" / "style.qss", "r") as f: app.setStyleSheet(f.read())
    window = MyMainWindow()
    window.showMaximized()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()