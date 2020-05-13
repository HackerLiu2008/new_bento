import time
import json
import requests
from requests.adapters import HTTPAdapter
import datetime
from datetime import datetime
from tools_me.redis_tools import RedisTool


class Key(object):
    ACCESSKEY = "4IEqK6pqfbC6CH8uf4oSXA"
    SECRETKEY = "XQH2NVKqTOdbKO3jIf1F1g"
    URL = "https://api.bentoforbusiness.com/"


def change_time(dt):
    if dt:
        # 转换成时间数组
        timeArray = time.strptime(dt, "%Y-%m-%d %H:%M:%S")
        # 转换成时间戳
        timestamp = time.mktime(timeArray)
        return int(timestamp * 1000)
    else:
        return int(time.time() * 1000)


def cut_list(ls, n):
    return [ls[i:i + n] for i in range(0, len(ls), n)]


def RefreshToken():
    token_url = "{}{}".format(Key.URL, "sessions")
    data = {
        "accessKey": Key.ACCESSKEY,
        "secretKey": Key.SECRETKEY,
    }
    headers = {"Connection": "close"}
    requests.adapters.DEFAULT_RETRIES = 5
    s = requests.session()
    s.keep_alive = False
    try:
        token = s.post(url=token_url, headers=headers, data=json.dumps(data), timeout=15)
        d = {
            "token": token.headers.get("authorization"),
            "time": datetime.now().hour
        }
        RedisTool.hash_set("new_bento", 'token', json.dumps(d))
        return d
    except:
        RefreshToken()


def GetToken():
    res = RedisTool.hash_get('new_bento', 'token')
    token = json.loads(res)
    if token.get("time") != datetime.now().hour:
        bento_token = RefreshToken()
        return bento_token.get("token")
    return token.get("token")


if __name__ == "__main__":
    d = {'aa': 13}
    print(d.get('df'))
