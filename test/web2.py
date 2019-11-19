import sys
import time

from PyQt5 import QtCore, QtGui
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import QApplication

app = QApplication(sys.argv)
ui = QWebEngineView()


class global_var:
    pagename = ""


def load_baidu():
    global_var.pagename = "baidu"
    print("load baidu")
    ui.load(QUrl("http://127.0.0.1:80/"))


def load_oschina():
    global_var.pagename = "oschina"
    print("load oschina")
    ui.load(QUrl("https://www.oschina.net/"))


def onStart():
    print("Started...")


def onDone():
    print("load ok---", global_var.pagename)


ui.loadStarted.connect(onStart)
ui.loadFinished.connect(onDone)

load_baidu()
# time.sleep(5)
# load_oschina()

ui.showMaximized()
sys.exit(app.exec_())
