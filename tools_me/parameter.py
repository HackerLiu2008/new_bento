# coding:utf-8
# 以下是一些常用参数

# 保存excel文件的路径


ACCOUNT_DIR = ""
TASK_DIR = ""
DW_TASK = ""
DW_ACCOUNT = ""
SMT_TASK = ""


class DIR_PATH:
    # LOG_PATH = "G:/world_pay/static/log/card.log"
    LOG_PATH = "/bento_web_version2/static/log/card.log"

    # PRI_PEM = "G:\\world_pay\\tools_me\\RSA_NAME\\privkey_henry.pem"
    PRI_PEM = "/var/www/bento_web_version/tools_me/RSA_NAME/privkey_henry.pem"

    # PUB_PEM = 'G:\\world_pay\\tools_me\\RSA_NAME\\pro_epaylinks_publickey.pem'
    PUB_PEM = "/var/www/bento_web/tools_me/RSA_NAME/pro_epaylinks_publickey.pem"

    PHOTO_DIR = "/bento_web_version2/static/pay_pic"


class RET:
    OK = 0
    SERVERERROR = 502


class MSG:
    OK = '完成'
    SERVERERROR = '服务器错误'
    NODATA = '无数据'
    DATAERROR = '参数错误'
    PSWDERROR = '账号或密码错误'
    PSWDLEN = '密码长度不得小于6位数'
    NOAUTH = '您没有权限操作'


class CACHE:
    TIMEOUT = 15


class TRANS_TYPE:
    IN = "收入"
    OUT = "支出"


class DO_TYPE:
    CREATE_CARD = "开卡"
    TOP_UP = "充值"
    REFUND = "退款"
    DELCARD = "删卡"
    SYSTEM = '系统扣费'
