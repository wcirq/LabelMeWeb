import json
import time

import requests

# URL = 'http://192.168.160.69:12345/xiaoi/{}'
URL = 'http://222.85.230.14:12345/xiaoi/{}'
# URL = 'http://222.85.230.14:12346/xiaoi/{}'
index = 0
count = 5


def post(request_url, data=None):
    global index, URL, count
    url = URL.format(request_url)
    data_json = json.dumps(data)
    for i in range(count):
        try:
            r = requests.post(url, data=data_json)
            result_json = r.json()
            if "state" in result_json.keys():
                if result_json["state"] == 0:
                    raise Exception("服务器内部错误 code:500", 1)
            return result_json
        except Exception as e:
            time.sleep(1)
            print("服务器忙！正在重试 [{}/{}]".format(i+1, count))
            continue
