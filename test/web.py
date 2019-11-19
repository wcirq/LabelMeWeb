import sys

from qtpy import QtWidgets, QtCore
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(QtWidgets.QMainWindow, self).__init__()
        self.setWindowTitle("打开网页例子")
        # 相当于初始化这个加载web的控件
        self.browser = QWebEngineView()
        # 加载外部页面，调用
        self.browser.load(QtCore.QUrl("http://www.baidu.com"))
        self.setCentraWidget(self.browser)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
