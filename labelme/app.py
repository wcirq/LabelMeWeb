import functools
import json
import os
import os.path as osp
import pickle
import re
import time
import webbrowser

import cv2
import numpy as np

from qtpy import QtCore
from qtpy.QtCore import Qt, QModelIndex
from qtpy import QtGui
from qtpy import QtWidgets

from labelme import __appname__
from labelme import PY2
from labelme import QT5
from labelme.network import post, URL

from . import utils
from labelme.config import get_config
from labelme.label_file import LabelFile
from labelme.label_file import LabelFileError
from labelme.logger import logger
from labelme.shape import DEFAULT_FILL_COLOR
from labelme.shape import DEFAULT_LINE_COLOR
from labelme.shape import Shape
from labelme.widgets import Canvas
from labelme.widgets import ColorDialog
from labelme.widgets import EscapableQListWidget
from labelme.widgets import LabelDialog
from labelme.widgets import LabelQListWidget
from labelme.widgets import ToolBar
from labelme.widgets import ZoomWidget


# FIXME
# - [medium] Set max zoom value to something big enough for FitWidth/Window

# TODO(unknown):
# - [high] Add polygon movement with arrow keys
# - [high] Deselect shape when clicking and already selected(?)
# - [low,maybe] Open images with drag & drop.
# - [low,maybe] Preview images on file dialogs.
# - Zoom is too "steppy".


class MainWindow(QtWidgets.QMainWindow):
    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = 0, 1, 2

    def __init__(
            self,
            config=None,
            filename=None,
            output=None,
            output_file=None,
            output_dir=None,
    ):
        if output is not None:
            logger.warning(
                'argument output is deprecated, use output_file instead'
            )
            if output_file is None:
                output_file = output

        # see labelme/config/default_config.yaml for valid configuration
        if config is None:
            config = get_config()
        self._config = config

        super(MainWindow, self).__init__()
        self.setWindowTitle(__appname__)

        # Whether we need to save or not.
        self.dirty = False

        self._noSelectionSlot = False

        # Main widgets and related state.
        self.labelDialog = LabelDialog(
            parent=self,
            labels=self._config['labels'],
            sort_labels=self._config['sort_labels'],
            show_text_field=self._config['show_label_text_field'],
            completion=self._config['label_completion'],
            fit_to_content=self._config['fit_to_content'],
        )

        self.labelList = LabelQListWidget()
        self.lastOpenDir = None

        self.expand_widget = QtWidgets.QLabel(self)
        self.expand_widget.setText("??????????????????")
        self.expand_widget.setFixedSize(200, 200)
        self.expand_widget.move(160, 160)

        self.expand_dock = QtWidgets.QDockWidget('?????????', self)
        self.expand_dock.setObjectName('Flags')
        self.expand_dock.setWidget(self.expand_widget)

        self.flag_dock = self.flag_widget = None
        self.flag_dock = QtWidgets.QDockWidget('??????', self)
        self.flag_dock.setObjectName('Flags')
        self.flag_widget = QtWidgets.QListWidget()
        if config['flags']:
            self.loadFlags({k: False for k in config['flags']})
        self.flag_dock.setWidget(self.flag_widget)
        self.flag_widget.itemChanged.connect(self.setDirty)

        self.labelList.itemActivated.connect(self.labelSelectionChanged)
        self.labelList.itemSelectionChanged.connect(self.labelSelectionChanged)
        self.labelList.itemDoubleClicked.connect(self.editLabel)
        # Connect to itemChanged to detect checkbox changes.
        self.labelList.itemChanged.connect(self.labelItemChanged)
        self.labelList.setDragDropMode(
            QtWidgets.QAbstractItemView.InternalMove)
        self.labelList.setParent(self)
        self.shape_dock = QtWidgets.QDockWidget('????????????', self)
        self.shape_dock.setObjectName('Labels')
        self.shape_dock.setWidget(self.labelList)

        self.uniqLabelList = EscapableQListWidget()
        self.uniqLabelList.setToolTip(
            "Select label to start annotating for it. "
            "Press 'Esc' to deselect.")
        if self._config['labels']:
            # self.uniqLabelList.addItems(self._config['labels'])
            # self.uniqLabelList.addItems(['pen', 'hand', 'form'])
            self.uniqLabelList.sortItems()
        self.label_dock = QtWidgets.QDockWidget(u'????????????', self)
        self.label_dock.setObjectName(u'Label List')
        self.label_dock.setWidget(self.uniqLabelList)

        self.fileSearch = QtWidgets.QLineEdit()
        self.fileSearch.setPlaceholderText('???????????????')
        self.fileSearch.textChanged.connect(self.fileSearchChanged)
        self.fileListWidget = QtWidgets.QListWidget()
        self.fileListWidget.itemSelectionChanged.connect(
            self.fileSelectionChanged
        )
        fileListLayout = QtWidgets.QVBoxLayout()
        fileListLayout.setContentsMargins(0, 0, 0, 0)
        fileListLayout.setSpacing(0)
        fileListLayout.addWidget(self.fileSearch)
        fileListLayout.addWidget(self.fileListWidget)
        self.file_dock = QtWidgets.QDockWidget(u'????????????', self)
        self.file_dock.setObjectName(u'Files')
        fileListWidget = QtWidgets.QWidget()
        fileListWidget.setLayout(fileListLayout)
        self.file_dock.setWidget(fileListWidget)

        self.zoomWidget = ZoomWidget()
        self.colorDialog = ColorDialog(parent=self)

        self.canvas = self.labelList.canvas = Canvas(callback=self.mouseMoveEvent, epsilon=self._config['epsilon'])
        self.canvas.zoomRequest.connect(self.zoomRequest)

        scrollArea = QtWidgets.QScrollArea()
        scrollArea.setWidget(self.canvas)
        scrollArea.setWidgetResizable(True)
        self.scrollBars = {
            Qt.Vertical: scrollArea.verticalScrollBar(),
            Qt.Horizontal: scrollArea.horizontalScrollBar(),
        }
        self.canvas.scrollRequest.connect(self.scrollRequest)

        self.canvas.newShape.connect(self.newShape)
        self.canvas.shapeMoved.connect(self.setDirty)
        self.canvas.selectionChanged.connect(self.shapeSelectionChanged)
        self.canvas.drawingPolygon.connect(self.toggleDrawingSensitive)

        self.setCentralWidget(scrollArea)

        features = QtWidgets.QDockWidget.DockWidgetFeatures()
        for dock in ['flag_dock', 'label_dock', 'shape_dock', 'file_dock']:
            if self._config[dock]['closable']:
                features = features | QtWidgets.QDockWidget.DockWidgetClosable
            if self._config[dock]['floatable']:
                features = features | QtWidgets.QDockWidget.DockWidgetFloatable
            if self._config[dock]['movable']:
                features = features | QtWidgets.QDockWidget.DockWidgetMovable
            getattr(self, dock).setFeatures(features)
            if self._config[dock]['show'] is False:
                getattr(self, dock).setVisible(False)

        self.addDockWidget(Qt.RightDockWidgetArea, self.flag_dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.label_dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.shape_dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.file_dock)

        # Actions
        action = functools.partial(utils.newAction, self)
        shortcuts = self._config['shortcuts']
        quit = action('&??????', self.close, shortcuts['quit'], 'quit',
                      '????????????')
        # open_ = action('&??????', self.openFile, shortcuts['open'], 'open',
        #                '???????????????????????????')
        # opendir = action('&???????????????', self.openDirDialog,
        #                  shortcuts['open_dir'], 'open', u'???????????????')
        openNextImg = action(
            '&?????????',
            self.openNextImg,
            shortcuts['open_next'],
            'next',
            u'???????????????(??????Ctl+Shift???????????????)',
            enabled=False,
        )
        openPrevImg = action(
            '&?????????',
            self.openPrevImg,
            shortcuts['open_prev'],
            'prev',
            u'???????????????(??????Ctl+Shift???????????????)',
            enabled=False,
        )
        save = action('&??????', self.saveFileByWeb, shortcuts['save'], 'save',
                      '?????????????????????', enabled=False)
        saveAs = action('&?????????', self.saveFileAs, shortcuts['save_as'],
                        'save-as', '??????????????????????????????',
                        enabled=False)

        deleteFile = action(
            '&????????????',
            self.deleteFile,
            shortcuts['delete_file'],
            'delete',
            '????????????????????????',
            enabled=False)

        ignoreImageButton = action(
            '&????????????',
            self.ignoreImage,
            shortcuts['ignoreImage'],
            'open',
            '???????????????????????????',
            checkable=True,
            enabled=True)

        changeOutputDir = action(
            '&????????????',
            slot=self.changeOutputDirDialog,
            shortcut=shortcuts['save_to'],
            icon='open',
            tip=u'????????????/?????????????????????'
        )

        saveAuto = action(
            text='????????????',
            slot=lambda x: self.actions.saveAuto.setChecked(x),
            icon='save',
            tip='????????????',
            checkable=True,
            enabled=True,
        )
        saveAuto.setChecked(self._config['auto_save'])

        close = action('&??????', self.closeFile, shortcuts['close'], 'close',
                       '??????????????????')
        color1 = action('????????????', self.chooseColor1,
                        shortcuts['edit_line_color'], 'color_line',
                        '???????????????????????????')
        color2 = action('????????????', self.chooseColor2,
                        shortcuts['edit_fill_color'], 'color',
                        '???????????????????????????')

        toggle_keep_prev_mode = action(
            '??????????????????',
            self.toggleKeepPrevMode,
            shortcuts['toggle_keep_prev_mode'], None,
            '??????????????????????????????',
            checkable=True)
        toggle_keep_prev_mode.setChecked(self._config['keep_prev'])

        createMode = action(
            '?????????',
            lambda: self.toggleDrawMode(False, createMode='polygon'),
            shortcuts['create_polygon'],
            'objects',
            '?????????????????????',
            enabled=False,
        )
        createRectangleMode = action(
            '??????',
            lambda: self.toggleDrawMode(False, createMode='rectangle'),
            shortcuts['create_rectangle'],
            'objects',
            '??????????????????',
            enabled=False,
        )
        createCircleMode = action(
            '??????',
            lambda: self.toggleDrawMode(False, createMode='circle'),
            shortcuts['create_circle'],
            'objects',
            '??????????????????',
            enabled=False,
        )
        createLineMode = action(
            '??????',
            lambda: self.toggleDrawMode(False, createMode='line'),
            shortcuts['create_line'],
            'objects',
            '??????????????????',
            enabled=False,
        )
        createPointMode = action(
            '??????',
            lambda: self.toggleDrawMode(False, createMode='point'),
            shortcuts['create_point'],
            'objects',
            '???????????????',
            enabled=False,
        )
        createLineStripMode = action(
            '??????',
            lambda: self.toggleDrawMode(False, createMode='linestrip'),
            shortcuts['create_linestrip'],
            'objects',
            '???????????????. ??? Ctrl+?????? ??????.',
            enabled=False,
        )
        editMode = action('??????', self.setEditMode,
                          shortcuts['edit_polygon'], 'edit',
                          '?????????????????????', enabled=False)

        delete = action('??????', self.deleteSelectedShape,
                        shortcuts['delete_polygon'], 'cancel',
                        '??????', enabled=False)
        copy = action('??????', self.copySelectedShape,
                      shortcuts['duplicate_polygon'], 'copy',
                      '??????????????????????????????',
                      enabled=False)
        undoLastPoint = action('??????????????????', self.canvas.undoLastPoint,
                               shortcuts['undo_last_point'], 'undo',
                               '????????????????????????', enabled=False)

        deletePoint = action('?????????', self.canvas.deletePoint,
                             None, 'edit', '????????????',
                             enabled=False)

        addDisVisiblePoint = action('??????????????????', self.canvas.addDisVisiblePoint,
                                    None, 'edit', '??????????????????????????????',
                                    enabled=False)

        addVisiblePoint = action('???????????????', self.canvas.addVisiblePoint,
                                 None, 'edit', '??????????????????????????????',
                                 enabled=False)

        undo = action('??????', self.undoShapeEdit, shortcuts['undo'], 'undo',
                      '?????????????????????????????????', enabled=False)

        hideAll = action('&??????\n??????',
                         functools.partial(self.togglePolygons, False),
                         icon='eye', tip='?????????????????????', enabled=False)
        showAll = action('&??????\n??????',
                         functools.partial(self.togglePolygons, True),
                         icon='eye', tip='?????????????????????', enabled=False)

        help = action('&??????', self.tutorial, icon='help',
                      tip='????????????')

        zoom = QtWidgets.QWidgetAction(self)
        zoom.setDefaultWidget(self.zoomWidget)
        self.zoomWidget.setWhatsThis(
            'Zoom in or out of the image. Also accessible with '
            '{} and {} from the canvas.'
                .format(
                utils.fmtShortcut(
                    '{},{}'.format(
                        shortcuts['zoom_in'], shortcuts['zoom_out']
                    )
                ),
                utils.fmtShortcut("Ctrl+Wheel"),
            )
        )
        self.zoomWidget.setEnabled(False)

        zoomIn = action('&??????', functools.partial(self.addZoom, 10),
                        shortcuts['zoom_in'], 'zoom-in',
                        '??????????????????', enabled=False)
        zoomOut = action('&??????', functools.partial(self.addZoom, -10),
                         shortcuts['zoom_out'], 'zoom-out',
                         '??????????????????', enabled=False)
        zoomOrg = action('&????????????',
                         functools.partial(self.setZoom, 100),
                         shortcuts['zoom_to_original'], 'zoom',
                         '?????????????????????', enabled=False)
        fitWindow = action('&????????????', self.setFitWindow,
                           shortcuts['fit_window'], 'fit-window',
                           '????????????????????????', checkable=True,
                           enabled=False)
        fitWidth = action('????????????', self.setFitWidth,
                          shortcuts['fit_width'], 'fit-width',
                          '????????????????????????',
                          checkable=True, enabled=False)
        # Group zoom controls into a list for easier toggling.
        zoomActions = (self.zoomWidget, zoomIn, zoomOut, zoomOrg,
                       fitWindow, fitWidth)
        self.zoomMode = self.FIT_WINDOW
        fitWindow.setChecked(Qt.Checked)
        self.scalers = {
            self.FIT_WINDOW: self.scaleFitWindow,
            self.FIT_WIDTH: self.scaleFitWidth,
            # Set to one to scale to 100% when loading files.
            self.MANUAL_ZOOM: lambda: 1,
        }

        edit = action('&????????????', self.editLabel, shortcuts['edit_label'],
                      'edit', '??????????????????????????????',
                      enabled=False)

        shapeLineColor = action(
            '????????????', self.chshapeLineColor, icon='color-line',
            tip='Change the line color for this specific shape', enabled=False)
        shapeFillColor = action(
            '????????????', self.chshapeFillColor, icon='color',
            tip='Change the fill color for this specific shape', enabled=False)
        fill_drawing = action(
            '????????????',
            lambda x: self.canvas.setFillDrawing(x),
            None,
            'color',
            '????????????????????????',
            checkable=True,
            enabled=True,
        )
        fill_drawing.setChecked(True)

        # Lavel list context menu.
        labelMenu = QtWidgets.QMenu()
        utils.addActions(labelMenu, (edit, delete))
        self.labelList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.labelList.customContextMenuRequested.connect(
            self.popLabelListMenu)

        # Store actions for further handling.
        self.actions = utils.struct(
            ignoreImageButton=ignoreImageButton,
            saveAuto=saveAuto,
            save=save, close=close,
            deleteFile=deleteFile,
            lineColor=color1, fillColor=color2,
            toggleKeepPrevMode=toggle_keep_prev_mode,
            delete=delete, edit=edit, copy=copy,
            undoLastPoint=undoLastPoint, undo=undo,
            deletePoint=deletePoint,
            addDisVisiblePoint=addDisVisiblePoint,
            addVisiblePoint=addVisiblePoint,
            createMode=createMode, editMode=editMode,
            createRectangleMode=createRectangleMode,
            createCircleMode=createCircleMode,
            createLineMode=createLineMode,
            createPointMode=createPointMode,
            createLineStripMode=createLineStripMode,
            shapeLineColor=shapeLineColor, shapeFillColor=shapeFillColor,
            zoom=zoom, zoomIn=zoomIn, zoomOut=zoomOut, zoomOrg=zoomOrg,
            fitWindow=fitWindow, fitWidth=fitWidth,
            zoomActions=zoomActions,
            openNextImg=openNextImg, openPrevImg=openPrevImg,
            fileMenuActions=(save, close, quit),
            tool=(),
            editMenu=(edit, copy, delete, None, undo, undoLastPoint,
                      None, color1, color2, None, toggle_keep_prev_mode),
            # menu shown at right click
            menu=(
                createMode,
                createRectangleMode,
                createCircleMode,
                createLineMode,
                createPointMode,
                createLineStripMode,
                editMode,
                edit,
                copy,
                delete,
                shapeLineColor,
                shapeFillColor,
                undo,
                undoLastPoint,
                deletePoint,
                addDisVisiblePoint,
                addVisiblePoint,
            ),
            onLoadActive=(
                close,
                createMode,
                createRectangleMode,
                createCircleMode,
                createLineMode,
                createPointMode,
                createLineStripMode,
                editMode,
            ),
            onShapesPresent=(hideAll, showAll),
        )

        self.canvas.edgeSelected.connect(self.actions.addDisVisiblePoint.setEnabled)
        self.canvas.edgeSelected.connect(self.actions.addVisiblePoint.setEnabled)
        self.canvas.edgeSelected.connect(self.actions.deletePoint.setEnabled)

        self.menus = utils.struct(
            file=self.menu('&??????'),
            edit=self.menu('&??????'),
            view=self.menu('&??????'),
            help=self.menu('&??????'),
            recentFiles=QtWidgets.QMenu('?????? &??????'),
            labelList=labelMenu,
        )

        utils.addActions(
            self.menus.file,
            (
                openNextImg,
                openPrevImg,
                # self.menus.recentFiles,
                save,
                saveAuto,
                close,
                deleteFile,
                None,
                quit,
            ),
        )
        utils.addActions(self.menus.help, (help,))
        utils.addActions(
            self.menus.view,
            (
                self.expand_dock.toggleViewAction(),
                self.flag_dock.toggleViewAction(),
                self.label_dock.toggleViewAction(),
                self.shape_dock.toggleViewAction(),
                self.file_dock.toggleViewAction(),
                None,
                fill_drawing,
                None,
                hideAll,
                showAll,
                None,
                zoomIn,
                zoomOut,
                zoomOrg,
                None,
                fitWindow,
                fitWidth,
                None,
            ),
        )

        self.menus.file.aboutToShow.connect(self.updateFileMenu)

        # Custom context menu for the canvas widget:
        utils.addActions(self.canvas.menus[0], self.actions.menu)
        utils.addActions(
            self.canvas.menus[1],
            (
                action('&???????????????', self.copyShape),
                action('&???????????????', self.moveShape),
            ),
        )

        self.tools = self.toolbar('Tools')
        # Menu buttons on Left
        self.actions.tool = (
            openNextImg,
            openPrevImg,
            save,
            deleteFile,
            ignoreImageButton,
            None,
            createMode,
            editMode,
            copy,
            delete,
            undo,
            None,
            zoomIn,
            zoom,
            zoomOut,
            fitWindow,
            fitWidth,
        )

        self.statusBar().showMessage('%s started.' % __appname__)
        self.statusBar().show()

        if output_file is not None and self._config['auto_save']:
            logger.warn(
                'If `auto_save` argument is True, `output_file` argument '
                'is ignored and output filename is automatically '
                'set as IMAGE_BASENAME.json.'
            )
        self.output_file = output_file
        self.output_dir = output_dir

        # Application state.
        self.image = QtGui.QImage()
        self.imagePath = None
        self.recentFiles = []
        self.maxRecent = 7
        self.lineColor = None
        self.fillColor = None
        self.otherData = None
        self.zoom_level = 100
        self.fit_window = False

        if filename is not None and osp.isdir(filename):
            self.importDirImages(filename, load=False)
        else:
            self.filename = filename

        if config['file_search']:
            self.fileSearch.setText(config['file_search'])
            self.fileSearchChanged()

        # XXX: Could be completely declarative.
        # Restore application settings.
        self.settings = QtCore.QSettings('labelme', 'labelme')
        # FIXME: QSettings.value can return None on PyQt4
        self.recentFiles = self.settings.value('recentFiles', []) or []
        size = self.settings.value('window/size', QtCore.QSize(600, 500))
        position = self.settings.value('window/position', QtCore.QPoint(0, 0))
        self.resize(size)
        self.move(position)
        # or simply:
        # self.restoreGeometry(settings['window/geometry']
        self.restoreState(
            self.settings.value('window/state', QtCore.QByteArray()))
        self.lineColor = QtGui.QColor(
            self.settings.value('line/color', Shape.line_color))
        self.fillColor = QtGui.QColor(
            self.settings.value('fill/color', Shape.fill_color))
        Shape.line_color = self.lineColor
        Shape.fill_color = self.fillColor

        # Populate the File menu dynamically.
        self.updateFileMenu()
        # Since loading the file may take some time,
        # make sure it runs in the background.
        if self.filename is not None:
            self.queueEvent(functools.partial(self.loadFile, self.filename))

        # Callbacks:
        self.zoomWidget.valueChanged.connect(self.paintCanvas)

        self.populateModeActions()

        # self.firstStart = True
        # if self.firstStart:
        #    QWhatsThis.enterWhatsThisMode()

        self.importWebImages()

    def menu(self, title, actions=None):
        menu = self.menuBar().addMenu(title)
        if actions:
            utils.addActions(menu, actions)
        return menu

    def toolbar(self, title, actions=None):
        toolbar = ToolBar(title)
        toolbar.setObjectName('%sToolBar' % title)
        # toolbar.setOrientation(Qt.Vertical)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if actions:
            utils.addActions(toolbar, actions)
        self.addToolBar(Qt.LeftToolBarArea, toolbar)
        return toolbar

    # Support Functions

    def noShapes(self):
        return not self.labelList.itemsToShapes

    def populateModeActions(self):
        tool, menu = self.actions.tool, self.actions.menu
        self.tools.clear()
        utils.addActions(self.tools, tool)
        self.canvas.menus[0].clear()
        utils.addActions(self.canvas.menus[0], menu)
        self.menus.edit.clear()
        actions = (
            self.actions.createMode,
            self.actions.createRectangleMode,
            self.actions.createCircleMode,
            self.actions.createLineMode,
            self.actions.createPointMode,
            self.actions.createLineStripMode,
            self.actions.editMode,
        )
        utils.addActions(self.menus.edit, actions + self.actions.editMenu)

    def setDirty(self):
        if self._config['auto_save'] or self.actions.saveAuto.isChecked():
            self.saveLabels(self.imagePath)
            return
        self.dirty = True
        self.actions.save.setEnabled(True)
        self.actions.undo.setEnabled(self.canvas.isShapeRestorable)
        title = __appname__
        if self.filename is not None:
            title = '{} - {}*'.format(title, self.filename)
        self.setWindowTitle(title)

    def setClean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.createMode.setEnabled(True)
        self.actions.createRectangleMode.setEnabled(True)
        self.actions.createCircleMode.setEnabled(True)
        self.actions.createLineMode.setEnabled(True)
        self.actions.createPointMode.setEnabled(True)
        self.actions.createLineStripMode.setEnabled(True)
        title = __appname__
        if self.filename is not None:
            title = '{} - {}'.format(title, self.filename)
        self.setWindowTitle(title)

        if self.hasLabelFile():
            self.actions.deleteFile.setEnabled(True)
        else:
            self.actions.deleteFile.setEnabled(False)

    def toggleActions(self, value=True):
        """Enable/Disable widgets which depend on an opened image."""
        for z in self.actions.zoomActions:
            z.setEnabled(value)
        for action in self.actions.onLoadActive:
            action.setEnabled(value)

    def queueEvent(self, function):
        QtCore.QTimer.singleShot(0, function)

    def status(self, message, delay=5000):
        """
        ????????????????????????
        :param message:
        :param delay:
        :return:
        """
        self.statusBar().showMessage(message, delay)

    def resetState(self):
        self.labelList.clear()
        self.filename = None
        self.imagePath = None
        self.imageData = None
        self.labelFile = None
        self.otherData = None
        self.canvas.resetState()

    def currentItem(self):
        items = self.labelList.selectedItems()
        if items:
            return items[0]
        return None

    def addRecentFile(self, filename):
        if filename in self.recentFiles:
            self.recentFiles.remove(filename)
        elif len(self.recentFiles) >= self.maxRecent:
            self.recentFiles.pop()
        self.recentFiles.insert(0, filename)

    # Callbacks

    def undoShapeEdit(self):
        self.canvas.restoreShape()
        self.labelList.clear()
        self.loadShapes(self.canvas.shapes)
        self.actions.undo.setEnabled(self.canvas.isShapeRestorable)

    def tutorial(self):
        # url = 'https://github.com/wkentaro/labelme/tree/master/examples/tutorial'  # NOQA
        # url = 'http://222.85.230.14:12345/xiaoi/doc'  # NOQA
        url = URL.format("doc")
        webbrowser.open(url)

    def toggleAddPointEnabled(self, enabled):
        self.actions.addPoint.setEnabled(enabled)

    def toggleDrawingSensitive(self, drawing=True):
        """Toggle drawing sensitive.

        In the middle of drawing, toggling between modes should be disabled.
        """
        self.actions.editMode.setEnabled(not drawing)
        self.actions.undoLastPoint.setEnabled(drawing)
        self.actions.undo.setEnabled(not drawing)
        self.actions.delete.setEnabled(not drawing)

    def toggleDrawMode(self, edit=True, createMode='polygon'):
        self.canvas.setEditing(edit)
        self.canvas.createMode = createMode
        if edit:
            self.actions.createMode.setEnabled(True)
            self.actions.createRectangleMode.setEnabled(True)
            self.actions.createCircleMode.setEnabled(True)
            self.actions.createLineMode.setEnabled(True)
            self.actions.createPointMode.setEnabled(True)
            self.actions.createLineStripMode.setEnabled(True)
        else:
            if createMode == 'polygon':
                self.actions.createMode.setEnabled(False)
                self.actions.createRectangleMode.setEnabled(True)
                self.actions.createCircleMode.setEnabled(True)
                self.actions.createLineMode.setEnabled(True)
                self.actions.createPointMode.setEnabled(True)
                self.actions.createLineStripMode.setEnabled(True)
            elif createMode == 'rectangle':
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(False)
                self.actions.createCircleMode.setEnabled(True)
                self.actions.createLineMode.setEnabled(True)
                self.actions.createPointMode.setEnabled(True)
                self.actions.createLineStripMode.setEnabled(True)
            elif createMode == 'line':
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(True)
                self.actions.createCircleMode.setEnabled(True)
                self.actions.createLineMode.setEnabled(False)
                self.actions.createPointMode.setEnabled(True)
                self.actions.createLineStripMode.setEnabled(True)
            elif createMode == 'point':
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(True)
                self.actions.createCircleMode.setEnabled(True)
                self.actions.createLineMode.setEnabled(True)
                self.actions.createPointMode.setEnabled(False)
                self.actions.createLineStripMode.setEnabled(True)
            elif createMode == "circle":
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(True)
                self.actions.createCircleMode.setEnabled(False)
                self.actions.createLineMode.setEnabled(True)
                self.actions.createPointMode.setEnabled(True)
                self.actions.createLineStripMode.setEnabled(True)
            elif createMode == "linestrip":
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(True)
                self.actions.createCircleMode.setEnabled(True)
                self.actions.createLineMode.setEnabled(True)
                self.actions.createPointMode.setEnabled(True)
                self.actions.createLineStripMode.setEnabled(False)
            else:
                raise ValueError('Unsupported createMode: %s' % createMode)
        self.actions.editMode.setEnabled(not edit)

    def setEditMode(self):
        self.toggleDrawMode(True)

    def updateFileMenu(self):
        current = self.filename

        def exists(filename):
            return osp.exists(str(filename))

        menu = self.menus.recentFiles
        menu.clear()
        files = [f for f in self.recentFiles if f != current and exists(f)]
        for i, f in enumerate(files):
            icon = utils.newIcon('labels')
            action = QtWidgets.QAction(
                icon, '&%d %s' % (i + 1, QtCore.QFileInfo(f).fileName()), self)
            action.triggered.connect(functools.partial(self.loadRecent, f))
            menu.addAction(action)

    def popLabelListMenu(self, point):
        self.menus.labelList.exec_(self.labelList.mapToGlobal(point))

    def validateLabel(self, label):
        # no validation
        if self._config['validate_label'] is None:
            return True

        for i in range(self.uniqLabelList.count()):
            label_i = self.uniqLabelList.item(i).text()
            if self._config['validate_label'] in ['exact', 'instance']:
                if label_i == label:
                    return True
            if self._config['validate_label'] == 'instance':
                m = re.match(r'^{}-[0-9]*$'.format(label_i), label)
                if m:
                    return True
        return False

    def editLabel(self, item=None):
        if not self.canvas.editing():
            return
        item = item if item else self.currentItem()
        text = self.labelDialog.popUp(item.text() if item else None)
        if text is None:
            return
        if not self.validateLabel(text):
            self.errorMessage('Invalid label',
                              "Invalid label '{}' with validation type '{}'"
                              .format(text, self._config['validate_label']))
            return
        item.setText(text)
        self.setDirty()
        if not self.uniqLabelList.findItems(text, Qt.MatchExactly):
            self.uniqLabelList.addItem(text)
            self.uniqLabelList.sortItems()

    def fileSearchChanged(self):
        self.importDirImages(
            self.imageList,
            pattern=self.fileSearch.text(),
            load=False,
        )

    def fileSelectionChanged(self):
        items = self.fileListWidget.selectedItems()
        if not items:
            return
        item = items[0]

        if not self.mayContinue():
            return

        currIndex = self.imageList.index(str(item.text()))
        if currIndex < len(self.imageList):
            filename = self.imageList[currIndex]
            if filename:
                self.loadFileByWeb(filename)
                # self.loadFile(filename)

    # React to canvas signals.
    def shapeSelectionChanged(self, selected=False):
        if self._noSelectionSlot:
            self._noSelectionSlot = False
        else:
            shape = self.canvas.selectedShape
            if shape:
                item = self.labelList.get_item_from_shape(shape)
                item.setSelected(True)
            else:
                self.labelList.clearSelection()
        self.actions.delete.setEnabled(selected)
        self.actions.copy.setEnabled(selected)
        self.actions.edit.setEnabled(selected)
        self.actions.shapeLineColor.setEnabled(selected)
        self.actions.shapeFillColor.setEnabled(selected)

    def addLabel(self, shape):
        item = QtWidgets.QListWidgetItem(shape.label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        self.labelList.itemsToShapes.append((item, shape))
        self.labelList.addItem(item)
        if not self.uniqLabelList.findItems(shape.label, Qt.MatchExactly):
            self.uniqLabelList.addItem(shape.label)
            self.uniqLabelList.sortItems()
        self.labelDialog.addLabelHistory(item.text())
        for action in self.actions.onShapesPresent:
            action.setEnabled(True)

    def remLabel(self, shape):
        item = self.labelList.get_item_from_shape(shape)
        self.labelList.takeItem(self.labelList.row(item))

    def loadShapes(self, shapes):
        for shape in shapes:
            self.addLabel(shape)
        self.canvas.loadShapes(shapes)

    def loadLabels(self, shapes):
        s = []
        for label, points, visibles, line_color, fill_color, shape_type in shapes:
            shape = Shape(label=label, shape_type=shape_type)
            shape.visibles = visibles
            for x, y in points:
                shape.addPoint(QtCore.QPoint(x, y))
            shape.close()
            s.append(shape)
            if line_color:
                shape.line_color = QtGui.QColor(*line_color)
            if fill_color:
                shape.fill_color = QtGui.QColor(*fill_color)
        self.loadShapes(s)

    def loadFlags(self, flags):
        self.flag_widget.clear()
        for key, flag in flags.items():
            item = QtWidgets.QListWidgetItem(key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if flag else Qt.Unchecked)
            self.flag_widget.addItem(item)

    def saveLabels(self, filename):
        lf = LabelFile()

        def format_shape(s):
            return dict(
                label=s.label.encode('utf-8') if PY2 else s.label,
                line_color=s.line_color.getRgb()
                if s.line_color != self.lineColor else None,
                fill_color=s.fill_color.getRgb()
                if s.fill_color != self.fillColor else None,
                points=[(p.x(), p.y()) for p in s.points],
                visible=s.visibles,
                shape_type=s.shape_type,
            )

        shapes = [format_shape(shape) for shape in self.labelList.shapes]
        flags = {}
        for i in range(self.flag_widget.count()):
            item = self.flag_widget.item(i)
            key = item.text()
            flag = item.checkState() == Qt.Checked
            flags[key] = flag
        try:
            imagePath = osp.relpath(
                self.imagePath, osp.dirname(filename))
            imageData = self.imageData if self._config['store_data'] else None
            # if osp.dirname(filename) and not osp.exists(osp.dirname(filename)):
            #     os.makedirs(osp.dirname(filename))
            lf.save_to_web(
                filename=filename,
                shapes=shapes,
                imagePath=imagePath,
                imageData=imageData,
                imageHeight=self.image.height(),
                imageWidth=self.image.width(),
                lineColor=self.lineColor.getRgb(),
                fillColor=self.fillColor.getRgb(),
                otherData=self.otherData,
                flags=flags,
                callback=[self.errorMessage, self.status]
            )
            # self.labelFile = lf
            items = self.fileListWidget.findItems(
                self.imagePath, Qt.MatchExactly
            )
            if len(items) > 0:
                if len(items) != 1:
                    raise RuntimeError('There are duplicate files.')
                if len(shapes) <= 0:
                    items[0].setCheckState(Qt.Unchecked)
                else:
                    items[0].setCheckState(Qt.Checked)
            # disable allows next and previous image to proceed
            # self.filename = filename
            return True
        except LabelFileError as e:
            self.errorMessage('Error saving label data', '<b>%s</b>' % e)
            return False

    def copySelectedShape(self):
        self.addLabel(self.canvas.copySelectedShape())
        # fix copy and delete
        self.shapeSelectionChanged(True)

    def labelSelectionChanged(self):
        item = self.currentItem()
        if item and self.canvas.editing():
            self._noSelectionSlot = True
            shape = self.labelList.get_shape_from_item(item)
            self.canvas.selectShape(shape)

    def labelItemChanged(self, item):
        shape = self.labelList.get_shape_from_item(item)
        label = str(item.text())
        if label != shape.label:
            shape.label = str(item.text())
            self.setDirty()
        else:  # User probably changed item visibility
            self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)

    # Callback functions:

    def newShape(self):
        """Pop-up and give focus to the label editor.

        position MUST be in global coordinates.
        """
        items = self.uniqLabelList.selectedItems()
        text = None
        if items:
            text = items[0].text()
        if self._config['display_label_popup'] or not text:
            text = self.labelDialog.popUp(text)
        if text is not None and not self.validateLabel(text):
            self.errorMessage('Invalid label',
                              "Invalid label '{}' with validation type '{}'"
                              .format(text, self._config['validate_label']))
            text = None
        if text is None:
            self.canvas.undoLastLine()
            self.canvas.shapesBackups.pop()
        else:
            self.addLabel(self.canvas.setLastLabel(text))
            self.actions.editMode.setEnabled(True)
            self.actions.undoLastPoint.setEnabled(False)
            self.actions.undo.setEnabled(True)
            self.setDirty()

    def scrollRequest(self, delta, orientation):
        units = - delta * 0.1  # natural scroll
        bar = self.scrollBars[orientation]
        bar.setValue(bar.value() + bar.singleStep() * units)

    def setZoom(self, value):
        self.actions.fitWidth.setChecked(False)
        self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.MANUAL_ZOOM
        self.zoomWidget.setValue(value)

    def addZoom(self, increment=10):
        self.setZoom(self.zoomWidget.value() + increment)

    def zoomRequest(self, delta, pos):
        canvas_width_old = self.canvas.width()

        units = delta * 0.1
        self.addZoom(units)

        canvas_width_new = self.canvas.width()
        if canvas_width_old != canvas_width_new:
            canvas_scale_factor = canvas_width_new / canvas_width_old

            x_shift = round(pos.x() * canvas_scale_factor) - pos.x()
            y_shift = round(pos.y() * canvas_scale_factor) - pos.y()

            self.scrollBars[Qt.Horizontal].setValue(
                self.scrollBars[Qt.Horizontal].value() + x_shift)
            self.scrollBars[Qt.Vertical].setValue(
                self.scrollBars[Qt.Vertical].value() + y_shift)

    def setFitWindow(self, value=True):
        if value:
            self.actions.fitWidth.setChecked(False)
        self.zoomMode = self.FIT_WINDOW if value else self.MANUAL_ZOOM
        self.adjustScale()

    def setFitWidth(self, value=True):
        if value:
            self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.FIT_WIDTH if value else self.MANUAL_ZOOM
        self.adjustScale()

    def togglePolygons(self, value):
        for item, shape in self.labelList.itemsToShapes:
            item.setCheckState(Qt.Checked if value else Qt.Unchecked)

    def loadFile(self, filename=None):
        """Load the specified file, or the last opened file if None."""
        # changing fileListWidget loads file
        if (filename in self.imageList and
                self.fileListWidget.currentRow() !=
                self.imageList.index(filename)):
            self.fileListWidget.setCurrentRow(self.imageList.index(filename))
            self.fileListWidget.repaint()
            return

        self.resetState()
        self.canvas.setEnabled(False)
        if filename is None:
            filename = self.settings.value('filename', '')
        filename = str(filename)
        if not QtCore.QFile.exists(filename):
            self.errorMessage(
                'Error opening file', 'No such file: <b>%s</b>' % filename)
            return False
        # assumes same name, but json extension
        self.status("Loading %s..." % osp.basename(str(filename)))
        label_file = osp.splitext(filename)[0] + '.json'
        if self.output_dir:
            label_file = osp.join(self.output_dir, label_file)
        if QtCore.QFile.exists(label_file) and \
                LabelFile.is_label_file(label_file):
            try:
                self.labelFile = LabelFile(label_file)
            except LabelFileError as e:
                self.errorMessage(
                    'Error opening file',
                    "<p><b>%s</b></p>"
                    "<p>Make sure <i>%s</i> is a valid label file."
                    % (e, label_file))
                self.status("Error reading %s" % label_file)
                return False
            self.imageData = self.labelFile.imageData
            self.imagePath = osp.join(
                osp.dirname(label_file),
                self.labelFile.imagePath,
            )
            if self.labelFile.lineColor is not None:
                self.lineColor = QtGui.QColor(*self.labelFile.lineColor)
            if self.labelFile.fillColor is not None:
                self.fillColor = QtGui.QColor(*self.labelFile.fillColor)
            self.otherData = self.labelFile.otherData
        else:
            self.imageData = LabelFile.load_image_file(filename)
            if self.imageData:
                self.imagePath = filename
            self.labelFile = None
        image = QtGui.QImage.fromData(self.imageData)

        if image.isNull():
            formats = ['*.{}'.format(fmt.data().decode())
                       for fmt in QtGui.QImageReader.supportedImageFormats()]
            self.errorMessage(
                'Error opening file',
                '<p>Make sure <i>{0}</i> is a valid image file.<br/>'
                'Supported image formats: {1}</p>'
                    .format(filename, ','.join(formats)))
            self.status("Error reading %s" % filename)
            return False
        self.image = image
        self.filename = filename
        if self._config['keep_prev']:
            prev_shapes = self.canvas.shapes
        self.canvas.loadPixmap(QtGui.QPixmap.fromImage(image))
        if self._config['flags']:
            self.loadFlags({k: False for k in self._config['flags']})
        if self._config['keep_prev']:
            self.loadShapes(prev_shapes)
        if self.labelFile:
            self.loadLabels(self.labelFile.shapes)
            if self.labelFile.flags is not None:
                self.loadFlags(self.labelFile.flags)
        self.setClean()
        self.canvas.setEnabled(True)
        self.adjustScale(initial=True)
        self.paintCanvas()
        self.addRecentFile(self.filename)
        self.toggleActions(True)
        self.status("Loaded %s" % osp.basename(str(filename)))
        return True

    def resizeEvent(self, event):
        if self.canvas and not self.image.isNull() \
                and self.zoomMode != self.MANUAL_ZOOM:
            self.adjustScale()
        super(MainWindow, self).resizeEvent(event)

    def paintCanvas(self):
        assert not self.image.isNull(), "cannot paint null image"
        self.canvas.scale = 0.01 * self.zoomWidget.value()
        self.canvas.adjustSize()
        self.canvas.update()

    def adjustScale(self, initial=False):
        value = self.scalers[self.FIT_WINDOW if initial else self.zoomMode]()
        self.zoomWidget.setValue(int(100 * value))

    def scaleFitWindow(self):
        """Figure out the size of the pixmap to fit the main widget."""
        e = 2.0  # So that no scrollbars are generated.
        w1 = self.centralWidget().width() - e
        h1 = self.centralWidget().height() - e
        a1 = w1 / h1
        # Calculate a new scale value based on the pixmap's aspect ratio.
        w2 = self.canvas.pixmap.width() - 0.0
        h2 = self.canvas.pixmap.height() - 0.0
        a2 = w2 / h2
        return w1 / w2 if a2 >= a1 else h1 / h2

    def scaleFitWidth(self):
        # The epsilon does not seem to work too well here.
        w = self.centralWidget().width() - 2.0
        return w / self.canvas.pixmap.width()

    def closeEvent(self, event):
        if not self.mayContinue():
            event.ignore()
        self.settings.setValue(
            'filename', self.filename if self.filename else '')
        self.settings.setValue('window/size', self.size())
        self.settings.setValue('window/position', self.pos())
        self.settings.setValue('window/state', self.saveState())
        self.settings.setValue('line/color', self.lineColor)
        self.settings.setValue('fill/color', self.fillColor)
        self.settings.setValue('recentFiles', self.recentFiles)
        # ask the use for where to save the labels
        # self.settings.setValue('window/geometry', self.saveGeometry())

    # User Dialogs #

    def loadRecent(self, filename):
        if self.mayContinue():
            self.loadFile(filename)

    def openPrevImg(self, _value=False):
        keep_prev = self._config['keep_prev']
        if QtGui.QGuiApplication.keyboardModifiers() == \
                (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier):
            self._config['keep_prev'] = True

        if not self.mayContinue():
            return

        if len(self.imageList) <= 0:
            return

        if self.filename is None:
            return

        currIndex = self.imageList.index(self.filename)
        if currIndex - 1 >= 0:
            filename = self.imageList[currIndex - 1]
            if filename:
                self.loadFile(filename)

        self._config['keep_prev'] = keep_prev

    def openNextImg(self, _value=False, load=True):
        keep_prev = self._config['keep_prev']
        if QtGui.QGuiApplication.keyboardModifiers() == \
                (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier):
            self._config['keep_prev'] = True

        if not self.mayContinue():
            return

        # ??????????????????????????????????????????0
        if len(self.imageList) <= 0:
            return

        filename = None
        if self.filename is None:
            filename = self.imageList[0]
        else:
            currIndex = self.imageList.index(self.filename)
            if currIndex + 1 < len(self.imageList):
                filename = self.imageList[currIndex + 1]
            else:
                filename = self.imageList[-1]
        self.filename = filename

        if self.filename and load:
            self.loadFile(self.filename)

        self._config['keep_prev'] = keep_prev

    def openFile(self, _value=False):
        if not self.mayContinue():
            return
        path = osp.dirname(str(self.filename)) if self.filename else '.'
        formats = ['*.{}'.format(fmt.data().decode())
                   for fmt in QtGui.QImageReader.supportedImageFormats()]
        filters = "?????? & ???????????? (%s)" % ' '.join(
            formats + ['*%s' % LabelFile.suffix])
        filename = QtWidgets.QFileDialog.getOpenFileName(
            self, '%s - ???????????????????????????' % __appname__,
            path, filters)
        if QT5:
            filename, _ = filename
        filename = str(filename)
        if filename:
            self.loadFile(filename)

    def changeOutputDirDialog(self, _value=False):
        default_output_dir = self.output_dir
        if default_output_dir is None and self.filename:
            default_output_dir = osp.dirname(self.filename)
        if default_output_dir is None:
            default_output_dir = self.currentPath()

        output_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self, '%s - ??????????????????/????????????' % __appname__,
            default_output_dir,
                  QtWidgets.QFileDialog.ShowDirsOnly |
                  QtWidgets.QFileDialog.DontResolveSymlinks,
        )
        output_dir = str(output_dir)

        if not output_dir:
            return

        self.output_dir = output_dir

        self.statusBar().showMessage(
            '%s . ??????????????????/????????? %s' %
            ('?????????????????????', self.output_dir))
        self.statusBar().show()

        current_filename = self.filename
        self.importDirImages(self.lastOpenDir, load=False)

        if current_filename in self.imageList:
            # retain currently selected file
            self.fileListWidget.setCurrentRow(
                self.imageList.index(current_filename))
            self.fileListWidget.repaint()

    def saveFile(self, _value=False):
        assert not self.image.isNull(), "?????????????????????"
        if self._config['flags'] or self.hasLabels():
            if self.labelFile:
                # DL20180323 - overwrite when in directory
                self._saveFile(self.labelFile.filename)
            elif self.output_file:
                self._saveFile(self.output_file)
                self.close()
            else:
                self._saveFile(self.saveFileDialog())

    def saveFileAs(self, _value=False):
        assert not self.image.isNull(), "?????????????????????"
        if self.hasLabels():
            self._saveFile(self.saveFileDialog())

    def saveFileDialog(self):
        caption = '%s - Choose File' % __appname__
        filters = 'Label files (*%s)' % LabelFile.suffix
        if self.output_dir:
            dlg = QtWidgets.QFileDialog(
                self, caption, self.output_dir, filters
            )
        else:
            dlg = QtWidgets.QFileDialog(
                self, caption, self.currentPath(), filters
            )
        dlg.setDefaultSuffix(LabelFile.suffix[1:])
        dlg.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        dlg.setOption(QtWidgets.QFileDialog.DontConfirmOverwrite, False)
        dlg.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, False)
        basename = osp.splitext(self.filename)[0]
        if self.output_dir:
            default_labelfile_name = osp.join(
                self.output_dir, basename + LabelFile.suffix
            )
        else:
            default_labelfile_name = osp.join(
                self.currentPath(), basename + LabelFile.suffix
            )
        filename = dlg.getSaveFileName(
            self, 'Choose File', default_labelfile_name,
            'Label files (*%s)' % LabelFile.suffix)
        if QT5:
            filename, _ = filename
        filename = str(filename)
        return filename

    def _saveFile(self, filename):
        if filename and self.saveLabels(filename):
            self.addRecentFile(filename)
            self.setClean()

    def closeFile(self, _value=False):
        if not self.mayContinue():
            return
        self.resetState()
        self.setClean()
        self.toggleActions(False)
        self.canvas.setEnabled(False)
        self.actions.saveAs.setEnabled(False)

    def getLabelFile(self):
        if self.filename.lower().endswith('.json'):
            label_file = self.filename
        else:
            label_file = osp.splitext(self.filename)[0] + '.json'

        return label_file

    def deleteFile(self):
        mb = QtWidgets.QMessageBox
        msg = '?????????????????????????????????, ' \
              '??????????'
        answer = mb.warning(self, 'Attention', msg, mb.Yes | mb.No)
        if answer != mb.Yes:
            return

        label_file = self.getLabelFile()
        if osp.exists(label_file):
            os.remove(label_file)
            logger.info('??????????????????: {}'.format(label_file))

            item = self.fileListWidget.currentItem()
            item.setCheckState(Qt.Unchecked)

            self.resetState()

    # Message Dialogs. #
    def hasLabels(self):
        if not self.labelList.itemsToShapes:
            self.errorMessage(
                '??????????????????',
                '???????????????????????????????????????????????????.')
            return False
        return True

    def hasLabelFile(self):
        if self.filename is None:
            return False

        label_file = self.getLabelFile()
        return osp.exists(label_file)

    def mayContinue(self):
        if not self.dirty:
            return True
        mb = QtWidgets.QMessageBox
        msg = '????????????????????????????????? "{}"?'.format(self.filename)
        answer = mb.question(self,
                             '?????????????',
                             msg,
                             mb.Save | mb.Discard | mb.Cancel,
                             mb.Save)
        if answer == mb.Discard:
            self.dirty = False
            return True
        elif answer == mb.Save:
            self.saveFile()
            return True
        else:  # answer == mb.Cancel
            return False

    def errorMessage(self, title, message):
        return QtWidgets.QMessageBox.critical(
            self, title, '<p><b>%s</b></p>%s' % (title, message))

    def currentPath(self):
        return osp.dirname(str(self.filename)) if self.filename else '.'

    def chooseColor1(self):
        color = self.colorDialog.getColor(
            self.lineColor, '??????????????????', default=DEFAULT_LINE_COLOR)
        if color:
            self.lineColor = color
            # Change the color for all shape lines:
            Shape.line_color = self.lineColor
            self.canvas.update()
            self.setDirty()

    def chooseColor2(self):
        color = self.colorDialog.getColor(
            self.fillColor, '??????????????????', default=DEFAULT_FILL_COLOR)
        if color:
            self.fillColor = color
            Shape.fill_color = self.fillColor
            self.canvas.update()
            self.setDirty()

    def toggleKeepPrevMode(self):
        self._config['keep_prev'] = not self._config['keep_prev']

    def deleteSelectedShape(self):
        yes, no = QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No
        msg = '??????????????????????????????, ' \
              '??????????'
        if yes == QtWidgets.QMessageBox.warning(self, 'Attention', msg,
                                                yes | no):
            self.remLabel(self.canvas.deleteSelected())
            self.setDirty()
            if self.noShapes():
                for action in self.actions.onShapesPresent:
                    action.setEnabled(False)

    def chshapeLineColor(self):
        color = self.colorDialog.getColor(
            self.lineColor, '??????????????????', default=DEFAULT_LINE_COLOR)
        if color:
            self.canvas.selectedShape.line_color = color
            self.canvas.update()
            self.setDirty()

    def chshapeFillColor(self):
        color = self.colorDialog.getColor(
            self.fillColor, '??????????????????', default=DEFAULT_FILL_COLOR)
        if color:
            self.canvas.selectedShape.fill_color = color
            self.canvas.update()
            self.setDirty()

    def copyShape(self):
        self.canvas.endMove(copy=True)
        self.addLabel(self.canvas.selectedShape)
        self.setDirty()

    def moveShape(self):
        self.canvas.endMove(copy=False)
        self.setDirty()

    def openDirDialog(self, _value=False, dirpath=None):
        if not self.mayContinue():
            return

        defaultOpenDirPath = dirpath if dirpath else '.'
        if self.lastOpenDir and osp.exists(self.lastOpenDir):
            defaultOpenDirPath = self.lastOpenDir
        else:
            defaultOpenDirPath = osp.dirname(self.filename) \
                if self.filename else '.'

        targetDirPath = str(QtWidgets.QFileDialog.getExistingDirectory(
            self, '%s - ?????????' % __appname__, defaultOpenDirPath,
                  QtWidgets.QFileDialog.ShowDirsOnly |
                  QtWidgets.QFileDialog.DontResolveSymlinks))
        self.importDirImages(targetDirPath)

    @property
    def imageList(self):
        lst = []
        for i in range(self.fileListWidget.count()):
            item = self.fileListWidget.item(i)
            lst.append(item.text())
        return lst

    def importDirImages(self, fileNames, pattern=None, load=True):
        self.actions.openNextImg.setEnabled(True)
        self.actions.openPrevImg.setEnabled(True)
        fileNames = [info[1] for info in self.images_data["image_list"]]
        if not self.mayContinue() or not fileNames:
            return

        self.lastOpenDir = fileNames
        self.filename = None
        self.fileListWidget.clear()

        # for filename in self.scanAllImages(fileNames):
        for filename in fileNames:
            if pattern and pattern not in filename:
                continue
            item = QtWidgets.QListWidgetItem(filename)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            label = self.dict_filename_label_web[filename]
            if label:
                label = json.loads(label)
                if len(label["shapes"]) != 0:
                    item.setCheckState(Qt.Checked)  # ?????????????????????????????????
                else:
                    item.setCheckState(Qt.Unchecked)
            else:
                item.setCheckState(Qt.Unchecked)
            self.fileListWidget.addItem(item)
        self.openNextImgByWeb(load=load)

    def scanAllImages(self, fileNames):
        s = time.time()
        extensions = ['.%s' % fmt.data().decode("ascii").lower()
                      for fmt in QtGui.QImageReader.supportedImageFormats()]
        images = []

        for fileName in fileNames:
            if fileName.lower().endswith(tuple(extensions)):
                images.append(fileName)

        images.sort(key=lambda x: x.lower())
        return images

    def loadFileByWeb(self, filename=None):
        """Load the specified file, or the last opened file if None."""
        # changing fileListWidget loads file
        if (filename in self.imageList and
                self.fileListWidget.currentRow() !=
                self.imageList.index(filename)):
            self.fileListWidget.setCurrentRow(self.imageList.index(filename))
            self.fileListWidget.repaint()
            return

        self.resetState()
        self.canvas.setEnabled(False)
        if filename is None:
            filename = self.settings.value('filename', '')
        filename = str(filename)
        if not filename in self.imageList:
            self.errorMessage(
                '???????????????????????????', '?????????: <b>%s</b>' % filename)
            return False
        # assumes same name, but json extension
        self.status("?????? %s..." % osp.basename(str(filename)))
        label_tag = self.dict_filename_label_web[filename]
        if not label_tag is None:
            label_tag = json.loads(label_tag)
        else:
            label_tag = []
        try:
            self.labelFile = LabelFile([filename, label_tag])
        except LabelFileError as e:
            self.errorMessage(
                '????????????',
                "<p><i>%s</i> "
                % ("???????????????????????????"))
            # self.errorMessage(
            #     'Error opening file',
            #     "<p><b>%s</b></p>"
            #     "<p>Make sure <i>%s</i> is a valid label file."
            #     % (e, label_tag))
            self.status("Error reading %s" % label_tag)
            return False
        self.imageData = self.labelFile.imageData
        self.imagePath = filename
        if self.labelFile.lineColor is not None:
            self.lineColor = QtGui.QColor(*self.labelFile.lineColor)
        if self.labelFile.fillColor is not None:
            self.fillColor = QtGui.QColor(*self.labelFile.fillColor)
        self.otherData = self.labelFile.otherData

        if self.labelFile.fuzzy:
            self.actions.ignoreImageButton.setIconText("??????")
            image = self.labelFile.image_numpy
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            image = cv2.imencode('.jpg', image)
            image = image[1].tobytes()
        else:
            self.actions.ignoreImageButton.setIconText("??????")
            image = self.imageData

        image = QtGui.QImage.fromData(image)

        if image.isNull():
            formats = ['*.{}'.format(fmt.data().decode())
                       for fmt in QtGui.QImageReader.supportedImageFormats()]
            self.errorMessage(
                'Error opening file',
                '<p>Make sure <i>{0}</i> is a valid image file.<br/>'
                'Supported image formats: {1}</p>'
                    .format(filename, ','.join(formats)))
            self.status("Error reading %s" % filename)
            return False
        self.image = image
        self.filename = filename
        if self._config['keep_prev']:
            prev_shapes = self.canvas.shapes
        self.canvas.loadPixmap(QtGui.QPixmap.fromImage(image))
        if self._config['flags']:
            self.loadFlags({k: False for k in self._config['flags']})

        if self.labelFile:
            if self._config['keep_prev'] and len(self.labelFile.shapes) == 0:
                self.loadShapes(prev_shapes)
            else:
                self.loadLabels(self.labelFile.shapes)
                if self.labelFile.flags is not None:
                    self.loadFlags(self.labelFile.flags)
        self.setClean()
        self.canvas.setEnabled(True)
        self.adjustScale(initial=True)
        self.paintCanvas()
        self.addRecentFile(self.filename)
        self.toggleActions(True)
        self.status("Loaded %s" % osp.basename(str(filename)))
        return True
# https://kyfw.12306.cn/passport/captcha/captcha-check?answer=245%2C105&rand=sjrand&login_site=E

# https://kyfw.12306.cn/passport/captcha/captcha-check?callback=jQuery19106513270212890739_1554170758410&answer=258,37,108,105&rand=sjrand&login_site=E&_=1554170758412
# https://kyfw.12306.cn/passport/captcha/captcha-check?callback=jQuery1910090132012414056_1554171347314&answer=44,33,107,39,265,42&rand=sjrand&login_site=E&_=1554171347316

    def openNextImgByWeb(self, _value=False, load=True):
        keep_prev = self._config['keep_prev']
        if QtGui.QGuiApplication.keyboardModifiers() == \
                (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier):
            self._config['keep_prev'] = True

        if not self.mayContinue():
            return

        # ??????????????????????????????????????????0
        if len(self.imageList) <= 0:
            return

        filename = None
        if self.filename is None:
            filename = self.imageList[0]
        else:
            currIndex = self.imageList.index(self.filename)
            if currIndex + 1 < len(self.imageList):
                filename = self.imageList[currIndex + 1]
            else:
                filename = self.imageList[-1]
        self.filename = filename

        if self.filename and load:
            self.loadFileByWeb(self.filename)

        self._config['keep_prev'] = keep_prev

    def importWebImages(self, pattern=None, load=True):
        while 1:
            self.images_data = post("get_file_list")
            if self.images_data is None:
                print("????????????????????????????????????")
                continue
            if "state" in self.images_data:
                print("????????????????????????????????????")
                continue
            elif "image_list" in self.images_data:
                print("???????????????????????? ???????????????")
                break
            else:
                print("?????????????????????????????????")
                continue

        # with open('images_data.pkl', 'wb') as f:
        #     pickle.dump(self.images_data, f)
        #
        # with open('images_data.pkl', 'rb') as f:
        #     self.images_data = pickle.load(f)

        self.actions.openNextImg.setEnabled(True)
        self.actions.openPrevImg.setEnabled(True)

        if not self.mayContinue():
            return

        self.filename = None
        self.fileListWidget.clear()
        self.dict_filename_label_web = dict()
        for id, filename, label in self.images_data["image_list"]:
            self.dict_filename_label_web[filename] = label
            if pattern and pattern not in filename:
                continue

            item = QtWidgets.QListWidgetItem(filename)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            if label:
                label = json.loads(label)
                if len(label["shapes"]) != 0:
                    item.setCheckState(Qt.Checked)  # ?????????????????????????????????
                else:
                    item.setCheckState(Qt.Unchecked)
            else:
                item.setCheckState(Qt.Unchecked)
            self.fileListWidget.addItem(item)
        self.openNextImgByWeb(load=load)

    def img2pixmap(self, image):
        Y, X = image.shape[:2]
        self._bgra = np.zeros((Y, X, 4), dtype=np.uint8, order='C')
        self._bgra[..., 0] = image[..., 2]
        self._bgra[..., 1] = image[..., 1]
        self._bgra[..., 2] = image[..., 0]
        qimage = QtGui.QImage(self._bgra.data, X, Y, QtGui.QImage.Format_RGB32)
        pixmap = QtGui.QPixmap.fromImage(qimage)
        return pixmap

    def mouseMoveEvent(self, event, adsorb, press, focus_x, focus_y):
        """
        Canvas ??????????????????????????????
        :param event:
        :return:
        """
        image = self.labelFile.image_numpy
        if image is not None:
            self.image_bak = image
        elif self.image_bak is not None:
            image = self.image_bak
        if not image is None:
            # image = image[:, :, ::-1]
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            h, w = image.shape[:2]
            offsetsX = self.canvas.offsets[0].x()
            offsetsY = self.canvas.offsets[1].y()
            if adsorb or press:
                x = min(max(self.canvas.prevMovePoint.x(), 0), w)
                y = min(max(self.canvas.prevMovePoint.y(), 0), h)
            else:
                x = focus_x
                y = focus_y

            color = (255, 255, 0)
            r, g, b = image[max(min(y, h - 1), 1), max(min(x, w - 1), 1), :]
            Y = ((r * 299) + (g * 587) + (b * 114)) / 1000
            # if 0 < Y < 255:
            #     h, s, v = cv2.cvtColor(np.array([r, g, b], np.uint8).reshape((1, 1, 3)), cv2.COLOR_RGB2HSV)[0, 0, :]
            #     h = h + 384
            #     if h > 864:
            #         h = h - 864
            #     v = 256 - v
            #     r, g, b = cv2.cvtColor(np.array([h, s, v], np.uint8).reshape((1, 1, 3)), cv2.COLOR_HSV2RGB)[0, 0, :]
            #     color = (int(255 - r), int(255 - g), int(255 - b))
            # else:
            #     if Y > 127:
            #         color = (0, 0, 0)
            #     else:
            #         color = (255, 255, 255)
            #
            # print(color)
            if Y > 125:
                color = (0, 0, 0)
            else:
                color = (255, 255, 255)

            side = 100
            paddingXL = 0
            paddingXR = side * 2
            paddingYT = 0
            paddingYB = side * 2
            if (w - side) >= x >= side and (h - side) >= y >= side:
                image = image[y - side:y + side, x - side:x + side, :]
                cv2.circle(image, (side, side), 15, color, 1)
                cv2.circle(image, (side, side), 3, color, 1)

            else:
                image_zero = np.zeros((side * 2, side * 2, 3), np.uint8)
                image = image[max(y - side, 0):min(y + side, h), max(x - side, 0):min(x + side, w), :]
                if x < side:
                    paddingXL = side - x
                    paddingXR = side * 2
                if x > w - side:
                    paddingXL = 0
                    paddingXR = side * 2 - (x - (w - side))
                if y < side:
                    paddingYT = side - y
                    paddingYB = side * 2
                if y > h - side:
                    paddingYT = 0
                    paddingYB = side * 2 - (y - (h - side))
                image_zero[paddingYT:paddingYB, paddingXL:paddingXR, :] = image
                cv2.circle(image_zero, (side, side), 15, color, 1)
                cv2.circle(image_zero, (side, side), 3, color, 1)
                image = image_zero

            # image = image[max(min(y-100, h), 0):max(min(y+100, h), 0), max(min(x-100, w), 0):max(min(x+100, w), 0), :]
            self.expand_widget.setPixmap(self.img2pixmap(image))

    def saveFileByWeb(self, _value=False):
        assert not self.image.isNull(), "?????????????????????"
        if self._config['flags'] or self.hasLabels():
            if self.labelFile:
                # DL20180323 - overwrite when in directory
                self._saveFile(self.labelFile.filename)
            elif self.output_file:
                self._saveFile(self.output_file)
                self.close()
            else:
                self._saveFile(self.saveFileDialog())

    def ignoreImage(self):
        def format_shape(s):
            return [s.label.encode('utf-8') if PY2 else s.label,
                    [(p.x(), p.y()) for p in s.points],
                    s.visibles,
                    s.line_color.getRgb(),
                    s.fill_color.getRgb(),
                    s.shape_type]

        ignoreImageButton = self.actions.ignoreImageButton
        # ignoreImageButton.setEnabled(True)
        shapes = [format_shape(shape) for shape in self.labelList.shapes]
        if not self.labelFile.fuzzy:
            res = post("set_fuzzy_by_path", data={"image_path": self.labelFile.filename, "fuzzy": 1})
            if res["state"] == 1:
                image = self.labelFile.image_numpy
                if image is None:
                    image =self.image_bak
                image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
                image = cv2.imencode('.jpg', image)
                image = image[1].tobytes()
                image = QtGui.QImage.fromData(image)
                self.canvas.loadPixmap(QtGui.QPixmap.fromImage(image))
                self.labelList.clear()
                self.loadLabels(shapes)
                ignoreImageButton.setIconText("??????")
                self.labelFile.fuzzy = 1
            else:
                self.errorMessage("????????????", "????????????")

        else:
            res = post("set_fuzzy_by_path", data={"image_path": self.labelFile.filename, "fuzzy": 0})
            if res["state"] == 1:
                image = self.labelFile.imageData
                image = QtGui.QImage.fromData(image)
                self.canvas.loadPixmap(QtGui.QPixmap.fromImage(image))
                self.labelList.clear()
                self.loadLabels(shapes)
                ignoreImageButton.setIconText("??????")
                self.labelFile.fuzzy = 0
            else:
                self.errorMessage("????????????", "????????????")
