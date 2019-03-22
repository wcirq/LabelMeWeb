import json
import requests

URL = 'http://127.0.0.1:12345/xiaoi/{}'

def post(request_url, data=None):
    global URL
    url = URL.format(request_url)
    data = json.dumps(data)
    r = requests.post(url, data=data)  # url为随意URL
    result_json = r.json()
    return result_json
