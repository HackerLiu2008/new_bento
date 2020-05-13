import time
import datetime
from dateutil.relativedelta import relativedelta


def change_today(datatime, day):
    time_l = datatime.replace("-0", "-").split("-")
    d1 = datetime.datetime(int(time_l[0]), int(time_l[1]), int(time_l[2]))
    d2 = d1 + relativedelta(days=day)
    d3 = datetime.datetime.strptime(str(d2), "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
    return d3


def cut_list(ls, n):
    return [ls[i:i + n] for i in range(0, len(ls), n)]



if __name__ == "__main__":
    g, t = get_time()
    print(g, t)
