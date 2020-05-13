import datetime
import requests
import json
import time
from tools_me.bento_token import GetToken
from requests.adapters import HTTPAdapter
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s :: %(levelname)s :: %(message)s', filename="bentoapi.log")


'''
以下是BENTOAPI需要调用处理数据的一些方法
'''

def get_time():
    customStartDate = int(round(time.time() * 1000))
    t = datetime.datetime.now()
    t2 = (t + datetime.timedelta(days=365)).strftime("%Y-%m-%d 00:00:00")
    customEndDate = int(time.mktime(time.strptime(t2, "%Y-%m-%d %H:%M:%S"))) * 1000
    return customStartDate, customEndDate


def bento_data(card_alias, card_amount):
    customStartDate, customEndDate = get_time()
    data = {
        "type": "CategoryCard",
        "virtualCard": True,
        "shippingMethod": "STANDARD",
        "blockInternationalTransactions": False,
        "blockOnlineTransactions": False,
        "allowedDaysActive": False,
        "allowedCategoriesActive": False,
        "alias": card_alias,
        "spendingLimit": {
            "active": True,
            "amount": card_amount,
            "period": "Custom",
            "customStartDate": customStartDate,
            "customEndDate": customEndDate},
        "allowedDays": [
            "MONDAY", "TUESDAY",
            "WEDNESDAY", "THURSDAY",
            "FRIDAY", "SATURDAY", "SUNDAY"],
        "allowedCategories": [
            {"transactionCategoryId": 7, "name": "Business Services", "type": "SPENDING", "group": "Services",
             "description": "Photography, Secretarial, Computer Consulting, etc.", "mccs": [],
             "bentoType": "com.bentoforbusiness.entity.card.TransactionCategory", "id": 7},

            {"transactionCategoryId": 8, "name": "Professional Services", "type": "SPENDING", "group": "Services",
             "description": "Insurance, Legal, Real Estate, Doctors, Medical, etc.", "mccs": [],
             "bentoType": "com.bentoforbusiness.entity.card.TransactionCategory", "id": 8},

            {"transactionCategoryId": 16, "name": "Financial Services", "type": "SPENDING", "group": "Services",
             "description": "Money order, OTC Cash Disbursement, etc.", "mccs": [],
             "bentoType": "com.bentoforbusiness.entity.card.TransactionCategory", "id": 16},

            {"transactionCategoryId": 17, "name": "Amusement and Entertainment", "type": "SPENDING",
             "group": "Food & Drink", "description": "Movie Theaters, Pool Halls, Bowling Alleys, etc.", "mccs": [],
             "bentoType": "com.bentoforbusiness.entity.card.TransactionCategory", "id": 17}
        ],
        "billingAddress":
            {
                "id": 91308,
                "street": "1709 Elmwood Dr",
                "city": "Harlingen",
                "country": "US",
                "zipCode": "78550",
                "state": "TX",
                "addressType": "BUSINESS_ADDRESS",
                "bentoType": "com.bentoforbusiness.entity.business.BusinessAddress"
            }
    }
    return data


class BentoCard(object):

    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
            "authorization": GetToken(),
            "Connection": "close"
        }
        requests.adapters.DEFAULT_RETRIES = 5
        self.requests = requests.session()
        self.requests.keep_alive = False

    def create_card(self, card_alias, card_amount):
        user_data = {}
        url = "https://api.bentoforbusiness.com/cards"
        try:
            r = self.requests.post(url=url, data=json.dumps(
                bento_data(card_alias=card_alias, card_amount=card_amount, )), headers=self.headers, verify=False, timeout=14)
            user_data["alias"] = r.json().get("alias")
            user_data["cardId"] = r.json().get("cardId")
            user_data["card_amount"] = card_amount
            if user_data.get("cardId"):
                pan_data = self.get_pan(cardid=user_data.get("cardId"))
                user_data.update(pan_data)
                expriation_data = self.get_expiration(cardid=user_data.get("cardId"))
                user_data.update(expriation_data)
            return user_data
        except Exception as e:
            logging.error("创建卡失败: " + str(e))
            return False

    # 获取pan cvv
    def get_pan(self, cardid):
        url = "https://api.bentoforbusiness.com/cards/{}/pan".format(cardid)
        try:
            response = self.requests.get(url=url, headers=self.headers, verify=False, timeout=14)
            return {
                "pan": response.json().get("pan"),
                "cvv": response.json().get("cvv")
            }
        except:
            return {}

    # 获取有效期
    def get_expiration(self, cardid):
        url = "https://api.bentoforbusiness.com/cards/{}".format(cardid)
        try:
            response = self.requests.get(url=url, headers=self.headers, verify=False, timeout=14)
            return {
                "expiration": response.json().get("expiration")
            }
        except:
            return {}

    def billing_address(self, card_id):
        url = "https://api.bentoforbusiness.com/cards/{}/billingaddress ".format(card_id)
        data = {
                "id": 91308,
                "street": "1709 Elmwood Dr",
                "city": "Harlingen",
                "country": "US",
                "zipCode": "78550",
                "state": "TX",
                "addressType": "BUSINESS_ADDRESS",
                "bentoType": "com.bentoforbusiness.entity.business.BusinessAddress"
            }
        respone = requests.put(url, headers=self.headers, data=json.dumps(data), verify=False, timeout=14)
        if respone.status_code == 200:
            return True
        else:
            return False

    def get_card_list(self):
        url = "https://api.bentoforbusiness.com/cards?index=0&limit=0"
        res = self.requests.get(url, headers=self.headers, verify=False, timeout=14)
        crads = res.json().get('cards')
        return crads
        # 返回未注销的所有卡信息(详细信息参数api文档card-list接口)

    def card_ava(self, alias):
        url = "https://api.bentoforbusiness.com/cards?index=0&limit=10000"
        headers = {
            "Authorization": GetToken()
        }
        params = {
            "cardName": "{}".format(alias),
        }
        try:
            r = self.requests.get(url=url, headers=headers, params=params, verify=False, timeout=14)
            info = r.json().get("cards")
            if len(info) == 0:
                return '卡已注销'
            for i in info:
                if i.get("alias") == str(alias):
                    remain = i.get("availableAmount")
                    return remain
                else:
                    return '查询异常'
        except Exception as e:
            logging.warning(str(e))
            return False

    def recharge(self, cardid, recharge_amount, due_remain):
        url = "https://api.bentoforbusiness.com/cards/{}".format(cardid)
        try:
            response = self.requests.get(url=url, headers=self.headers, timeout=15, verify=False)
            data = response.json()
            # 获取用户可用余额
            availableAmount = data.get("availableAmount")
            spendlimit = data.get("spendingLimit").get('amount')
            # 真实余额必须是等于或者小于理论余额的， 大于就是充值的同时产生消费了，小于是因为产生了手续费没有交易记录
            # 所以比较大小总以小的余额去做添加余额更新
            if availableAmount > due_remain:
                limit = due_remain + recharge_amount
            elif availableAmount < due_remain:
                limit = availableAmount + recharge_amount
            else:
                limit = availableAmount + recharge_amount
            limit = round(limit, 2)
            data["spendingLimit"]["amount"] = limit
            response = self.requests.put(url=url, headers=self.headers, data=json.dumps(data), timeout=15, verify=False)
            if response.status_code == 200:
                data = response.json()
                new_limit = data.get('spendingLimit').get('amount')
                new_available = data.get("availableAmount")
                msg = "充值前: availableAmount:{},spendingLimit:{};充值后: availableAmount:{},spendingLimit:" \
                      "{};充值金额: {}".format(availableAmount, spendlimit, new_available, new_limit, recharge_amount)
                return {'code': 200, 'msg': msg}
        except Exception as e:
            logging.error('充值卡失败：' + str(e))
            # 记录格式：时间，card_id, 类型（充值， 退款， 删卡），成功/失败，内容（）
            return {'code': 500, 'msg': '充值失败，调用API超时异常'}

    def refund(self, cardid, recharge_amount, due_remain):
        url = "https://api.bentoforbusiness.com/cards/{}".format(cardid)
        try:
            response = self.requests.get(url=url, headers=self.headers, timeout=15, verify=False)
            data = response.json()
            # 获取用户可用余额
            availableAmount = data.get("availableAmount")
            spendlimit = data.get("spendingLimit").get('amount')
            # print(availableAmount, spendlimit)
            # 真实余额必须是等于或者小于理论余额的， 大于就是充值的同时产生消费了，小于是因为产生了手续费没有交易记录
            # 所以比较大小总以小的余额去做添加余额更新
            if availableAmount > due_remain:
                limit = due_remain + recharge_amount
                # 记录退款是以哪个余额为准
                remain = due_remain
            elif availableAmount < due_remain:
                limit = availableAmount + recharge_amount
                remain = availableAmount
            else:
                limit = availableAmount + recharge_amount
                # 记录退款是以哪个余额为准
                remain = availableAmount
            limit = round(limit, 2)

            if limit < 10:
                return {'code': 400, 'msg': '退款后卡余额必须大于10; 卡余额: {}, 退款金额:{},卡退款后理论余额: {}'.format(remain, abs(recharge_amount), limit)}
            data["spendingLimit"]["amount"] = limit
            response = self.requests.put(url=url, headers=self.headers, data=json.dumps(data), timeout=15, verify=False)
            if response.status_code == 200:
                data = response.json()
                new_limit = data.get('spendingLimit').get('amount')
                new_available = data.get("availableAmount")
                msg = "退款前: availableAmount:{},spendingLimit:{};退款后: availableAmount:{},spendingLimit:" \
                      "{};退款金额: {}".format(availableAmount, spendlimit, new_available, new_limit, recharge_amount)
                return {'code': 200, 'msg': msg}
        except Exception as e:
            logging.error('充值卡失败：' + str(e))
            # 记录格式：时间，card_id, 类型（充值， 退款， 删卡），成功/失败，内容（）
            return {'code': 500, 'msg': '退款失败，调用API超时异常'}

    # 使用递归多次查询大于500条交易记录的卡交易数据
    def transaction_data(self, card_id, end_time=0, transactions_datas=None):
        url = "https://api.bentoforbusiness.com/transactions"
        params = {
            "cards": "{}".format(card_id),
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
                    "date": time.strftime("%Y-%m-%d %H:%M:%S",
                                          time.localtime(transactions.get("transactionDate") / 1000)),
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
                transactions_datas = self.transaction_data(card_id, date, transactions_datas)
            return transactions_datas
        except Exception as e:
            logging.error('交易记录请求超时！' + str(e))
            return False

    def del_card(self, cardid):
        try:
            url = "https://api.bentoforbusiness.com/cards/{}".format(cardid)
            r = self.requests.delete(url=url, headers=self.headers, verify=False, timeout=14)
            if r.status_code == 204:
                return 200
            else:
                return 404
        except Exception as e:
            logging.warning(str(e))
            return 404


bento = BentoCard()

if __name__ == "__main__":
    s = bento.del_card(1121854)
    print(s)
    # main(limit_num=3, card_amount=300, label="杨经理kevin")
    pass
