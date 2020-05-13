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

    def search_card_name(self):
        sql = "SELECT card_name FROM card_name WHERE status is NULL;"
        self.cursor.execute(sql)
        rows = self.cursor.fetchone()
        return rows[0]

    def update_name_status(self, card_name):
        sql = "UPDATE card_name SET status = 'T' WHERE card_name = '{}'".format(card_name)
        try:
            self.cursor.execute(sql)
            self.connect.commit()
        except Exception as e:
            self.connect.rollback()
            return False
        return True

    def update_card_field(self, field, value, card_id):
        sql = "UPDATE new_card SET  {}= '{}' WHERE card_id = '{}'".format(field, value, card_id)
        try:
            self.cursor.execute(sql)
            self.connect.commit()
        except Exception as e:
            self.connect.rollback()
            return False
        return True

    def search_card_num(self, amount, status):
        sql = "SELECT COUNT(*) FROM new_card WHERE card_amount = {} AND card_status='{}'".format(amount, status)
        self.cursor.execute(sql)
        rows = self.cursor.fetchone()
        return rows[0]

    def search_fail_card(self):
        sql = "SELECT * FROM new_card WHERE card_number='None' OR card_cvv='None' OR  card_validity='None'"
        self.cursor.execute(sql)
        rows = self.cursor.fetchall()
        return rows

    def search_card_info(self, amount):
        sql = "SELECT * FROM new_card WHERE card_amount = {} AND card_status='' ORDER BY rand() limit 1".format(amount)
        self.cursor.execute(sql)
        rows = self.cursor.fetchone()
        return rows

    def insert_card(self, alias, card_id, card_number, card_amount, card_cvv, card_validity):
        sql = "INSERT INTO new_card(alias, card_id, card_number, card_amount, card_cvv, card_validity) VALUES ('{}'," \
              " '{}', '{}', {}, '{}', '{}')".format(alias, card_id, card_number, card_amount, card_cvv, card_validity)
        try:
            self.cursor.execute(sql)
            self.connect.commit()
        except Exception as e:
            self.connect.rollback()
            return False
        return True

    def update_card_status(self, card_id):
        sql = "UPDATE new_card SET status = 'T' WHERE card_id = '{}'".format(card_id)
        try:
            self.cursor.execute(sql)
            self.connect.commit()
        except Exception as e:
            self.connect.rollback()
            return False
        return True


sqldata = SqlData()

if __name__ == '__main__':

    # 根据需求创建缓存卡
    user_card_num = sqldata.search_card_num(10, '')
    create_num = 1
    new_card = 20 - user_card_num
    while create_num <= new_card:
        card_name = sqldata.search_card_name()
        r = bento.create_card(card_name, 10)
        if r:
            sqldata.update_name_status(card_name)
            alias = r.get('alias')
            cardId = r.get('cardId')
            card_amount = r.get('card_amount')
            expiration = r.get('expiration')
            pan = r.get('pan')
            cvv = r.get('cvv')
            sqldata.insert_card(alias, cardId, pan, card_amount, cvv, expiration)
            create_num += 1

    # 补全开卡没返回卡号的卡信息
    up_num = 0
    while up_num < 5:
        fail = sqldata.search_fail_card()
        for i in fail:
            card_id = i[2]
            if i[3] == "None" or i[5]:
                res = bento.get_pan(card_id)
                card_number = res.get('pan')
                sqldata.update_card_field('card_number', card_number, card_id)
                cvv = res.get('cvv')
                sqldata.update_card_field('card_cvv', cvv, card_id)
            if i[6] == "None":
                res = bento.get_expiration(card_id)
                expiration = res.get('expiration')
                sqldata.update_card_field('card_validity', expiration, card_id)
        up_num += 1

