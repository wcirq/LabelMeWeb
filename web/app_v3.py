# -*- coding=utf-8 -*-
"""
api接口控制
"""
import base64
import os
import platform
import socket
import subprocess
import threading
import time

import cv2
import numpy as np
from PIL import Image
from flask import Flask, request, json, send_from_directory, render_template

from dao.dao import session, VisualShanghai

# from web.servce.detection import detection_pen
from flask_bootstrap import Bootstrap
app = Flask(__name__, static_folder='', static_url_path='')
bootstrap = Bootstrap(app)


sysstr = platform.system()
if sysstr == "Windows":
    PATH_D = "D:\\src"
    PATH_C = "C:\\image"
elif sysstr == "Linux":
    # PATH_D = "/home/wcy/image"
    # PATH_C = "/home/wcy/images"
    PATH_C = "/home/wcy/web/data/image"
    PATH_D = "/home/wcy/web/data/image2"
else:
    print("Other System tasks")

VERSION = 0.1
IP_LIST = []


@app.route('/xiaoi/get_image', methods=['POST'])
def get_image():
    if request.data:
        data = json.loads(request.data)
        image_path = session.query(VisualShanghai.image_path).filter(VisualShanghai.id == data['image_id']).all()
        img_path = image_path[0][0]
        # img_path = 'D:\\baidu_img\\动物\\93.jpg'
        # filepath, filename = os.path.split(img_path)
        filename = os.path.basename(img_path)
        img_path = os.path.join(PATH_C, filename)
        if not os.path.isfile(img_path):
            img_path = os.path.join(PATH_D, filename)
        img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if img is None:
            img = Image.open(img_path)
            img = np.array(img, dtype=np.uint8)
        else:
            img = img[:, :, ::-1]
        # img = detection_pen(img)
        # img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        # img = cv2.resize(img, (500, 500))
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], np.float32)  # 锐化
        # img = cv2.filter2D(img, -1, kernel=kernel)
        ret, flow = cv2.imencode('.jpg', img)
        image_flow = flow.tobytes()
        image_base64 = base64.b64encode(image_flow).decode()

        isFuzzy = session.query(VisualShanghai.image_fuzzy).filter(VisualShanghai.id == data['image_id']).all()[0][0]

        return json.dumps({'image': image_base64, "fuzzy": isFuzzy})
    else:
        return json.dumps({"erorr": "参数有误"}, ensure_ascii=False)


@app.route('/xiaoi/get_image_by_path', methods=['POST'])
def get_image_by_path():
    if request.data:
        data = json.loads(request.data)
        image_path = data['image_path']
        # img_path = 'D:\\baidu_img\\动物\\93.jpg'
        # filepath, filename = os.path.split(img_path)
        filename = os.path.basename(image_path)
        img_path = os.path.join(PATH_C, filename)
        if not os.path.isfile(img_path):
            img_path = os.path.join(PATH_D, filename)
        img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if img is None:
            img = Image.open(img_path)
            img = np.array(img, dtype=np.uint8)
        else:
            pass
            # img = img[:, :, ::-1]
        # img = detection_pen(img)
        # img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], np.float32)  # 锐化
        # img = cv2.filter2D(img, -1, kernel=kernel)
        ret, flow = cv2.imencode('.jpg', img)
        image_flow = flow.tobytes()
        image_base64 = base64.b64encode(image_flow).decode()

        isFuzzy = session.query(VisualShanghai.image_fuzzy).filter(VisualShanghai.image_path == data['image_path']).all()[0][0]

        return json.dumps({'image': image_base64, "fuzzy": isFuzzy})
    else:
        return json.dumps({"erorr": "参数有误"}, ensure_ascii=False)


@app.route('/xiaoi/get_list', methods=['POST'])
def get_list():
    try:
        image_ids = session.query(VisualShanghai.id).all()
        image_ids = [id[0] for id in image_ids]
        result = json.dumps({'image_num': len(image_ids), 'image_list': image_ids}, ensure_ascii=False)
    except Exception as e:
        print(e)
        session.rollback()
        result = json.dumps({'state': 0}, ensure_ascii=False)
    return result


@app.route('/xiaoi/get_file_list', methods=['POST'])
def get_file_list():
    try:
        visuals = session.query(VisualShanghai.id, VisualShanghai.image_path, VisualShanghai.image_label).all()
        image_ids_path = [[visual.id, visual.image_path, visual.image_label] for visual in visuals]
        result = json.dumps({'image_num': len(image_ids_path), 'image_list': image_ids_path}, ensure_ascii=False)
    except Exception as e:
        print(e)
        session.rollback()
        result = json.dumps({'state': 0}, ensure_ascii=False)
    return result


@app.route('/xiaoi/get_lable_by_id', methods=['POST'])
def get_lable_by_id():
    if request.data:
        data = json.loads(request.data)
        try:
            tag = session.query(VisualShanghai.tag).filter(VisualShanghai.id == data['image_id']).all()
            result = json.dumps({'lable': tag[0][0]}, ensure_ascii=False)
        except:
            session.rollback()
            result = json.dumps({'state': 0}, ensure_ascii=False)
        return result


@app.route('/xiaoi/get_lable_by_path', methods=['POST'])
def get_lable_by_path():
    if request.data:
        data = json.loads(request.data)
        try:
            visual = session.query(VisualShanghai.image_label, VisualShanghai.image_fuzzy).filter(
                VisualShanghai.image_path == data['image_path']).first()
            result = json.dumps({'label': visual.image_label, "fuzzy": visual.image_fuzzy}, ensure_ascii=False)
        except Exception as e:
            print(e)
            print(data)
            session.rollback()
            result = json.dumps({'state': 0}, ensure_ascii=False)
        return result


@app.route('/xiaoi/save_lable', methods=['POST'])
def save_lable():
    if request.data:
        data = json.loads(request.data)
        id = data['image_id']
        lable = data['image_tag']
        lable = json.dumps(lable)
        try:
            result = session.query(VisualShanghai).filter(VisualShanghai.id == id).first()
        except:
            session.rollback()
        old_tag = result.tag
        result.tag = lable
        try:
            session.commit()
            res = json.dumps({'state': 1}, ensure_ascii=False)
        except:
            session.rollback()
            res = json.dumps({'state': 0}, ensure_ascii=False)
        return res


@app.route('/xiaoi/save_lable_by_path', methods=['POST'])
def save_lable_by_path():
    if request.data:
        data = json.loads(request.data)
        image_path = data['image_path']
        image_label = data['image_label']
        image_label = json.dumps(image_label)
        try:
            result = session.query(VisualShanghai).filter(VisualShanghai.image_path == image_path).first()
            result.image_label = image_label
        except Exception as e:
            print("Exception1", e)
            print("data", data)
            session.rollback()
            res = json.dumps({'state': 0}, ensure_ascii=False)
            return res
        try:
            session.commit()
            res = json.dumps({'state': 1}, ensure_ascii=False)
        except Exception as e:
            print("Exception2", e)
            print("data", data)
            session.rollback()
            res = json.dumps({'state': 0}, ensure_ascii=False)
        return res


@app.route('/xiaoi/set_fuzzy', methods=['POST'])
def set_fuzzy():
    if request.data:
        data = json.loads(request.data)
        id = data['image_id']
        fuzzy = data['fuzzy']
        try:
            result = session.query(VisualShanghai).filter(VisualShanghai.id == id).first()
        except:
            session.rollback()
        old_fuzzy = VisualShanghai.image_fuzzy
        result.image_fuzzy = fuzzy
        try:
            session.commit()
            res = json.dumps({'state': 1}, ensure_ascii=False)
        except:
            session.rollback()
            res = json.dumps({'state': 0}, ensure_ascii=False)
        return res


@app.route('/xiaoi/set_fuzzy_by_path', methods=['POST'])
def set_fuzzy_by_path():
    if request.data:
        data = json.loads(request.data)
        image_path = data['image_path']
        fuzzy = data['fuzzy']
        try:
            result = session.query(VisualShanghai).filter(VisualShanghai.image_path == image_path).first()
        except:
            session.rollback()
            session.rollback()
            res = json.dumps({'state': 0}, ensure_ascii=False)
            return res
        old_fuzzy = result.image_fuzzy
        result.image_fuzzy = fuzzy
        try:
            session.commit()
            res = json.dumps({'state': 1}, ensure_ascii=False)
        except:
            session.rollback()
            res = json.dumps({'state': 0}, ensure_ascii=False)
        return res


@app.route('/xiaoi/inverse_color', methods=['POST'])
def inverse_color():
    if request.data:
        data = json.loads(request.data)
        image_path = session.query(VisualShanghai.image_path).filter(VisualShanghai.id == data['image_id']).all()
        img_path = image_path[0][0]
        # img_path = 'D:\\baidu_img\\动物\\93.jpg'
        # filepath, filename = os.path.split(img_path)
        filename = os.path.basename(img_path)
        img_path = os.path.join(PATH_C, filename)
        if not os.path.isfile(img_path):
            img_path = os.path.join(PATH_D, filename)
        img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if img is None:
            img = Image.open(img_path)
            img = np.array(img, dtype=np.uint8)
        try:
            # img = img[::-1]
            img = img[..., ::-1]
            cv2.imwrite(img_path, img)
            res = json.dumps({'state': 1}, ensure_ascii=False)
        except:
            res = json.dumps({'state': 0}, ensure_ascii=False)
        return res


@app.route('/xiaoi/check_update', methods=['POST', 'GET'])
def check_update():
    return json.dumps({'VERSION': VERSION}, ensure_ascii=False)


@app.route('/xiaoi/upload', methods=['POST', 'GET'])
def upload():
    return send_from_directory(os.path.dirname(__file__), "main.py", as_attachment=True)


@app.route('/xiaoi/doc', methods=["GET", "POST"])
def show_test():
    return render_template("show.html")


def get_host_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    finally:
        s.close()

    return ip


def ping_ip(ip):
    '''
    检查对应的IP是否被占用
    '''
    global IP_LIST
    cmd_str = "ping {0} -n 1 -w 600".format(ip)
    DETACHED_PROCESS = 0x00000008  # 不创建cmd窗口
    try:
        subprocess.run(cmd_str, creationflags=DETACHED_PROCESS, check=True)  # 仅用于windows系统
    except subprocess.CalledProcessError as err:
        if ip in IP_LIST:
            IP_LIST.remove(ip)
    else:
        if not ip in IP_LIST:
            IP_LIST.append(ip)


def get_life_ip(HOST):
    while True:
        pthread_list = []
        for i in range(256):
            ip = HOST.format(i)
            pthread_list.append(threading.Thread(target=ping_ip, args=(ip,)))
        for item in pthread_list:
            item.setDaemon(True)
            item.start()
            item.join()
        time.sleep(2)


def start_radio():
    """
    向局域网内广播
    :return:
    """
    global IP_LIST
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    PORT = 12346
    HOST = '<broadcast>'
    HOST = get_host_ip()
    HOST = HOST.split(".")
    HOST = "{}.{{}}".format(".".join(HOST[:-1]))
    # threading.Thread(target=get_life_ip, args=(HOST,)).start()
    while 1:
        for i in range(256):
            s.sendto('服务启动'.encode('utf-8'), (HOST.format(i), PORT))
            # print(HOST.format(i))
            # time.sleep(0.001)
        time.sleep(3)


def main():
    # threading.Thread(target=start_radio, args=()).start()
    app.run(host='0.0.0.0', port=12346)


if __name__ == '__main__':
    main()
