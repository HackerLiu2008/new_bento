import requests
import json
import time
from tools_me.bento_token import GetToken
from apps.bento_create_card.sqldata_native import SqlDataNative
from requests.adapters import HTTPAdapter


class CreateCard(object):
    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
            "authorization": GetToken(),
            "Connection": "close"
        }
        requests.adapters.DEFAULT_RETRIES = 5
        self.requests = requests.session()
        self.requests.keep_alive = False

    def create_card(self, card_alias, card_amount, label, attribution):
        user_data = {}
        url = "https://api.bentoforbusiness.com/cards"
        try:
            r = self.requests.post(url=url, data=json.dumps(
                bento_data(card_alias=card_alias, card_amount=card_amount, attribution=attribution)), headers=self.headers, verify=False, timeout=14)
            user_data["alias"] = r.json().get("alias")
            user_data["cardId"] = r.json().get("cardId")
            user_data["card_amount"] = card_amount
            if user_data.get("cardId"):
                pan_data = self.get_pan(cardid=user_data.get("cardId"))
                user_data.update(pan_data)
                expriation_data = self.get_expiration(cardid=user_data.get("cardId"))
                user_data.update(expriation_data)
                # update alias card_id, card_amount
                SqlDataNative.insert_new_account(alias=user_data.get("alias"), card_id=user_data.get("cardId"),
                                                   card_amount=card_amount, card_number=user_data.get("pan"),
                                                   card_cvv=user_data.get("cvv"), label=label,
                                                   card_validity=user_data.get("expiration"), attribution=attribution,
                                                   create_time=time.strftime('%Y-%m-%d %H:%M:%S',
                                                                             time.localtime(time.time())))
                self.billing_address(user_data.get("cardId"))
            return user_data
        except Exception as e:
            return False

    # 获取pan cvv
    def get_pan(self, cardid):
        url = "https://api.bentoforbusiness.com/cards/{}/pan".format(cardid)
        response = self.requests.get(url=url, headers=self.headers, verify=False, timeout=14)
        return {
            "pan": response.json().get("pan"),
            "cvv": response.json().get("cvv")
        }

    # 获取有效期
    def get_expiration(self, cardid):
        url = "https://api.bentoforbusiness.com/cards/{}".format(cardid)
        response = self.requests.get(url=url, headers=self.headers, verify=False, timeout=14)
        return {
            "expiration": response.json().get("expiration")
        }

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
        print(url)
        respone = requests.put(url, headers=self.headers, data=json.dumps(data), verify=False, timeout=14)
        print(respone.text)
        print(respone.status_code)
        if respone.status_code == 200:
            return True
        else:
            return False

    def get_card_list(self):
        url = "https://api.bentoforbusiness.com/cards?index=0&limit=0"
        res = self.requests.get(url, headers=self.headers, verify=False, timeout=14)
        crads = res.json().get('cards')
        # 返回未注销的所有卡信息(详细信息参数api文档card-list接口)

# 单张开卡
def main_createcard(limit_num, card_amount, label, attribution):
    """
    :param limit_num:开卡的数量
    :param card_amount: 开卡的金额
    :param label: 开卡的备注
    :return: 返回开卡的数据并入库
    """
    for i in SqlDataNative.search_data(limit_num=limit_num):
        c = CreateCard().create_card(card_alias=i.get("username"), card_amount=card_amount, label=label,
                                     attribution=attribution)
        return c


def get_bento_data(cardid):
    pan = CreateCard().get_pan(cardid)
    expiration = CreateCard().get_expiration(cardid)
    return {
        "pan": pan.get("pan"),
        "cvv": pan.get("cvv"),
        "expiration": expiration.get("expiration"),
    }


if __name__ == "__main__":
    s = CreateCard()
    r = s.billing_address(1081270)
    print(r)
    # main(limit_num=3, card_amount=300, label="杨经理kevin")
    pass
