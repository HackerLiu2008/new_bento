import requests


def ip_where(ip):
    url = "http://apidata.chinaz.com/CallAPI/ip"
    parms = {'key': 'ea74dcfecc6a455586a849ec69291d62',
             'ip': ip}
    response = requests.get(url, params=parms)
    print(response.json())


if __name__ == "__main__":
    ip_where('61.140.182.90')
