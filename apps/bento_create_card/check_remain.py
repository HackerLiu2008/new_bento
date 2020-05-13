import logging
import time
import requests
import re
from tools_me.bento_token import GetToken
from requests.adapters import HTTPAdapter
import pymysql
import asyncio

logging.basicConfig(level=logging.INFO, format='%(asctime)s :: %(levelname)s :: %(message)s', filename="error.log")


class SqlData(object):
    def __init__(self, database_name):
        host = "127.0.0.1"
        port = 3306
        user = "root"
        password = "admin"
        database = database_name
        self.connect = pymysql.Connect(
            host=host, port=port, user=user,
            passwd=password, db=database,
            charset='utf8'
                )
        self.cursor = self.connect.cursor()

    def search_card_data(self):
        sql = "select alias, card_id, card_number,attribution from bento_create_card"
        self.cursor.execute(sql)
        rows = self.cursor.fetchall()
        self.close_connect()
        return tuple(reversed(rows))

    def search_out_trans(self, card_number):
        sql = "SELECT SUM(do_money) FROM account_trans WHERE card_no LIKE '%{}%' AND do_type='充值'".format(card_number)
        self.cursor.execute(sql)
        rows = self.cursor.fetchone()
        # self.close_connect()
        if not rows[0]:
            return 0
        return rows[0]

    def search_recycle_trans(self, card_number):
        sql = "SELECT SUM(do_money) FROM account_trans WHERE card_no LIKE '%{}%' AND trans_type='收入'".format(card_number)
        self.cursor.execute(sql)
        rows = self.cursor.fetchone()
        # self.close_connect()
        if not rows[0]:
            return 0
        return rows[0]

    def close_connect(self):
        if self.cursor:
            self.cursor.close()
        if self.connect:
            self.connect.close()


class RechargeCard(object):

    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
            "authorization": GetToken(),
            "Connection": "close",
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/80.0.3987.149 Safari/537.36'
        }
        self.requests = requests.session()
        self.requests.mount('https://', HTTPAdapter(max_retries=5))
        self.requests.keep_alive = False

    # 使用递归多次查询大于500条交易记录的卡交易数据
    def transaction_data(self, cards, end_time=0, transactions_datas=None):
        url = "https://api.bentoforbusiness.com/transactions"
        params = {
            "cards": "{}".format(cards),
            "dateStart": 1570032000000,
            "dateEnd": int(round(time.time() * 1000)) if end_time == 0 else end_time
        }
        try:
            r = self.requests.get(url=url, headers=self.headers, params=params, timeout=30)
            size = r.json().get('size')
            if not transactions_datas:
                transactions_datas = []
            for transactions in r.json().get("cardTransactions"):
                transactions_datas.append({
                    "date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(transactions.get("transactionDate") / 1000)),
                    "description": transactions.get("payee").get("name"),
                    "alias": transactions.get("card").get("alias"),
                    "amount": transactions.get("amount"),
                    "status": transactions.get("status"),
                    "cardTransactionId": transactions.get("cardTransactionId"),
                    "lastFour": transactions.get("card").get("lastFour"),
                    "originalCurrency": transactions.get("originalCurrency"),
                    "businessId": transactions.get("business").get("businessId"),
                    "availableAmount": transactions.get("availableAmount"),
                })
            if size > 500:
                end_data = transactions_datas[-1].get('date')
                date = int(time.mktime(time.strptime(end_data, "%Y-%m-%d %H:%M:%S")) - 1) * 1000
                transactions_datas = self.transaction_data(cards, date, transactions_datas)
            return transactions_datas
        except Exception as e:
            print(params)
            print('交易记录请求超时！' + str(e))
            self.transaction_data(card_id, transactions_datas=transactions_datas)

    def one_alias(self, alias):
        url = "https://api.bentoforbusiness.com/cards?index=0&limit=10000"
        headers = {
            "Authorization": GetToken()
        }
        params = {
            "cardName": "{}".format(alias),
        }
        try:
            r = self.requests.get(url=url, headers=headers, params=params, timeout=30)
            for i in r.json().get("cards"):
                if i.get("alias") == str(alias):
                    return i.get("availableAmount")
        except Exception as e:
            logging.warning(str(e))
            self.one_alias(alias)


recharge = RechargeCard()
SqlData_bento = SqlData('bento')


async def remain_trans(alias, card_id, card_number, user_name):
    try:
        remain = recharge.one_alias(alias)
        trans = recharge.transaction_data(card_id)
        if remain is None:
            remain = 0
        currency_status = '是'
        card_real_pay = 0
        if len(trans) > 0:
            for tran in trans:
                amount = tran.get('amount')
                status = tran.get('status')
                currency = tran.get('originalCurrency')
                if status != "DECLINED":
                    card_real_pay += abs(amount)
                if currency != "USD":
                    currency_status = '否'
        top_money = SqlData_bento.search_out_trans(card_number)
        re_money = SqlData_bento.search_recycle_trans(card_number)
        remain = round(remain, 2)
        card_real_pay = round(card_real_pay, 2)
        if not round(top_money - re_money - card_real_pay, 2) != remain:
            diff_balance = round(top_money - re_money - card_real_pay, 2) - remain
            s = '{},{},{},{},{},{},{},{},{}'.format(remain, currency_status, card_real_pay, top_money, re_money, card_number, alias, user_name, diff_balance)
            print(s)
            with open('check.txt', 'a', encoding='utf-8') as f:
                f.write(s + "\n")
    except Exception as e:
        print('卡号: {} 异常'.format(card_number) + str(e))


def exchange_rate_conversion(from_currency, to_currency, money):
    url = "https://qq.ip138.com/hl.asp?from={}&to={}&q={}".format(from_currency, to_currency, money)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/80.0.3987.149 Safari/537.36',
        'Referer': 'https://qq.ip138.com/'
    }
    try:
        response = requests.get(url, headers=headers)
        money = re.findall('<p>([1-9]\d*\.\d*|0\.\d*[1-9]\d*)</p>', response.text)
        return money[-1]
    except Exception as e:
        print("交易货币汇率异常" + str(e))
        exchange_rate_conversion(from_currency, to_currency, money)


SqlData = SqlData('bento_card')

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    card_info = SqlData.search_card_data()
    print(card_info)
    with open('check.txt', 'a', encoding='utf-8') as f:
        f.write('卡余额,全部美元,卡总支出,卡总充值,总退款,卡号,卡名,用户,差额' + "\n")
    for card_one in card_info:
        alias = card_one[0]
        card_id = card_one[1]
        card_number = card_one[2]
        user_name = card_one[3]
        loop.run_until_complete(remain_trans(alias, card_id, card_number, user_name))

