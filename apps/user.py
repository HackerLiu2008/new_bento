import json
import datetime
import logging
import operator
import os
import re
import time
import uuid
from concurrent.futures.thread import ThreadPoolExecutor
from tools_me.bento_api import bento
from tools_me.other_tools import xianzai_time, login_required, check_float, account_lock, dic_key, sum_code, trans_lock, create_card, get_nday_list
from tools_me.parameter import RET, MSG, TRANS_TYPE, DO_TYPE, DIR_PATH
from tools_me.redis_tools import RedisTool
from tools_me.remain import get_card_remain
from tools_me.send_email import send
from tools_me.img_code import createCodeImage
from tools_me.des_code import ImgCode
from . import user_blueprint
from flask import render_template, request, jsonify, session, g, redirect
from tools_me.mysql_tools import SqlData
from apps.bento_create_card.main_create_card import main_createcard, CreateCard, get_bento_data
from apps.bento_create_card.main_recharge import main_transaction_data, RechargeCard

logging.basicConfig(level=logging.INFO, format='%(asctime)s :: %(levelname)s :: %(message)s', filename="error.log")


executor = ThreadPoolExecutor(5)


@user_blueprint.route('/pay_pic/', methods=['GET', 'POST'])
@login_required
def pay_pic():
    if request.method == 'GET':
        sum_money = request.args.get('sum_money')
        top_money = request.args.get('top_money')
        ex_change = request.args.get('ex_change')
        # 取出目前当前收款金额最低的收款码
        qr_info = SqlData.search_qr_code('WHERE status=0')
        if not qr_info:
            url = ''
        else:
            url = ''
            value_list = list()
            for i in qr_info:
                value_list.append(i.get('sum_money'))
            value = min(value_list)
            for n in qr_info:
                money = n.get('sum_money')
                if value == money:
                    url = n.get('qr_code')
                    break
        context = dict()
        bank_top_data = SqlData.search_bank_info(sql_line='WHERE status=2')
        if bank_top_data:
            data = bank_top_data[0]
            context['bank_name'] = data.get('bank_name')
            context['bank_number'] = data.get('bank_number')
            context['bank_address'] = data.get('bank_address')
        else:
            # 一下三个循环和判断为处理相同收款人，多个账号，取低于累计20万的中的最小收款账号
            bank_data = SqlData.search_bank_info(sql_line='WHERE status=0')
            # bank_info 整理为一个收款人对应多个收款卡号 {'':[],'':[]} 格式
            bank_info = dict()
            for n in bank_data:
                bank_name = n.get('bank_name')
                if bank_name in bank_info:
                    info_list = bank_info.get(bank_name)
                    info_list.append(n)
                else:
                    info_list = list()
                    info_list.append(n)
                    bank_info[bank_name] = info_list
            # sum_money_dict 为统计一个账号一共充值了多少元
            sum_money_dict = dict()
            for i in bank_info:
                value = bank_info.get(i)
                money = 0
                for m in value:
                    money += float(m.get('day_money'))
                sum_money_dict[i] = money
            # min_dict 为取出满足累计收款低于20万的账户，且最小的充值战账户
            min_dict = dict()
            for acc in sum_money_dict:
                if sum_money_dict.get(acc) < 200000:
                    min_dict[acc] = sum_money_dict.get(acc)
            if len(min_dict) == 0:
                context['bank_name'] = '无符合要求收款账户！'
                context['bank_number'] = '请联系管理员处理！'
                context['bank_address'] = '-------------'
            else:
                # 在最小充值账户中取出最小收款卡号推送
                min_acc = min(zip(min_dict.values(), min_dict.keys()))
                min_acc = min_acc[1]
                acc_list = bank_info.get(min_acc)
                data = min(acc_list, key=dic_key)
                context['bank_name'] = data.get('bank_name')
                context['bank_number'] = data.get('bank_number')
                context['bank_address'] = data.get('bank_address')

        context['sum_money'] = sum_money
        context['top_money'] = top_money
        context['url'] = url
        context['ex_change'] = ex_change
        return render_template('user/pay_pic.html', **context)
    if request.method == 'POST':
        '''
        获取充值金额, 保存付款截图. 发送邮件通知管理员
        '''
        # try:
        # 两组数据,1,表单信息充值金额,等一下客户信息 2,截图凭证最多可上传5张
        # print(request.form)
        # print(request.files)
        data = json.loads(request.form.get('data'))
        top_money = data.get('top_money')
        sum_money = data.get('sum_money')
        exchange = data.get('exchange')
        url = json.loads(request.form.get('url'))
        change_type = json.loads(request.form.get("change_type"))
        bank_name = json.loads(request.form.get("bank_name"))
        bank_number = json.loads(request.form.get("bank_number"))
        bank_address = json.loads(request.form.get("bank_address"))
        results = {'code': RET.OK, 'msg': MSG.OK}
        cus_name = g.user_name
        cus_id = g.user_id
        cus_account = SqlData.search_user_field_name('account', cus_name)
        phone = SqlData.search_user_field_name('phone_num', cus_name)
        try:
            # 保存所有图片
            file_n = 'file_'
            pic_list = list()
            # 判断有无上传图片
            f_obj = request.files.get("{}{}".format(file_n, 1))
            if not f_obj:
                return jsonify({'code': RET.SERVERERROR, 'msg': "请先上传图片再操作"})
            for i in range(5):
                file_name = "{}{}".format(file_n, i + 1)
                fileobj = request.files.get(file_name)
                if fileobj:
                    now_time = sum_code()
                    file_name = cus_account + "_" + str(now_time) + str(i) + ".png"
                    file_path = os.path.join(DIR_PATH.PHOTO_DIR, file_name)
                    fileobj.save(file_path)
                    with open(file_path, 'rb') as f:
                        c = f.read()
                        if b'Adobe Photoshop' in c:
                            logging.error('上传PS的图片可客户名称：' + cus_name)
                            return jsonify({'code': RET.SERVERERROR, 'msg': "图片存在异常，请勿使用PS截图凭证！"})
                    pic_list.append(file_path)
            n_time = xianzai_time()
            vir_code = str(uuid.uuid1())[:6]
            context = "客户:  " + cus_name + " , 于<span style='color:red'>" + n_time + "</span>在线申请充值: " \
                      + top_money + "美元, 折和人名币: <span style='color:red'>" + sum_money + "</span>元。本次计算汇率为: " + exchange + ", 验证码为: " + vir_code

            sum_money = float(sum_money)
            top_money = float(top_money)
            if change_type == "pic":
                SqlData.insert_pay_log(n_time, sum_money, top_money, vir_code, '待充值', phone, url, cus_id)
            elif change_type == "bank":
                SqlData.insert_pay_log(n_time, sum_money, top_money, vir_code, '待充值', phone,
                                         "{},{},{}".format(bank_name, bank_number, bank_address), cus_id)
            # 获取要推送邮件的邮箱
            top_push = SqlData.search_admin_field('top_push')
            top_dict = json.loads(top_push)
            email_list = list()
            for i in top_dict:
                email_list.append(top_dict.get(i))
            for p in email_list:
                executor.submit(send, context, pic_list, p)
                # send(context, pic_list, p)

            return jsonify(results)
        except Exception as e:
            logging.error(str(e))
            return jsonify({'code': RET.SERVERERROR, 'msg': str(e)})


@user_blueprint.route('/user_top/', methods=['GET', 'POST'])
@login_required
def user_top():
    if request.method == 'GET':
        ex_change = SqlData.search_admin_field('ex_change')
        ex_range = SqlData.search_admin_field('ex_range')
        hand = SqlData.search_admin_field('hand')
        dollar_hand = SqlData.search_admin_field('dollar_hand')
        context = dict()
        context['ex_change'] = ex_change
        context['ex_range'] = ex_range
        context['hand'] = hand
        context['dollar_hand'] = dollar_hand
        return render_template('user/pay_top.html', **context)
    if request.method == 'POST':
        '''
        1:校验前端数据是否正确
        2:查看实时汇率有没有变动
        3:核实客户是否存在
        '''
        data = json.loads(request.form.get('data'))
        sum_money = data.get('sum_money')
        top_money = data.get('top_money')
        if float(top_money) < 100:
            return jsonify({'code': RET.SERVERERROR, 'msg': '充值金额不能小于100$'})

        ex_change = SqlData.search_admin_field('ex_change')
        ex_range = SqlData.search_admin_field('ex_range')
        hand = SqlData.search_admin_field('hand')
        _money_self = float(top_money) * (ex_change + ex_range) * (hand + 1)
        money_self = round(_money_self, 10)
        sum_money = round(float(sum_money), 10)
        if money_self == sum_money:
            return jsonify({'code': RET.OK, 'msg': MSG.OK})
        else:
            return jsonify({'code': RET.SERVERERROR, 'msg': '汇率已变动!请刷新界面后重试!'})


@user_blueprint.route('/del_vice/', methods=['GET'])
@login_required
@account_lock
def del_vice():
    vice_id = request.args.get('vice_id')
    SqlData.del_vice(int(vice_id))
    RedisTool.hash_del('vice_auth', int(vice_id))
    return jsonify({'code': RET.OK, 'msg': MSG.OK})


@user_blueprint.route('/up_auth/', methods=['GET'])
@login_required
@account_lock
def up_auth():
    '处理正在使用的客户被删除的问题'
    vice_id = request.args.get('vice_id')
    field = request.args.get('field')
    check = request.args.get('check')
    value = request.args.get('value')
    if check:
        field_status = ''
        if check == "true":
            field_status = 'T'
        elif check == 'false':
            field_status = 'F'
        SqlData.update_vice_field(field, field_status, int(vice_id))
        res = SqlData.search_one_acc_vice(vice_id)
        RedisTool.hash_set('vice_auth', res.get('vice_id'), res)
        return jsonify({'code': RET.OK, 'msg': MSG.OK})
    if value:
        if field == "v_account":
            if SqlData.search_value_in('vice_account', value, field):
                return jsonify({'code': RET.SERVERERROR, 'msg': '用户名已存在,请重新命名！'})
        SqlData.update_vice_field(field, value, int(vice_id))
        return jsonify({'code': RET.OK, 'msg': MSG.OK})


@user_blueprint.route('/vice_info/', methods=['GET', 'POST'])
@login_required
@account_lock
def vice_info():
    if request.method == 'GET':
        user_id = g.user_id
        res = SqlData.search_acc_vice(user_id)
        resluts = dict()
        resluts['code'] = RET.OK
        resluts['msg'] = MSG.OK
        resluts['data'] = res
        return jsonify(resluts)


@user_blueprint.route('/update_vice/', methods=['GET', 'POST'])
@login_required
@account_lock
def update_vice():
    if request.method == 'GET':
        vice_id = g.vice_id
        if vice_id:
            return render_template('user/no_auth.html')
        return render_template('user/vice_acc_list.html')


@user_blueprint.route('/add_vice/', methods=['POST'])
@login_required
@account_lock
def add_vice():
    if request.method == 'POST':
        try:
            # 判断是否是子账号用户
            vice_id = g.vice_id
            print(vice_id)
            if vice_id:
                return {'code': RET.SERVERERROR, 'msg': MSG.NOAUTH}
            user_id = g.user_id
            data = json.loads(request.form.get('data'))
            v_account = data.get('account')
            v_password = data.get('password')
            c_card = data.get('c_card')
            top_up = data.get('top_up')
            refund = data.get('refund')
            del_card = data.get('del_card')
            up_label = data.get('up_label')
            account = v_account.strip()
            password = v_password.strip()
            if len(account) < 6 or len(password) < 6:
                return jsonify({"code": RET.SERVERERROR, 'msg': '账号或密码长度小于6位！'})
            # 判断用户选择可哪些权限开启
            c_card_status = 'T' if c_card else 'F'
            top_up_status = 'T' if top_up else 'F'
            refund_status = 'T' if refund else 'F'
            del_card_status = 'T' if del_card else 'F'
            up_label_status = 'T' if up_label else 'F'
            res = SqlData.search_vice_count(user_id)
            # 判断是否已经添加子账号，已添加则更新
            if res < 3:
                if SqlData.search_value_in('vice_user', account, 'v_account'):
                    return jsonify({'code': RET.SERVERERROR, 'msg': '用户名已存在,请重新命名！'})
                SqlData.insert_account_vice(account, password, c_card_status, top_up_status, refund_status, del_card_status, up_label_status, user_id)
                vice_id = SqlData.search_vice_id(v_account)
                res = SqlData.search_one_acc_vice(vice_id)
                RedisTool.hash_set('new_vice_auth', res.get('vice_id'), res)
                return jsonify({'code': RET.OK, 'msg': MSG.OK})
            else:
                return jsonify({'code': RET.SERVERERROR, 'msg': '您的账号已添加3个子账号，不可重复添加！'})
        except Exception as e:
            print(e)


@user_blueprint.route('/refund/', methods=['POST'])
@login_required
@account_lock
@trans_lock
def bento_refund():
    # 判断是否是子账号用户
    vice_id = g.vice_id
    if vice_id:
        auth_dict = RedisTool.hash_get('vice_auth', vice_id)
        if auth_dict is None:
            return jsonify({'code': RET.SERVERERROR, 'msg': '抱歉您没有权限执行此操作！'})
        c_card = auth_dict.get('refund')
        if c_card == 'F':
            return jsonify({'code': RET.SERVERERROR, 'msg': '抱歉您没有权限执行此操作！'})
    refund_money = request.form.get("data")
    card_no = request.form.get("card_no").strip()
    user_id = g.user_id
    if "-" in str(refund_money):
        return jsonify({"code": RET.SERVERERROR, 'msg': "请输入正确金额!"})
    card_id = SqlData.search_card_field('card_id', card_no)
    if not card_id:
        return jsonify({"code": RET.SERVERERROR, "msg": "卡已注销"})

    if card_id:
        # 判断是不是当前用户的卡
        now_user = SqlData.search_card_field('user_id', card_no)
        if now_user != user_id:
            results = {"code": RET.SERVERERROR, "msg": "不要违规操作"}
            return jsonify(results)
    alias = SqlData.search_card_field('alias', card_no)
    # 查询卡的消费记录计算总支出金额
    card_trans = bento.transaction_data(card_id)
    card_real_pay = 0
    if isinstance(card_trans, list):
        if len(card_trans) > 0:
            for tran in card_trans:
                amount = tran.get('amount')
                status = tran.get('status')
                if status != "DECLINED":
                    card_real_pay += amount
    else:
        results = {"code": RET.SERVERERROR, "msg": "退款失败，请重试"}
        return jsonify(results)

    # 计算在平台上一共给这个卡充值了多少钱
    sum_top = SqlData.search_out_trans(card_no)
    sum_refund = SqlData.search_recycle_trans(card_no)
    # 相加是因为支出是以负数形式存进数据库， 再取绝对值，就是卡总充值的金额
    due_top = round(abs(sum_top + sum_refund), 2)

    # 卡消费中有正数负数，正数为退款收到的金额，负数为交易扣除的金额，所以也是相加取绝对值，为开始总真实花费的金额
    card_real_pay = round(abs(card_real_pay), 2)
    # 卡总充值-卡总真实花费的=理论卡上还有的余额
    due_remain = round(due_top - card_real_pay, 2)

    # 调用api退款
    refund_money = float(refund_money)
    result = bento.refund(card_id, -round(refund_money, 2), due_remain)
    code = result.get('code')
    msg = result.get('msg')
    n_time = xianzai_time()
    if code == 400:
        SqlData.insert_operating_log(n_time, card_id, '退款', '失败', msg)
        return jsonify({"code": RET.SERVERERROR, "msg": "退款失败，卡内最少保留$10"})

    elif code == 500:
        SqlData.insert_operating_log(n_time, card_id, '退款', '失败', msg)
        return jsonify({"code": RET.SERVERERROR, "msg": '退款失败请重试'})

    elif code == 200:
        before_balance = SqlData.search_user_field('balance', user_id)
        SqlData.update_balance(round(refund_money, 2), user_id)
        balance = SqlData.search_user_field("balance", user_id)

        n_time = xianzai_time()
        SqlData.insert_user_trans(n_time, TRANS_TYPE.IN, DO_TYPE.REFUND, alias, card_no, round(refund_money, 2),
                                  before_balance, balance, user_id)
        SqlData.insert_operating_log(n_time, card_id, '退款', '成功', msg)
        return jsonify({"code": RET.OK, "msg": MSG.OK})


@user_blueprint.route('/card_trans_decline/', methods=['GET'])
@login_required
@account_lock
def all_trans_decline():
    page = request.args.get("page")
    limit = request.args.get("limit")
    trans_card = request.args.get("trans_card")
    card_name = request.args.get("card_name")
    card_num_sql = ""
    if trans_card:
        card_num_sql = "AND card_number='{}'".format(trans_card)
    card_name_sql = ""
    if card_name:
        card_name_sql = "AND alias='{}'".format(card_name)
    user_id = g.user_id
    card_trans = SqlData.search_card_decline(user_id, card_num_sql, card_name_sql)
    results = {}
    results['code'] = RET.OK
    results['msg'] = MSG.OK
    if not card_trans:
        results['code'] = RET.SERVERERROR
        results['msg'] = MSG.NODATA
        return jsonify(results)
    data = sorted(card_trans, key=operator.itemgetter("transaction_hour"))
    data = list(reversed(data))
    page_list = list()
    for i in range(0, len(data), int(limit)):
        page_list.append(data[i: i + int(limit)])
    results["data"] = page_list[int(page) - 1]
    results["count"] = len(data)
    return jsonify(results)


@user_blueprint.route('/card_trans/', methods=['GET'])
@login_required
@account_lock
def all_trans():
    page = request.args.get("page")
    limit = request.args.get("limit")
    trans_card = request.args.get("trans_card")
    card_name = request.args.get("card_name")
    card_num_sql = ""
    if trans_card:
        card_num_sql = "AND card_number='{}'".format(trans_card)
    card_name_sql = ""
    if card_name:
        card_name_sql = "AND alias='{}'".format(card_name)
    user_id = g.user_id
    card_trans = SqlData.search_card_trans(user_id, card_num_sql, card_name_sql)
    results = {}
    results['code'] = RET.OK
    results['msg'] = MSG.OK
    if not card_trans:
        results['code'] = RET.SERVERERROR
        results['msg'] = MSG.NODATA
        return jsonify(results)
    data = sorted(card_trans, key=operator.itemgetter("transaction_hour"))
    data = list(reversed(data))
    page_list = list()
    for i in range(0, len(data), int(limit)):
        page_list.append(data[i: i + int(limit)])
    results["data"] = page_list[int(page) - 1]
    results["count"] = len(data)
    return jsonify(results)


@user_blueprint.route('/bento_decline/', methods=['GET'])
@login_required
@account_lock
def bento_decline():
    page = request.args.get('page')
    limit = request.args.get('limit')

    time_range = request.args.get('time_range')
    card_num = request.args.get('card_num')
    time_sql = ""
    card_sql = ""
    if time_range:
        min_time = time_range.split(' - ')[0] + ' 00:00:00'
        max_time = time_range.split(' - ')[1] + ' 23:59:59'
        time_sql = "AND date BETWEEN " + "'" + min_time + "'" + " and " + "'" + max_time + "'"
    else:
        min_time = ""
        max_time = ""
    if card_num:
        # card_sql = "AND card_no = '" + card_num + "'"
        card_sql = "AND last_four LIKE '%{}%'".format(card_num)

    alias = g.user_name
    results = {"code": RET.OK, "msg": MSG.OK, "count": 0, "data": ""}
    task_info = SqlDataNative.search_decline_data(alias, card_sql, time_sql)
    task_info = sorted(task_info, key=operator.itemgetter("date"))
    task_info = list(reversed(task_info))
    # cardid_list = SqlDataNative.attribution_fount_cardid(alias)
    # decline_ratio = RechargeCard().declined_statistics(cardid_list[1: 50], min_time, max_time)
    if len(task_info) == 0:
        results["MSG"] = MSG.NODATA
        return jsonify(results)
    page_list = list()
    for i in range(0, len(task_info), int(limit)):
        page_list.append(task_info[i:i + int(limit)])
    results["data"] = page_list[int(page) - 1]
    results["count"] = len(task_info)
    return jsonify(results)


@user_blueprint.route('/bento_update/', methods=['GET'])
@login_required
def bento_update():
    alias = request.args.get("account")
    s = SqlDataNative.alias_fount_cardid(alias)
    data = get_bento_data(cardid=s)
    if data.get("pan"):
        SqlDataNative.update_card_data(pan=data.get("pan"), cvv=data.get("cvv"), expiration=data.get("expiration"),
                                        alias=alias)
        card_id = SqlDataNative.search_card_number('card_id', alias)[0]
        SqlData.update_account_trans(card_id, data.get("pan"))
        return jsonify({"code": RET.OK, "msg": "更新成功"})
    else:
        return jsonify({"code": RET.OK, "msg": "更新失败, 请稍后再试"})


@user_blueprint.route('/delcard/', methods=['GET'])
@login_required
@account_lock
def del_account():
    # 判断是否是子账号用户
    vice_id = g.vice_id
    if vice_id:
        auth_dict = RedisTool.hash_get('vice_auth', vice_id)
        if auth_dict is None:
            return jsonify({'code': RET.SERVERERROR, 'msg': '抱歉您没有权限执行此操作！'})
        c_card = auth_dict.get('del_card')
        if c_card == 'F':
            return jsonify({'code': RET.SERVERERROR, 'msg': '抱歉您没有权限执行此操作！'})
    cardnumber = request.args.get('card_no')
    user_id = g.user_id
    # 获取cardid, 用于删除卡
    cardid = SqlData.search_card_field('card_id', cardnumber)
    if not cardid:
        return jsonify({"code": RET.SERVERERROR, "msg": "卡已注销"})

    if cardid:
        # 判断是不是当前用户的卡
        now_user = SqlData.search_card_field('user_id', cardnumber)
        if now_user != user_id:
            results = {"code": RET.SERVERERROR, "msg": "不要违规操作"}
            return jsonify(results)

    alias = SqlData.search_card_field('alias', cardnumber)
    availableAmount = RechargeCard().one_alias(alias)

    if not availableAmount or availableAmount == "查询异常" or availableAmount == "卡已注销":
        return jsonify({"code": RET.SERVERERROR, "msg": "该卡余额异常, 无法进行删卡操作"})

    # 查询卡的消费记录计算总支出金额
    card_trans = bento.transaction_data(cardid)
    card_real_pay = 0
    if isinstance(card_trans, list):
        if len(card_trans) > 0:
            for tran in card_trans:
                amount = tran.get('amount')
                status = tran.get('status')
                if status != "DECLINED":
                    card_real_pay += amount
    else:
        results = {"code": RET.SERVERERROR, "msg": "删卡失败，请重试"}
        return jsonify(results)

    # 计算在平台上一共给这个卡充值了多少钱
    sum_top = SqlData.search_out_trans(cardnumber)
    sum_refund = SqlData.search_recycle_trans(cardnumber)
    # 相加是因为支出是以负数形式存进数据库， 再取绝对值，就是卡总充值的金额
    due_top = round(abs(sum_top + sum_refund), 2)

    # 卡消费中有正数负数，正数为退款收到的金额，负数为交易扣除的金额，所以也是相加取绝对值，为开始总真实花费的金额
    card_real_pay = round(abs(card_real_pay), 2)
    # 卡总充值-卡总真实花费的=理论卡上还有的余额
    due_remain = round(due_top - card_real_pay, 2)

    if due_remain > availableAmount:
        refund_limit = availableAmount
    elif due_remain < availableAmount:
        refund_limit = due_remain
    else:
        refund_limit = availableAmount

    del_status = bento.del_card(cardid)
    n_time = xianzai_time()
    if del_status == 200:
        before_balance = SqlData.search_user_field('balance', user_id)
        SqlData.update_balance(round(refund_limit, 2), user_id)
        balance = SqlData.search_user_field("balance", user_id)

        SqlData.insert_user_trans(n_time, TRANS_TYPE.IN, DO_TYPE.DELCARD, alias, cardnumber, refund_limit,
                                  before_balance, balance, user_id)
        SqlData.update_card_destroy(cardid)
        SqlData.insert_operating_log(n_time, cardid, '删卡', '成功', '删卡成功, 退回金额:{}'.format(refund_limit))
        return jsonify({"code": RET.OK, "msg": MSG.OK})
    else:
        SqlData.insert_operating_log(n_time, cardid, '删卡', '失败', '删卡失败')
        return jsonify({"code": RET.OK, "msg": "删卡失败"})


@user_blueprint.route('/card_remain/', methods=['GET'])
@account_lock
def card_remain():
    results = dict()
    try:
        results['code'] = RET.OK
        results['msg'] = MSG.OK
        data = request.args.get('data')
        data = json.loads(data)
        info = get_card_remain(data)
        results['data'] = info
        results['count'] = len(info)
        return results
    except Exception as e:
        logging.error(str(e))
        results['code'] = RET.SERVERERROR
        results['msg'] = MSG.SERVERERROR
        return jsonify(results)


@user_blueprint.route('/user_trans/', methods=['GET'])
@login_required
@account_lock
def account_trans():
    page = request.args.get('page')
    limit = request.args.get('limit')

    time_range = request.args.get('time_range')
    card_num = request.args.get('card_num')
    do_type = request.args.get('do_type')
    card_name = request.args.get('card_name')
    time_sql = ""
    card_sql = ""
    do_sql = ""
    name_sql = ""
    if time_range:
        min_time = time_range.split(' - ')[0]
        max_time = time_range.split(' - ')[1] + ' 23:59:59'
        time_sql = "AND do_date BETWEEN " + "'" + min_time + "'" + " and " + "'" + max_time + "'"
    if card_num:
        card_sql = "AND card_no LIKE '%{}%'".format(card_num)
    if do_type:
        do_sql = "AND do_type='" + do_type + "'"
    if card_name:
        name_sql = "AND card_name='" + card_name + "'"

    user_id = g.user_id
    task_info = SqlData.search_user_trans(user_id, card_sql, time_sql, name_sql, type_sql=do_sql)
    results = {"code": RET.OK, "msg": MSG.OK, "count": 0, "data": ""}
    if len(task_info) == 0:
        results['MSG'] = MSG.NODATA
        return jsonify(results)

    # 查询注销的卡，隐藏注销的卡号
    fail_card = SqlData.search_card_fail()
    card_info = list()
    for i in task_info:
        card_number = i.get('card_no')
        card_no = card_number.split()[0]
        if card_no in fail_card:
            i['card_no'] = "****" + card_no[-4:]
        card_info.append(i)
    page_list = list()
    task_info = list(reversed(card_info))
    for i in range(0, len(task_info), int(limit)):
        page_list.append(task_info[i:i + int(limit)])
    results['data'] = page_list[int(page) - 1]
    results['count'] = len(task_info)
    return jsonify(results)


@user_blueprint.route('/update_label/', methods=['GET'])
@login_required
@account_lock
def update_label():
    card_no = request.args.get('card_no')
    context = dict()
    context['card_no'] = card_no
    return render_template('user/update_label.html', **context)


@user_blueprint.route('/label_update/', methods=['POST'])
@login_required
@account_lock
def label_update():
    # 判断是否是子账号用户
    vice_id = g.vice_id
    if vice_id:
        auth_dict = RedisTool.hash_get('vice_auth', vice_id)
        c_card = auth_dict.get('up_label')
        if c_card == 'F':
            return jsonify({'code': RET.SERVERERROR, 'msg': '抱歉您没有权限执行此操作！'})
    data = json.loads(request.form.get('data'))
    # 卡名
    card_number = data.get('card_no')

    # 修改的标签名
    label_name = data.get("top_money")
    # label_status = SqlDataNative.select_label_status(card_no=card_no)

    SqlData.update_card_label(label_name, card_number)

    return jsonify({"code": RET.OK, "msg": "修改标签成功"})


# 充值
@user_blueprint.route('/top_up/', methods=['POST'])
@login_required
@account_lock
@trans_lock
def top_up():
    # 判断是否是子账号用户
    vice_id = g.vice_id
    if vice_id:
        auth_dict = RedisTool.hash_get('vice_auth', vice_id)
        if auth_dict is None:
            return jsonify({'code': RET.SERVERERROR, 'msg': '抱歉您没有权限执行此操作！'})
        c_card = auth_dict.get('top_up')
        if c_card == 'F':
            return jsonify({'code': RET.SERVERERROR, 'msg': '抱歉您没有权限执行此操作！'})
    user_id = g.user_id
    data = json.loads(request.form.get('data'))
    card_no = data.get('card_no')
    top_money = data.get('top_money')
    user_data = SqlData.search_user_index(user_id)
    balance = user_data.get('balance')
    if not check_float(top_money):
        results = {"code": RET.SERVERERROR, "msg": "充值金额不能为小数"}
        return jsonify(results)
    if int(top_money) > balance:
        results = {"code": RET.SERVERERROR, "msg": "本次消费金额:" + str(top_money) + ",账号余额不足!"}
        return jsonify(results)
    card_number = str(card_no.strip())
    card_id = SqlData.search_card_field('card_id', card_number)
    if not card_id:
        return jsonify({"code": RET.SERVERERROR, "msg": "卡已注销"})
    if card_id:
        # 判断是不是当前用户的卡
        now_user = SqlData.search_card_field('user_id', card_number)
        if now_user != user_id:
            results = {"code": RET.SERVERERROR, "msg": "不要违规操作"}
            return jsonify(results)

        # 查询卡的消费记录计算总支出金额
        card_trans = bento.transaction_data(card_id)
        card_real_pay = 0
        if isinstance(card_trans, list):
            if len(card_trans) > 0:
                for tran in card_trans:
                    amount = tran.get('amount')
                    status = tran.get('status')
                    if status != "DECLINED":
                        card_real_pay += amount
        else:
            results = {"code": RET.SERVERERROR, "msg": "充值失败，请重试"}
            return jsonify(results)

        # 计算在平台上一共给这个卡充值了多少钱
        sum_top = SqlData.search_out_trans(card_number)
        sum_refund = SqlData.search_recycle_trans(card_number)
        # 相加是因为支出是以负数形式存进数据库， 再取绝对值，就是卡总充值的金额
        due_top = round(abs(sum_top + sum_refund), 2)

        # 卡消费中有正数负数，正数为退款收到的金额，负数为交易扣除的金额，所以也是相加取绝对值，为开始总真实花费的金额
        card_real_pay = round(abs(card_real_pay), 2)
        # 卡总充值-卡总真实花费的=理论卡上还有的余额
        due_remain = round(due_top - card_real_pay, 2)

        # 进行充值
        result_msg = bento.recharge(card_id, int(top_money), due_remain)
        code = result_msg.get('code')
        msg = result_msg.get('msg')
        if code == 200:
            before_balance = SqlData.search_user_field('balance', user_id)
            # balance = round(before_balance - int(top_money), 2)
            bento_do_money = -int(top_money)
            SqlData.update_balance(bento_do_money, user_id)
            balance = SqlData.search_user_field("balance", user_id)
            # SqlData.update_user_field_int('balance', balance, user_id)
            card_name = SqlData.search_card_field('alias', card_number)
            n_time = xianzai_time()
            SqlData.insert_user_trans(n_time, TRANS_TYPE.OUT, DO_TYPE.TOP_UP, card_name, card_no,
                                      -int(top_money), before_balance, balance, user_id)
            SqlData.insert_operating_log(n_time, card_id, '充值', '成功', msg)
            return jsonify({"code": RET.OK, "msg": MSG.OK})
        elif code == 500:
            n_time = xianzai_time()
            SqlData.insert_operating_log(n_time, card_id, '充值', '失败', msg)
            return jsonify({"code": RET.SERVERERROR, "msg": '充值失败，请重试'})

    else:
        return jsonify({"code": RET.SERVERERROR, "msg": "卡号异常, 请联系管理员"})


# 批量建卡
@user_blueprint.route('/create_card/', methods=['GET', 'POST'])
@login_required
@account_lock
@trans_lock
@create_card
def create_some():
    if request.method == 'GET':
        user_id = g.user_id
        price = SqlData.search_user_field('create_price', user_id)
        contxt = dict()
        contxt['price'] = price
        return render_template('user/create_card.html', **contxt)

    if request.method == 'POST':
        # 判断是否是子账号用户
        vice_id = g.vice_id
        if vice_id:
            auth_dict = RedisTool.hash_get('vice_auth', vice_id)
            if auth_dict is None:
                return jsonify({'code': RET.SERVERERROR, 'msg': '抱歉您没有权限执行此操作！'})
            c_card = auth_dict.get('c_s_card')
            if c_card == 'F':
                return jsonify({'code': RET.SERVERERROR, 'msg': '抱歉您没有权限执行此操作！'})
        data = json.loads(request.form.get('data'))
        card_num = data.get('card_num')
        limit = data.get('limit')
        label = data.get('label')
        user_id = g.user_id
        user_data = SqlData.search_user_index(user_id)
        create_price = user_data.get('create_price')
        balance = user_data.get('balance')
        create_card_num = user_data.get('card_num')
        # 比较可开卡数量与已开卡数量
        use_card_num = SqlData.count_card_used(user_id)
        if int(create_card_num) - int(use_card_num) < int(card_num):
            results = {"code": RET.SERVERERROR, "msg": "可开卡数量不足, 请联系管理员"}
            return jsonify(results)

        card_num = int(card_num)
        if card_num > 10:
            results = {"code": RET.SERVERERROR, "msg": "一次最多建卡10张"}
            return jsonify(results)
        if not check_float(limit):
            results = {"code": RET.SERVERERROR, "msg": "充值金额不能为小数!"}
            return jsonify(results)
        sum_money = card_num * int(limit) + card_num * create_price

        # 本次开卡需要的费用,计算余额是否充足
        if sum_money > balance:
            results = {"code": RET.SERVERERROR, "msg": "本次消费金额:" + str(sum_money) + ",账号余额不足!"}
            return jsonify(results)

        new_card = SqlData.search_valid_card(int(card_num))
        if not int(card_num) == len(new_card):
            results = {"code": RET.SERVERERROR, "msg": "库存不足请五分钟后重试"}
            return jsonify(results)
        try:
            for i in new_card:
                n_time = xianzai_time()
                alias = i[1]
                card_id = i[2]
                card_number = i[3]
                card_amount = i[4]
                cvv = i[5]
                card_validity = i[6]
                SqlData.update_new_card_use(card_id)
                SqlData.insert_user_card(alias, card_id, card_number, card_amount, cvv, card_validity, n_time, label, user_id)
                # 开卡费用
                before_balance = SqlData.search_user_field('balance', user_id)
                create_price_do_money = -float(create_price)
                SqlData.update_balance(create_price_do_money, user_id)
                balance = SqlData.search_user_field("balance", user_id)
                SqlData.insert_user_trans(n_time, TRANS_TYPE.OUT, DO_TYPE.CREATE_CARD, alias, card_number, create_price_do_money, before_balance, balance, user_id)

                # 充值费用
                before_balance = SqlData.search_user_field('balance', user_id)
                top_money_do_money = -int(limit)
                SqlData.update_balance(top_money_do_money, user_id)
                balance = SqlData.search_user_field("balance", user_id)
                n_time = xianzai_time()
                SqlData.insert_user_trans(n_time, TRANS_TYPE.OUT, DO_TYPE.TOP_UP, alias, card_number,
                                          top_money_do_money, before_balance, balance, user_id)
            return jsonify({"code": RET.OK, "msg": "成功开卡"})
        except Exception as e:
            logging.error(e)
            results = {"code": RET.SERVERERROR, "msg": str(e)}
            return jsonify(results)


@user_blueprint.route('/top_history/', methods=['GET'])
@login_required
@account_lock
def top_history():
    page = request.args.get('page')
    limit = request.args.get('limit')
    user_id = g.user_id
    task_info = SqlData.search_top_history_acc(user_id)
    task_info = sorted(task_info, key=operator.itemgetter('time'))
    results = {"code": RET.OK, "msg": MSG.OK, "count": 0, "data": ""}
    if len(task_info) == 0:
        results['MSG'] = MSG.NODATA
        return results
    page_list = list()
    task_info = list(reversed(task_info))
    for i in range(0, len(task_info), int(limit)):
        page_list.append(task_info[i:i + int(limit)])
    results['data'] = page_list[int(page) - 1]
    results['count'] = len(task_info)
    return jsonify(results)


@user_blueprint.route('/', methods=['GET'])
@login_required
# @account_lock
def account_html():
    '''
    user_name = g.user_name
    user_id = g.user_id
    dict_info = SqlData.search_user_index(user_id)
    create_card = dict_info.get('create_card')
    refund = dict_info.get('refund') * 100
    min_top = dict_info.get('min_top')
    max_top = dict_info.get('max_top')
    balance = dict_info.get('balance')

    today_time = time.strftime('%Y-%m-%d', time.localtime(time.time()))
    max_today = "{} {}".format(change_today(today_time, 0), "23:59:59")
    min_today = "{} {}".format(change_today(today_time, -3), "00:00:00")
    # one_t_data = SqlDataNative.account_sum_transaction(attribution=user_name)
    three_data = SqlDataNative.count_decline_data(attribution=user_name, min_today=min_today, max_today=max_today)
    three_tran_data = SqlDataNative.search_d(user_name)
    decline_ratio = "{}{}".format(float("%.4f" % (three_data / three_tran_data * 100)),
                                  '%') if three_tran_data != 0 else 0

    # decline_ratio = "{}{}".format(float("%.4f"%(decline_data / t_data * 100)), '%') if t_data != 0 else 0
    # 获取已开卡数量
    use_label = SqlDataNative.count_alias_data(user_name)
    context = dict()

    # 公告
    notice = SqlDataNative.bento_notice()
    # 用户的所有卡金额
    if use_label:
        context['use_label'] = use_label[0]
    else:
        context['use_label'] = "异常, 请联系管理员"

    if g.vice_id:
        context['bg_color'] = 'layui-bg-blue'
    # 所拥有的总余额参数
    context['decline_ratio'] = decline_ratio
    context['user_name'] = user_name
    context['balance'] = balance
    context['refund'] = refund
    context['create_card'] = create_card
    context['min_top'] = min_top
    context['max_top'] = max_top
    context['notice'] = notice
    '''
    return render_template('user/index.html', )


@user_blueprint.route('/change_phone/', methods=['POST'])
@login_required
@account_lock
def change_phone():
    # 判断是否是子账号用户
    vice_id = g.vice_id
    if vice_id:
        return jsonify({'code': RET.SERVERERROR, 'msg': '您没有权限操作！请切换主账号后重试！'})
    user_id = g.user_id
    data = json.loads(request.form.get('data'))
    phone_num = data.get('phone')
    results = dict()
    try:
        SqlData.update_user_field('phone_num', phone_num, user_id)
        results['code'] = RET.OK
        results['msg'] = MSG.OK
        return jsonify(results)
    except Exception as e:
        logging.error(str(e))
        results['code'] = RET.SERVERERROR
        results['msg'] = MSG.SERVERERROR
        return jsonify(results)


# 卡的交易记录
@user_blueprint.route('/one_card_detail/', methods=['GET'])
@login_required
def one_detail():
    try:
        context = {}
        info_list = []
        card_no = request.args.get('card_no')
        card_id = SqlData.search_card_field('card_id', card_no.strip())
        transaction_data = bento.transaction_data(card_id)
        for td in transaction_data:
            info_list.append({
                "status": td.get("status"),
                "amount": td.get("amount"),
                "description": td.get("description"),
                "date": td.get("date"),
                "cardTransactionId": td.get("cardTransactionId"),
                "lastFour": td.get("lastFour"),
                "alias": td.get("alias"),
                "originalCurrency": td.get("originalCurrency"),
            })
        context['pay_list'] = info_list
        return render_template('user/card_detail_trans.html', **context)
    except Exception as e:
        logging.error((str(e)))
        return render_template('user/404.html')


# 卡的余额
@user_blueprint.route('/one_card_remain/', methods=['GET'])
@login_required
def one_remain():
    context = {}
    alias = request.args.get('card_name')
    balance = bento.card_ava(alias)
    if not balance:
        return render_template('user/404.html')
    context['remain'] = balance
    return render_template('user/card_remain.html', **context)


@user_blueprint.route('/card_top/', methods=['GET'])
@login_required
@account_lock
def change_detail():
    return render_template('user/card_top.html')


# 余额
@user_blueprint.route('/card_info/', methods=['GET'])
@login_required
@account_lock
def card_info():
    card_name = request.args.get('card_name')
    card_num = request.args.get('card_num')
    limit = request.args.get('limit')
    page = request.args.get('page')
    label = request.args.get('label')
    range_time = request.args.get('range_time')
    card_status = request.args.get('card_status')
    results = {}
    results['code'] = RET.OK
    results['msg'] = MSG.OK
    user_id = g.user_id
    if not label and not card_name and not card_num and not range_time:
        if card_status == 'show':
            status = ''
        else:
            status = 'F'
        data = SqlData.select_user_card_show(status, user_id)
    else:
        name_sql = ""
        if card_name:
            name_sql = "AND alias LIKE '%{}%'".format(card_name)
        card_sql = ""
        if card_num:
            card_sql = "AND card_number LIKE '%{}%'".format(card_num)
        label_sql = ""
        if label:
            label_sql = "AND label LIKE '%{}%'".format(label)
        data = SqlData.select_user_card(user_id, name_sql, card_sql, label_sql)
    if not data:
        results['code'] = RET.SERVERERROR
        results['msg'] = MSG.NODATA
        return jsonify(results)
    page_list = list()
    info = list(reversed(data))
    for i in range(0, len(info), int(limit)):
        page_list.append(info[i:i + int(limit)])
    data = page_list[int(page) - 1]
    # data = get_card_remain(data)
    results['data'] = data
    results['count'] = len(info)
    return jsonify(results)


@user_blueprint.route('/edit_user', methods=['GET'])
@login_required
@account_lock
def ch_pass_html():
    vice_id = g.vice_id
    if vice_id:
        return render_template('user/no_auth.html')
    return render_template('user/edit_user.html')


@user_blueprint.route('/change_pass', methods=["POST"])
@login_required
@account_lock
def change_pass():
    data = json.loads(request.form.get('data'))
    old_pass = data.get('old_pass')
    new_pass_one = data.get('new_pass_one')
    new_pass_two = data.get('new_pass_two')
    user_id = g.user_id
    pass_word = SqlData.search_user_field('password', user_id)
    results = {'code': RET.OK, 'msg': MSG.OK}
    res = re.match('(?!.*\s)(?!^[\u4e00-\u9fa5]+$)(?!^[0-9]+$)(?!^[A-z]+$)(?!^[^A-z0-9]+$)^.{8,16}$', new_pass_one)
    if not res:
        results['code'] = RET.SERVERERROR
        results['msg'] = '密码不符合要求！'
        return jsonify(results)
    if not (old_pass == pass_word):
        results['code'] = RET.SERVERERROR
        results['msg'] = MSG.PSWDERROR
        return jsonify(results)
    if not (new_pass_one == new_pass_two):
        results['code'] = RET.SERVERERROR
        results['msg'] = '两次密码输入不一致！'
        return jsonify(results)
    try:
        SqlData.update_user_field('password', new_pass_one, g.user_id)
        session.pop('user_id')
        session.pop('name')
        return jsonify(results)
    except Exception as e:
        logging.error(e)
        results['code'] = RET.SERVERERROR
        results['msg'] = MSG.SERVERERROR
        return jsonify(results)


@user_blueprint.route('/logout/', methods=['GET'])
@login_required
def logout():
    session.pop('user_id')
    session.pop('name')
    session.pop('vice_id')
    return redirect('/user/login/')


@user_blueprint.route('/material/', methods=['GET', 'POST'])
def material():
    if request.method == 'GET':
        '''完善资料的HTML界面'''
        user_name = request.args.get('name')
        if not user_name:
            return redirect('/user/')
        context = dict()
        context['user_name'] = user_name
        return render_template('user/material.html', **context)
    if request.method == 'POST':

        '''新用户的首次登录更换密码和完善电话信息'''

        data = json.loads(request.form.get('data'))
        pass_1 = data.get('pass_1')
        pass_2 = data.get('pass_2')
        phone = data.get('phone')
        user_acc = data.get('user_name')
        if not all([pass_1, pass_2, phone]):
            return jsonify({'code': RET.SERVERERROR, 'msg': '必填项不能为空！'})
        if pass_1 != pass_2:
            return jsonify({'code': RET.SERVERERROR, 'msg': '两次输入密码不一致！'})
        res = re.match('(?!.*\s)(?!^[\u4e00-\u9fa5]+$)(?!^[0-9]+$)(?!^[A-z]+$)(?!^[^A-z0-9]+$)^.{8,16}$', pass_1)
        if not res:
            return jsonify({'code': RET.SERVERERROR, 'msg': '密码不符合要求！'})
        res_phone = re.match('^1(3[0-9]|4[5,7]|5[0-9]|6[2,5,6,7]|7[0,1,3,7,8]|8[0-9]|9[1,8,9])\d{8}$', phone)
        if not res_phone:
            return jsonify({'code': RET.SERVERERROR, 'msg': '请输入规范手机号码！'})
        try:
            user_id = SqlData.search_user_id(user_acc)
            SqlData.update_user_field('password', pass_1, user_id)
            SqlData.update_user_field('phone_num', phone, user_id)
            user_name = SqlData.search_user_field('name', user_id)
            session['user_id'] = user_id
            session['name'] = user_name
            session['vice_id'] = None
            session.permanent = True
            ip = request.remote_addr
            SqlData.update_user_field('login_ip', str(ip), user_id)
            now_t = xianzai_time()
            SqlData.update_user_field('login_time', now_t, user_id)
            return jsonify({'code': RET.OK, 'msg': MSG.OK})
        except Exception as e:
            logging.error(str(e))
            return jsonify({'code': RET.SERVERERROR, 'MSG': MSG.SERVERERROR})


@user_blueprint.route('/img_code/', methods=['GET'])
def img_code():
    try:
        code, img_str = createCodeImage()
        string = ImgCode().jiami(code)
        return jsonify({'code': RET.OK, 'data': {'string': string, 'src': img_str}})
    except Exception as e:
        logging.error(str(e))
        return jsonify({'code': RET.SERVERERROR, 'msg': MSG.SERVERERROR})


@user_blueprint.route('/notice/', methods=['GET'])
@login_required
def notice():
    notice = SqlData.search_admin_field('notice')
    note_list = notice.split("!@#")
    note = note_list[0]
    date = note_list[1]
    s = '<html><body><div style="padding-left:20px; color:red;">公告时间：{}</div><div style="padding:15px 20px; text-align:justify; line-height: 22px; text-indent:2em;"><p class="layui-red">{}</p></div></body></html>'.format(date, note)
    return s


@user_blueprint.route('/html/', methods=['GET'])
@login_required
def html():
    name = request.args.get('name')
    return render_template('user/{}.html'.format(name))


@user_blueprint.route('/line_chart/')
@login_required
def lind_card():
    day_list = get_nday_list(30)
    user_id = g.user_id
    sum_day_money = list()
    sum_day_card = list()
    for d in day_list:
        start_t = d + " 00:00:00"
        end_t = d + " 23:59:59"
        day_money = SqlData.search_trans_money(start_t, end_t, user_sql='AND user_id={}'.format(user_id))
        if not day_money:
            day_money = 0
        else:
            day_money = abs(day_money)
        sum_day_money.append(day_money)
        sql = "WHERE do_type='开卡' AND do_date BETWEEN '{}' AND '{}' AND user_id={}".format(start_t, end_t, user_id)
        card_num = SqlData.search_value_count('user_trans', sql=sql)
        sum_day_card.append(card_num)
    money_dict = {'name': '充值金额', 'type': 'column', 'yAxis': 1, 'data': sum_day_money, 'tooltip': {'valueSuffix': ' $'}}
    card_dict = {'name': '开卡数量', 'type': 'spline', 'data': sum_day_card, 'tooltip': {'valueSuffix': ' 张'}}
    results = dict()
    results['code'] = RET.OK
    results['msg'] = MSG.OK
    results['data'] = [money_dict, card_dict]
    results['xAx'] = day_list
    return jsonify(results)


@user_blueprint.route('/main/', methods=['GET'])
@login_required
def main_index():
    user_id = g.user_id
    data = SqlData.search_user_index(user_id)
    card_remain = SqlData.search_user_card_balance(user_id)
    card_using = SqlData.search_user_card_using(user_id)
    card_destroy = SqlData.search_user_card_destroy(user_id)
    remain_time = SqlData.search_admin_field('up_remain_time')
    spend_money = SqlData.search_spend_money(user_id)
    data.update({'card_remain': card_remain, 'card_using': card_using, 'card_destroy': card_destroy,
                 'remain_time': remain_time, 'spend_money':spend_money})
    return render_template('user/main.html', **data)


@user_blueprint.route('/login/', methods=['POST', 'GET'])
def login():
    if request.method == 'GET':
        code, img_str = createCodeImage(height=46)
        context = dict()
        string = ImgCode().jiami(code)
        context['img'] = img_str
        context['code'] = string
        return render_template('user/login.html', **context)

    if request.method == 'POST':
        results = {'code': RET.OK, 'msg': MSG.OK}
        data = json.loads(request.form.get('data'))
        user_name = data.get('user_name')
        user_pass = data.get('pass_word')
        image_real = data.get('image_real')
        image_code = data.get('image_code')
        try:
            # 校验图片验证码
            img_code = ImgCode().jiemi(image_real)
            if image_code.lower() != img_code.lower():
                results['code'] = RET.SERVERERROR
                results['msg'] = '验证码错误！'
                return jsonify(results)

            # 主账号登录
            user_data = SqlData.search_user_login(user_name)
            user_id = user_data.get('user_id')
            pass_word = user_data.get('password')
            name = user_data.get('name')
            login_time = user_data.get('login_time')
            if user_pass == pass_word:
                if not login_time:
                    return jsonify({'code': 307, 'msg': MSG.OK})
                else:
                    ip = request.remote_addr
                    SqlData.update_user_field('login_ip', str(ip), user_id)
                    now_t = xianzai_time()
                    SqlData.update_user_field('login_time', now_t, user_id)
                    session['user_id'] = user_id
                    session['name'] = name
                    session['vice_id'] = None
                    session.permanent = True
                    return jsonify(results)

            # 子账号登录
            user_data = SqlData.search_user_vice_info(user_name)
            user_id = user_data.get('user_id')
            password = user_data.get('password')
            vice_id = user_data.get('vice_id')
            if password == user_pass:
                # 存储到缓存
                session['user_id'] = user_id
                session['name'] = user_name
                session['vice_id'] = vice_id
                session.permanent = True
                # 存储子子账号操作权限到redis
                res = SqlData.search_one_acc_vice(vice_id)
                RedisTool.hash_set('vice_auth', res.get('vice_id'), res)
                return jsonify(results)
            results['code'] = RET.SERVERERROR
            results['msg'] = MSG.PSWDERROR
            return jsonify(results)

        except Exception as e:
            results['code'] = RET.SERVERERROR
            results['msg'] = MSG.PSWDERROR
            return jsonify(results)
