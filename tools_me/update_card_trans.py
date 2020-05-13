import pymysql
from tools_me.bento_api import bento


class SqlData(object):
    def __init__(self):
        host = "127.0.0.1"
        port = 3306
        user = "root"
        # password = "gute123"
        password = "admin"
        database = "new_bento"
        self.connect = pymysql.Connect(
            host=host, port=port, user=user,
            passwd=password, db=database,
            charset='utf8'
        )
        self.cursor = self.connect.cursor()

    def close_connect(self):
        if self.cursor:
            self.cursor.close()
        if self.connect:
            self.connect.close()

    def __del__(self):
        self.close_connect()

    def insert_card_trans(self, card_number, card_id, alias, description, transaction_hour, amount,
                          transaction_status, transaction_id, currency, user_id):
        sql = "INSERT INTO card_trans(card_number, card_id, alias, description, transaction_hour, amount, " \
              "transaction_status, transaction_id, currency, user_id) VALUES ('{}','{}','{}','{}','{}',{},'{}'" \
              ",{},'{}',{});".format(card_number, card_id, alias, description, transaction_hour, amount,
                                     transaction_status, transaction_id, currency, user_id)
        try:
            self.cursor.execute(sql)
            self.connect.commit()
        except Exception as e:
            self.connect.rollback()
            return False
        return True

    def update_card_trans(self, trans_time, amount, transaction_status, currency, transaction_id):
        sql = "UPDATE card_trans SET transaction_hour = '{}' ,amount = {}, transaction_status='{}', currency='{}' " \
              "WHERE transaction_id = {}".format(trans_time, amount, transaction_status, currency, transaction_id)
        try:
            self.cursor.execute(sql)
            self.connect.commit()
        except Exception as e:
            self.connect.rollback()
            return False
        return True

    def search_card_info(self):
        sql = "SELECT card_id, card_number, user_id FROM card_info WHERE card_status='T';"
        self.cursor.execute(sql)
        rows = self.cursor.fetchall()
        return rows


SqlData = SqlData()

if __name__ == '__main__':
    card_info = SqlData.search_card_info()
    for card in card_info:
        card_number = card[1]
        cardid = card[0]
        user_id = card[2]
        trans_data = bento.transaction_data(cardid)
        if not trans_data:
            continue
        for trans in trans_data:
            trans_time = trans.get('date')
            description = trans.get('description')
            alias = trans.get('alias')
            amount = trans.get('amount')
            status = trans.get('status')
            transaction_id = trans.get('cardTransactionId')
            currency = trans.get('originalCurrency')
            res = SqlData.insert_card_trans(card_number, cardid, alias, description, trans_time, amount, status, transaction_id, currency, user_id)
            if not res:
                up_res = SqlData.update_card_trans(trans_time, amount, status, currency, transaction_id)
                print(up_res)
