import base64
import io
import json
import os.path as osp

import PIL.Image
import cv2
import numpy as np
from labelme._version import __version__
from labelme.logger import logger
from labelme import PY2
from labelme import QT4
from labelme import utils
from labelme.network import post


class LabelFileError(Exception):
    pass


class LabelFile(object):
    suffix = '.json'

    def __init__(self, filename=None):
        self.shapes = ()
        self.imagePath = None
        self.imageData = None
        self.image_numpy = None

        if isinstance(filename, list):
            if filename is not None:
                self.load(filename)
            self.filename = filename[0]
        else:
            if filename is not None:
                self.load(filename)
            self.filename = filename

    @staticmethod
    def load_image_file(filename):
        try:
            image_pil = PIL.Image.open(filename)
        except IOError:
            logger.error('Failed opening image file: {}'.format(filename))
            return

        # apply orientation to image according to exif
        image_pil = utils.apply_exif_orientation(image_pil)

        with io.BytesIO() as f:
            ext = osp.splitext(filename)[1].lower()
            if PY2 and QT4:
                format = 'PNG'
            elif ext in ['.jpg', '.jpeg']:
                format = 'JPEG'
            else:
                format = 'PNG'
            image_pil.save(f, format=format)
            f.seek(0)
            return f.read()

    def load(self, filename):
        keys = [
            'imageData',
            'imagePath',
            'lineColor',
            'fillColor',
            'shapes',  # polygonal annotations
            'flags',  # image level flags
            'imageHeight',
            'imageWidth',
        ]
        otherData = {}
        shapes = []
        try:
            if isinstance(filename, str):
                with open(filename, 'rb' if PY2 else 'r') as f:
                    data = json.load(f)
                if data['imageData'] is not None:
                    imageData = base64.b64decode(data['imageData'])
                    if PY2 and QT4:
                        imageData = utils.img_data_to_png_data(imageData)
                else:
                    # relative path from label file to relative path from cwd
                    imagePath = osp.join(osp.dirname(filename), data['imagePath'])
                    imageData = self.load_image_file(imagePath)
                flags = data.get('flags')
                imagePath = data['imagePath']
                self._check_image_height_and_width(
                    base64.b64encode(imageData).decode('utf-8'),
                    data.get('imageHeight'),
                    data.get('imageWidth'),
                )
                lineColor = data['lineColor']
                fillColor = data['fillColor']
                shapes = (
                    (
                        s['label'],
                        s['points'],
                        s['line_color'],
                        s['fill_color'],
                        s.get('shape_type', 'polygon'),
                    )
                    for s in data['shapes']
                )

                for key, value in data.items():
                    if key not in keys:
                        otherData[key] = value
            elif isinstance(filename, list):
                # data = filename[1]
                data = post("get_lable_by_path", data={"image_path": filename[0]})
                try:
                    data = json.loads(data["label"])
                except Exception as e:
                    print(e)
                if data['imageData'] is not None:
                    imageData = base64.b64decode(data['imageData'])
                    if PY2 and QT4:
                        imageData = utils.img_data_to_png_data(imageData)
                else:
                    result = post("get_image_by_path", data={"image_path": filename[0]})
                    image = result["image"]
                    imageData = base64.b64decode(image)
                image_numpy = np.asarray(bytearray(imageData), dtype="uint8")
                self.image_numpy = cv2.imdecode(image_numpy, cv2.IMREAD_COLOR)
                height, width = self.image_numpy.shape[:2]

                flags = data.get('flags')
                imagePath = data['imagePath']
                self._check_image_height_and_width(
                    base64.b64encode(imageData).decode('utf-8'),
                    data.get('imageHeight'),
                    data.get('imageWidth'),
                )
                lineColor = data['lineColor']
                fillColor = data['fillColor']
                for s in data['shapes']:
                    label = s['label']
                    points = s['points']
                    if "visible" in s.keys():
                        visibles = s['visible']
                    else:
                        visibles = [1] * len(points)
                    line_color = s['line_color']
                    fill_color = s['fill_color']
                    shape_type = s.get('shape_type', 'polygon')
                    shapes.append([label, points, visibles, line_color, fill_color, shape_type])

                for key, value in data.items():
                    if key not in keys:
                        otherData[key] = value
                # imageData = PIL.Image.fromarray(image)
                # for s in data:
                #     type = s["type"]
                #     tag = s["tag"]
                #     label = ""
                #     if type == 0:
                #         label = "笔杆"
                #     elif type == 1:
                #         label = "手掌"
                #     elif type == 2:
                #         label = "表格"
                #     points = []
                #     if type < 2:
                #         points.append([int(tag[0]*width+0.5), int(tag[1]*height+0.5)])
                #         points.append([int(tag[2]*width+0.5), int(tag[3]*height+0.5)])
                #     line_color = None
                #     fill_color = None
                #     shape_type = ""
                #     if type == 0:
                #         shape_type = "line"
                #     elif type == 1:
                #         shape_type = "rectangle"
                #     elif type == 2:
                #         shape_type = "polygon"
                #     shapes.append([label, points, line_color, fill_color, shape_type])
                # flags = {}
                # imagePath = None
                # lineColor = None
                # fillColor = None
                # filename = None
        except Exception as e:
            raise LabelFileError(e)

        # Only replace data after everything is loaded.
        self.flags = flags
        self.shapes = shapes
        self.imagePath = imagePath
        self.imageData = imageData
        self.lineColor = lineColor
        self.fillColor = fillColor
        self.filename = filename
        self.otherData = otherData

    @staticmethod
    def _check_image_height_and_width(imageData, imageHeight, imageWidth):
        img_arr = utils.img_b64_to_arr(imageData)
        if imageHeight is not None and img_arr.shape[0] != imageHeight:
            logger.error(
                'imageHeight does not match with imageData or imagePath, '
                'so getting imageHeight from actual image.'
            )
            imageHeight = img_arr.shape[0]
        if imageWidth is not None and img_arr.shape[1] != imageWidth:
            logger.error(
                'imageWidth does not match with imageData or imagePath, '
                'so getting imageWidth from actual image.'
            )
            imageWidth = img_arr.shape[1]
        return imageHeight, imageWidth

    def save(
            self,
            filename,
            shapes,
            imagePath,
            imageHeight,
            imageWidth,
            imageData=None,
            lineColor=None,
            fillColor=None,
            otherData=None,
            flags=None,
    ):
        if imageData is not None:
            imageData = base64.b64encode(imageData).decode('utf-8')
            imageHeight, imageWidth = self._check_image_height_and_width(
                imageData, imageHeight, imageWidth
            )
        if otherData is None:
            otherData = {}
        if flags is None:
            flags = {}
        data = dict(
            version=__version__,
            flags=flags,
            shapes=shapes,
            lineColor=lineColor,
            fillColor=fillColor,
            imagePath=imagePath,
            imageData=imageData,
            imageHeight=imageHeight,
            imageWidth=imageWidth,
        )
        for key, value in otherData.items():
            data[key] = value
        try:
            with open(filename, 'wb' if PY2 else 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.filename = filename
        except Exception as e:
            raise LabelFileError(e)

    def save_to_web(
            self,
            filename,
            shapes,
            imagePath,
            imageHeight,
            imageWidth,
            imageData=None,
            lineColor=None,
            fillColor=None,
            otherData=None,
            flags=None,
            callback=None,
    ):
        if imageData is not None:
            imageData = base64.b64encode(imageData).decode('utf-8')
            imageHeight, imageWidth = self._check_image_height_and_width(
                imageData, imageHeight, imageWidth
            )
        if otherData is None:
            otherData = {}
        if flags is None:
            flags = {}
        image_label = dict(
            version=__version__,
            flags=flags,
            shapes=shapes,
            lineColor=lineColor,
            fillColor=fillColor,
            imagePath=imagePath,
            imageData=imageData,
            imageHeight=imageHeight,
            imageWidth=imageWidth,
        )
        for key, value in otherData.items():
            image_label[key] = value
        try:
            image_path = filename
            data = {"image_path": image_path, "image_label": image_label}
            res = post("save_lable_by_path", data)
            if res["state"] == 1:
                callback[1]("标签保存成功！")
            else:
                callback[0]("保存提示!", "标签保存失败！")
            self.filename = filename
        except Exception as e:
            print(e)
            print(data, type(data))
            raise LabelFileError(e)

    @staticmethod
    def is_label_file(filename):
        return osp.splitext(filename)[1].lower() == LabelFile.suffix
