import json
import os
import random
import re
import time
import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal

from flask import request, current_app
from sqlalchemy import false, cast, Date, func, extract

from tickets.config.enums import PayType, ProductStatus, UserCommissionStatus, ApplyFrom, OrderStatus, WexinBankCode
from tickets.config.http_config import API_HOST
from tickets.config.timeformat import format_for_web_second, format_forweb_no_HMS
from tickets.extensions.error_response import ParamsError, StatusError, AuthorityError
from tickets.extensions.interface.user_interface import is_user, is_admin, token_required, phone_required, is_supplizer
from tickets.extensions.make_qrcode import qrcodeWithtext
from tickets.extensions.params_validates import parameter_required
from tickets.extensions.register_ext import db, mini_wx_pay
from tickets.extensions.success_response import Success
from tickets.extensions.tasks import add_async_task, auto_cancle_order
from tickets.extensions.weixin.pay import WeixinPayError
from tickets.extensions.register_ext import qiniu_oss
from tickets.models import User, Product, UserWallet, Commision, OrderPay, OrderMain, UserCommission, Supplizer, \
    ProductMonthSaleValue


class COrder():

    def __init__(self):
        self.wx_pay = mini_wx_pay

    """post 接口"""

    def wechat_notify(self, **kwargs):
        """微信支付回调接口"""
        redirect = kwargs.get('redirect')
        with db.auto_commit():
            if not redirect:
                data = self.wx_pay.to_dict(request.data)

                if not self.wx_pay.check(data):
                    return self.wx_pay.reply(u"签名验证失败", False)

                out_trade_no = data.get('out_trade_no')
                current_app.logger.info("This is wechat_notify, opayno is {}".format(out_trade_no))

                pp = OrderPay.query.filter_by(OPayno=out_trade_no, isdelete=False).first()
                if not pp:
                    # 支付流水不存在 钱放在平台
                    return self.wx_pay.reply("OK", True).decode()
                self._commision(pp)  # 佣金到账
                pp.update({
                    'OPaytime': data.get('time_end'),
                    'OPaysn': data.get('transaction_id'),
                    'OPayJson': json.dumps(data)
                })

            else:
                pp = kwargs.get('pp')
                pp.update({
                    'OPaytime': datetime.now(),
                })

            db.session.add(pp)

            # 修改订单状态
            om = OrderMain.query.filter(OrderMain.isdelete == false(), OrderMain.OPayno == pp.OPayno).first()
            if not om:
                current_app.logger.error('===订单查询失败 OPayno= {} ==='.format(pp.OPayno))
                return self.wx_pay.reply("OK", True).decode()
            if om.OMpayType == PayType.deposit.value:  # 押金付
                om.OMstatus = OrderStatus.pending.value
            elif om.OMpayType == PayType.scorepay.value:  # 信用付
                om.OMstatus = OrderStatus.pending.value
            elif om.OMpayType == PayType.cash.value:  # 直接买
                om.OMstatus = OrderStatus.has_won.value
                om.OMqrcode = self._ticket_order_qrcode(om.OMid, om.USid)
            # todo 管理员确认中奖
        return self.wx_pay.reply("OK", True).decode()

    @phone_required
    def pay(self):
        """购买"""
        data = parameter_required()
        prid, ompaytype = data.get('prid'), data.get('ompaytype')
        try:
            ompaytype = PayType(int(ompaytype)).value
        except (ValueError, AttributeError, TypeError):
            raise ParamsError('支付方式错误')

        # if not is_user():
        #     raise AuthorityError

        user = self._current_user('请重新登录')
        opayno = self._opayno()
        now = datetime.now()
        product = Product.query.filter(Product.PRid == prid, Product.PRstatus == ProductStatus.active.value,
                                       Product.isdelete == false()).first_('商品已下架')

        if product.PRtimeLimeted:
            starttime = self._check_time(product.PRissueStartTime)
            endtime = self._check_time(product.PRissueEndTime)
            if starttime and now < starttime:
                raise StatusError('商品未到发放时间')
            if endtime and now > endtime:
                raise StatusError('商品已过发放时间')
        trade = self._query_traded(prid, user.USid)  # 直购不限制
        redirect = False
        omid = str(uuid.uuid1())

        with db.auto_commit():
            if ompaytype == PayType.cash.value:
                # 直购
                mount_price = Decimal(product.PRtruePrice)
                if mount_price == Decimal('0'):
                    redirect = True
                trade = False
            elif ompaytype == PayType.scorepay.value:
                # 活跃分
                # if not user.USrealname:  # 暂时除去实名验证
                #     raise StatusError('用户未进行信用认证')
                if not product.PRtimeLimeted:
                    raise StatusError('活跃分支持限时商品')
                mount_price = 0
                redirect = True
            else:
                raise StatusError('支付方式错误')
            if trade:
                raise StatusError('您已申请成功，请在“我的 - 我的试用”中查看')
            omdict = {
                "OMid": omid,
                "OMno": self._generic_omno(),
                "OPayno": opayno,
                "USid": user.USid,
                "PRid": prid,
                "OMmount": product.PRlinePrice,
                "OMtrueMount": mount_price,
                "OMpayType": ompaytype,
                "PRcreateId": product.CreatorId,
                "PRname": product.PRname,
                "PRimg": product.PRimg,
                "OPnum": 1,  # 目前没有添加数量
            }
            if ompaytype == PayType.cash.value:
                omdict.setdefault('UPperid', user.USopenid1)
                omdict.setdefault('UPperid2', user.USopenid2)
                omdict.setdefault('UPperid3', user.USopenid3)
                # 极差分佣暂时不需要
                # omdict.setdefault('USCommission1', user.USCommission1)
                # omdict.setdefault('USCommission2', user.USCommission2)
                # omdict.setdefault('USCommission3', user.USCommission3)
            om = OrderMain.create(omdict)
            # product.PRnum -= 1  # 商品库存修改 # 0618 fix 非商品逻辑，不能改库存数

            # 月销量 修改或新增
            today = datetime.now()
            month_sale_instance = ProductMonthSaleValue.query.filter(
                ProductMonthSaleValue.isdelete == false(),
                ProductMonthSaleValue.PRid == product.PRid,
                extract('month', ProductMonthSaleValue.createtime) == today.month,
                extract('year', ProductMonthSaleValue.createtime) == today.year,
            ).first()
            if not month_sale_instance:
                month_sale_instance = ProductMonthSaleValue.create({'PMSVid': str(uuid.uuid1()),
                                                                    'PRid': prid,
                                                                    'PMSVnum': 1,
                                                                    'PMSVfakenum': 1
                                                                    })
            else:
                month_sale_instance.update({'PMSVnum': ProductMonthSaleValue.PMSVnum + 1,
                                            'PMSVfakenum': ProductMonthSaleValue.PMSVfakenum + 1})
            db.session.add(month_sale_instance)

            db.session.add(product)
            db.session.add(om)
        body = product.PRname[:16] + '...'
        openid = user.USopenid1
        # 直购订单 不付款 1分钟 自动取消
        if not product.PRtimeLimeted:
            add_async_task(auto_cancle_order, now + timedelta(minutes=1), (omid,), conn_id='autocancle{}'.format(omid))
        pay_args = self._add_pay_detail(opayno=opayno, body=body, mount_price=mount_price, openid=openid,
                                        opayType=ompaytype, redirect=redirect)
        response = {
            'pay_type': 'wechat_pay',
            'opaytype': ompaytype,
            # 'tscode': tscode_list,
            'args': pay_args,
            'redirect': redirect
        }
        current_app.logger.info('response = {}'.format(response))
        return Success(data=response)

    def cancle(self):
        """付款前取消订单"""
        data = parameter_required(('omid',))
        omid = data.get('omid')
        if not is_user():
            raise AuthorityError

        usid = getattr(request, 'user').id
        order_main = OrderMain.query.filter(
            OrderMain.OMid == omid, OrderMain.USid == usid, OrderMain.isdelete == false()).first_('指定订单不存在')
        # if is_supplizer() and order_main.PRcreateId != usid:
        #     raise AuthorityError()
        # if not is_admin() and order_main.USid != usid:
        #     raise NotFound('订单订单不存在')
        self._cancle(order_main)
        return Success('取消成功')

    def pay_to_user(self, cn):
        """
        付款到用户微信零钱
        :return:
        """
        user = User.query.filter_by_(USid=cn.USid).first_("提现用户状态异常，请检查后重试")
        try:
            result = self.wx_pay.pay_individual(
                partner_trade_no=self.wx_pay.nonce_str,
                openid=user.USopenid2,
                amount=int(Decimal(cn.CNcashNum).quantize(Decimal('0.00')) * 100),
                desc="优惠下沙-零钱转出",
                spbill_create_ip=self.wx_pay.remote_addr
            )
            current_app.logger.info('微信提现到零钱, response: {}'.format(request))
        except Exception as e:
            current_app.logger.error('微信提现返回错误：{}'.format(e))
            raise StatusError('微信商户平台: {}'.format(e))
        return result

    def _pay_to_bankcard(self, cn):
        """
        付款到银行卡号
        :param cn:
        :return:
        """
        try:
            enc_bank_no = self._to_encrypt(cn.CNcardNo)
            enc_true_name = self._to_encrypt(cn.CNcardName)
            bank_code = WexinBankCode(cn.CNbankName).zh_value
        except Exception as e:
            current_app.logger.error('提现到银行卡，参数加密出错：{}'.format(e))
            raise ParamsError('服务器繁忙，请稍后再试')

        try:
            result = self.wx_pay.pay_individual_to_card(
                partner_trade_no=self.wx_pay.nonce_str,
                enc_bank_no=enc_bank_no,
                enc_true_name=enc_true_name,
                bank_code=bank_code,
                amount=int(Decimal(cn.CNcashNum).quantize(Decimal('0.00')) * 100)
            )
            current_app.logger.info('微信提现到银行卡, response: {}'.format(request))
        except Exception as e:
            current_app.logger.error('微信提现返回错误：{}'.format(e))
            raise StatusError('微信商户平台: {}'.format(e))
        return result

    def _to_encrypt(self, message):
        """银行卡信息加密"""
        from tickets.config.secret import apiclient_public
        import base64
        from Cryptodome.PublicKey import RSA
        from Cryptodome.Cipher import PKCS1_OAEP

        with open(apiclient_public, 'r') as f:
            # pubkey = rsa.PublicKey.load_pkcs1(f.read().encode())
            pubkey = f.read()
            rsa_key = RSA.importKey(pubkey)
            # crypto = rsa.encrypt(message.encode(), pubkey)
            cipher = PKCS1_OAEP.new(rsa_key)
            crypto = cipher.encrypt(message.encode())
        return base64.b64encode(crypto).decode()

    def list(self):
        data = parameter_required()
        omstatus = data.get('omstatus')
        filter_args = [OrderMain.isdelete == false()]
        order_by_list = [OrderMain.updatetime.desc(), OrderMain.createtime.desc()]
        if is_user():
            user = self._current_user('请重新登录')

            try:
                omstatus = OrderStatus(int(str(omstatus))).value
            except ValueError:
                current_app.logger.error('omstatus error')
                omstatus = OrderStatus.pending.value
            filter_args.append(OrderMain.USid == user.USid)
            filter_args.append(OrderMain.OMstatus == omstatus)
        else:
            if omstatus:
                try:
                    omstatus = OrderStatus(int(str(omstatus))).value
                except:
                    omstatus = OrderStatus.pending.value
                filter_args.append(OrderMain.OMstatus == omstatus)
            omno = data.get('omno')
            prname = data.get('prname')
            ompaytype = data.get('ompaytype', PayType.cash.value)
            try:
                ompaytype = PayType(int(str(ompaytype))).value
            except:
                ompaytype = PayType.cash.value
            filter_args.append(OrderMain.OMpayType == ompaytype)
            createtime_start = self._check_date(data.get('createtime_start'))
            createtime_end = self._check_date(data.get('createtime_end'))
            if createtime_start:
                filter_args.append(cast(OrderMain.createtime, Date) >= createtime_start)
            if createtime_end:
                filter_args.append(cast(OrderMain.createtime, Date) <= createtime_end)
            if omno:
                filter_args.append(OrderMain.OMno.ilike('%{}%'.format(omno)))
            if prname:
                filter_args.append(OrderMain.PRname.ilike('%{}%'.format(prname)))
            if is_supplizer():
                filter_args.append(OrderMain.PRcreateId == getattr(request, 'user').id)
        omlist = OrderMain.query.filter(*filter_args).order_by(*order_by_list).all_with_page()

        now = datetime.now()

        user_list = db.session.query(User.USid, User.USname, User.USheader).filter(
            User.isdelete == false(), OrderMain.USid == User.USid, *filter_args).all()
        user_dict = {user_info[0]: user_info for user_info in user_list}
        for om in omlist:
            self._fill_ordermain(om)
            if om.OMstatus == OrderStatus.wait_pay.value:
                duration = om.createtime + timedelta(minutes=30) - now
                om.fill('duration', str(duration))
            # todo 填充商品信息
            # 填充用户信息
            user_info = user_dict.get(om.USid)
            # current_app.logger.info('get user info {}'.format(user_info))
            # current_app.logger.info('get user id {}'.format(om.USid))
            # current_app.logger.info('get om id {}'.format(om.OMid))

            om.fill('usname', user_info[1])
            om.fill('USheader', user_info[2])

        return Success(data=omlist)

    @token_required
    def get(self):
        data = parameter_required('omid')
        omid = data.get('omid')
        filter_args = [OrderMain.OMid == omid, OrderMain.isdelete == false()]
        if is_user():
            filter_args.append(OrderMain.USid == getattr(request, 'user').id)
        om = OrderMain.query.filter(*filter_args).first_('订单不存在')
        user = User.query.filter(User.isdelete == false(), User.USid == om.USid).first_('订单信息错误')
        self._fill_ordermain(om)
        om.fill('usname', user.USname)
        om.fill('usheader', user['USheader'])
        return Success(data=om)

    def list_omstatus(self):
        """所有试用记录状态类型"""
        res = [{'omstatus': k,
                'omstatus_en': OrderStatus(k).name,
                'omstatus_zh': OrderStatus(k).zh_value
                } for k in (OrderStatus.pending.value, OrderStatus.has_won.value,
                            OrderStatus.completed.value, OrderStatus.cancle.value,
                            OrderStatus.not_won.value,)]
        return Success(data=res)

    def list_trade(self):
        """门票购买记录"""
        # if not is_admin():
        #     raise StatusError('用户无权限')
        args = parameter_required('prid')
        prid = args.get('prid')
        product = Product.query.filter(Product.isdelete == false(), Product.PRid == prid).first_('无信息')
        tos = OrderMain.query.filter(
            OrderMain.isdelete == false(), OrderMain.PRid == prid).order_by(
            OrderMain.OMintegralpayed.desc(), OrderMain.OMstatus.desc(), OrderMain.createtime.desc()).all_with_page()
        res = []
        for to in tos:
            usinfo = db.session.query(User.USname, User.USheader
                                      ).filter(User.isdelete == false(), User.USid == to.USid).first()
            if not usinfo:
                continue
            res.append({'usname': usinfo[0],
                        'usheader': usinfo[1],
                        'omid': to.OMid,
                        'createtime': to.createtime,
                        'omstatus': to.OMstatus,
                        'omintegralpayed': to.OMintegralpayed,
                        'omstatus_zh': OrderStatus(to.OMstatus).zh_value
                        })
        trade_num, award_num = map(lambda x: db.session.query(
            func.count(OrderMain.OMid)).filter(
            OrderMain.isdelete == false(),
            OrderMain.PRid == prid,
            OrderMain.OMstatus == x, ).scalar() or 0, (
                                       OrderStatus.completed.value, OrderStatus.has_won.value))
        ticket_info = {'prid': product.PRid,
                       'prname': product.PRname,
                       'time': '{} - {}'.format(product.PRissueStartTime, product.PRissueEndTime),
                       'prstatus': product.PRstatus,
                       'prstatus_zh': ProductStatus(product.PRstatus).zh_value,
                       'trade_num': '{} / {}'.format(trade_num, product.PRnum),
                       'award_num': '{} / {}'.format(award_num, product.PRnum)}
        return Success(data={'product': ticket_info,
                             'ordermain': res})

    def _fill_ordermain(self, om):
        om.hide('USid', 'UPperid', 'UPperid2', 'UPperid3', 'PRcreateId', 'OPayno')
        om.fill('ompayType_zh', PayType(om.OMpayType).zh_value)
        om.fill('ompayType_eh', PayType(om.OMpayType).name)
        om.fill('omstatus_zh', OrderStatus(om.OMstatus).zh_value)
        om.fill('omstatus_eh', OrderStatus(om.OMstatus).name)
        om.fill('tsocreatetime', om.createtime)
        prtimelimeted = 0
        product = Product.query.filter(Product.PRid == om.PRid).first()
        if product and product.PRtimeLimeted:
            prtimelimeted = 1
            om.fill('triptime', '{} - {}'.format(product.PRuseStartTime.strftime("%Y/%m/%d %H:%M:%S"),
                                                 product.PRuseEndTime.strftime("%Y/%m/%d %H:%M:%S")))

        om.fill('prtimelimeted', prtimelimeted)

    def _opayno(self):
        opayno = self.wx_pay.nonce_str
        pp = OrderPay.query.filter_by(OPayno=opayno, isdelete=False).first()
        if pp:
            return self._opayno()
        return opayno

    def _add_pay_detail(self, **kwargs):
        with db.auto_commit():
            mountprice = kwargs.get('mount_price')
            if Decimal(str(mountprice)) <= Decimal('0'):
                # mountprice = Decimal('0.01')
                mountprice = Decimal('0.00')
            pp = OrderPay.create({
                'OPayid': str(uuid.uuid1()),
                'OPayno': kwargs.get('opayno'),
                'OPayType': kwargs.get('opayType'),
                'OPayMount': mountprice,
            })
            db.session.add(pp)

        if kwargs.get('redirect'):
            self.wechat_notify(redirect=True, pp=pp)
            return ''

        return self._pay_detail(kwargs.get('body'), float(mountprice),
                                kwargs.get('opayno'), kwargs.get('openid'))

    def _pay_detail(self, body, mount_price, opayno, openid):
        body = re.sub("[\s+\.\!\/_,$%^*(+\"\'\-_]+|[+——！，。？、~@#￥%……&*（）]+", '', body)
        current_app.logger.info('get mount price {}'.format(mount_price))
        mount_price = 0.01 if API_HOST != 'https://planet.sanbinit.cn' else mount_price  # todo 测试域名下来之后配置

        current_app.logger.info('openid is {}, out_trade_no is {} '.format(openid, opayno))
        # 微信支付的单位是'分', 支付宝使用的单位是'元'

        try:
            body = body[:16] + '...'
            current_app.logger.info('body is {}, wechatpay'.format(body))
            wechat_pay_dict = {
                'body': body,
                'out_trade_no': opayno,
                'total_fee': int(mount_price * 100),
                'attach': 'attach',
                'spbill_create_ip': request.remote_addr
            }

            if not openid:
                raise StatusError('用户未使用微信登录')
            # wechat_pay_dict.update(dict(trade_type="JSAPI", openid=openid))
            wechat_pay_dict.update({
                'trade_type': 'JSAPI',
                'openid': openid
            })
            raw = self.wx_pay.jsapi(**wechat_pay_dict)

        except WeixinPayError as e:
            raise SystemError('微信支付异常: {}'.format('.'.join(e.args)))

        return raw

    def _check_time(self, check_time):
        if not check_time:
            return
        if not isinstance(check_time, datetime):
            try:
                check_time = datetime.strptime(str(check_time), format_for_web_second)

            except:
                return ParamsError('日期格式不对，具体格式为{}'.format(format_for_web_second))

        return check_time

    def _check_date(self, check_date):
        if not check_date:
            return
        if not isinstance(check_date, date):
            try:
                check_date = datetime.strptime(str(check_date), format_forweb_no_HMS).date()

            except:
                return ParamsError('日期格式不对，具体格式为{}'.format(format_forweb_no_HMS))

        return check_date

    def _query_traded(self, prid, usid):
        return OrderMain.query.filter(OrderMain.isdelete == false(), OrderMain.PRid == prid, OrderMain.USid == usid,
                                      OrderMain.OMpayType != PayType.cash.value).first()

    @staticmethod
    def _generic_omno():
        """生成订单号"""
        return str(time.strftime('%Y%m%d%H%M%S', time.localtime(time.time()))) + \
               str(time.time()).replace('.', '')[-7:] + str(random.randint(1000, 9999))

    def _commision(self, pp):
        commision = Commision.query.filter(Commision.isdelete == False).first()
        if not commision:
            current_app.logger.error('=== 佣金分配尚未配置，分佣失败 ===')
            return

        om = OrderMain.query.filter(OrderMain.isdelete == false(), OrderMain.OPayno == pp.OPayno).first()
        if not om:
            current_app.logger.error("===订单不存在，分佣失败 OPayno = {}===".format(pp.OPayno))
            return
        # user = self._current_user()
        user = User.query.filter(User.USid == om.USid, User.isdelete == false()).first()

        if not user:
            current_app.logger.error("===用户不存在，分佣失败 omid = {} USid = {}===".format(om.OMid, om.USid))
            return

        up1, up2, up3 = om.UPperid, om.UPperid2, om.UPperid3
        # 如果付款用户有下级则自己分一部分佣金
        sub = User.query.filter(User.isdelete == false(), User.USsupper1 == user.USid).first()
        if sub:
            up1, up2, up3 = user.USid, up1, up2  # 代理商自己也会有一部分佣金
        up1_user = User.query.filter(User.isdelete == False, User.USid == up1).first()
        up2_user = User.query.filter(User.isdelete == False, User.USid == up2).first()
        up3_user = User.query.filter(User.isdelete == False, User.USid == up3).first()
        default_level1commision, default_level2commision, default_level3commision, default_planetcommision = json.loads(
            commision.Levelcommision
        )
        # 平台让利比
        deviderate = Decimal(commision.DevideRate) / 100 if commision.DevideRate else 0

        user_level1commision = Decimal(str(default_level1commision)) / 100
        user_level2commision = Decimal(str(default_level2commision)) / 100
        user_level3commision = Decimal(str(default_level3commision)) / 100
        planet_rate = Decimal(str(default_planetcommision)) / 100  # 平台抽成比例

        mountprice = Decimal(str(om.OMtrueMount))  # 根据支付实价分佣
        deviderprice = mountprice * deviderate  # 商品供应商佣金
        planet_commision = mountprice * planet_rate
        user_commision = mountprice - deviderprice - planet_commision  # 用户获得, 是总价- 供应商佣金 - 平台获得
        # 供应商佣金记录

        supplizer = Supplizer.query.filter(Supplizer.SUid == om.PRcreateId, Supplizer.isdelete == false()).first()

        commisionfor = ApplyFrom.supplizer.value if supplizer else ApplyFrom.platform.value
        suid = supplizer.SUid if supplizer else 0
        commision_account = UserCommission.create({
            'UCid': str(uuid.uuid1()),
            'OMid': om.OMid,
            'CommisionFor': commisionfor,
            'UCcommission': self._get_two_float(deviderprice),
            'USid': suid,
            'PRname': om.PRname,
            'PRimg': om.PRimg,
            'UCstatus': UserCommissionStatus.in_account.value,  # 佣金实时到账
            'FromUsid': user.USid
        })
        db.session.add(commision_account)

        if up1_user:
            up1_base = self._get_two_float(user_commision * user_level1commision)
            user_commision -= up1_base
            current_app.logger.info('一级获得佣金: {}'.format(up1_base))
            commision_account = UserCommission.create({
                'UCid': str(uuid.uuid1()),
                'OMid': om.OMid,
                'UCcommission': up1_base,
                'USid': up1_user.USid,
                'PRname': om.PRname,
                'PRimg': om.PRimg,
                'UCstatus': UserCommissionStatus.in_account.value,  # 佣金实时到账
                'FromUsid': user.USid
            })
            db.session.add(commision_account)
        if up2_user:
            up2_base = self._get_two_float(user_commision * user_level2commision)
            user_commision -= up2_base
            current_app.logger.info('二级获得佣金: {}'.format(up2_base))
            commision_account = UserCommission.create({
                'UCid': str(uuid.uuid1()),
                'OMid': om.OMid,
                'UCcommission': up2_base,
                'USid': up2_user.USid,
                'PRname': om.PRname,
                'PRimg': om.PRimg,
                'UCstatus': UserCommissionStatus.in_account.value,  # 佣金实时到账
                'FromUsid': user.USid
            })
            db.session.add(commision_account)
        if up3_user:
            up3_base = self._get_two_float(user_commision * user_level3commision)
            user_commision -= up3_base
            current_app.logger.info('三级获得佣金: {}'.format(up3_base))
            commision_account = UserCommission.create({
                'UCid': str(uuid.uuid1()),
                'OMid': om.OMid,
                'UCcommission': up3_base,
                'USid': up3_user.USid,
                'PRname': om.PRname,
                'PRimg': om.PRimg,
                'UCstatus': UserCommissionStatus.in_account.value,  # 佣金实时到账
                'FromUsid': user.USid
            })
            db.session.add(commision_account)
        planet_remain = user_commision + planet_commision
        # 平台剩余佣金
        commision_account = UserCommission.create({
            'UCid': str(uuid.uuid1()),
            'OMid': om.OMid,
            'UCcommission': planet_remain,
            'USid': '0',
            'CommisionFor': ApplyFrom.platform.value,
            'PRname': om.PRname,
            'PRimg': om.PRimg,
            'UCstatus': UserCommissionStatus.in_account.value,
            'FromUsid': user.USid
        })
        db.session.add(commision_account)
        current_app.logger.info('平台获取: {}'.format(planet_remain))

        # order_part.OPid

        # 佣金到账
        user_commisions = UserCommission.query.filter(
            UserCommission.isdelete == False,
            UserCommission.OMid == om.OMid
        ).all()
        for user_commision in user_commisions:
            # 佣金实时到账
            # user_commision.update({
            #     'UCstatus': UserCommissionStatus.in_account.value
            # })
            # db.session.add(user_commision)
            # 余额
            user_wallet = UserWallet.query.filter(
                UserWallet.isdelete == false(),
                UserWallet.USid == user_commision.USid,
                UserWallet.CommisionFor == user_commision.CommisionFor
            ).first()
            if user_wallet:
                # 余额
                user_wallet.UWbalance = Decimal(str(user_wallet.UWbalance or 0)) + \
                                        Decimal(str(user_commision.UCcommission or 0))
                # 总额 包含余额和提现金额
                user_wallet.UWtotal = Decimal(str(user_wallet.UWtotal or 0)) + \
                                      Decimal(str(user_commision.UCcommission))
                # 可提现余额 总额 减去 提现金额 和 正在提现金额
                user_wallet.UWcash = Decimal(str(user_wallet.UWcash or 0)) + \
                                     Decimal(str(user_commision.UCcommission))
                db.session.add(user_wallet)
            else:
                # 创建和更新一个逻辑 供应商创建逻辑/更新逻辑与普通用户到账逻辑一样了
                # if user_commision.CommisionFor == ApplyFrom.supplizer.value:
                #     user_wallet_instance = UserWallet.create({
                #         'UWid': str(uuid.uuid1()),
                #         'USid': user_commision.USid,
                #         'UWexpect': user_commision.UCcommission,
                #         'UWbalance': 0,
                #         'UWtotal': 0,
                #         'UWcash': 0,
                #         'CommisionFor': user_commision.CommisionFor
                #     })
                # else:
                user_wallet_instance = UserWallet.create({
                    'UWid': str(uuid.uuid1()),
                    'USid': user_commision.USid,
                    'UWbalance': user_commision.UCcommission,
                    'UWtotal': user_commision.UCcommission,
                    'UWcash': user_commision.UCcommission,
                    # 'UWexpect': user_commision.UCcommission,
                    'CommisionFor': user_commision.CommisionFor
                })
                db.session.add(user_wallet_instance)
            current_app.logger.info('佣金到账数量 {}'.format(user_commision))

    @staticmethod
    def _get_two_float(f_str, n=2):
        f_str = str(f_str)
        a, b, c = f_str.partition('.')
        c = (c + "0" * n)[:n]
        return Decimal(".".join([a, c]))

    def _ticket_order_qrcode(self, omid, usid):
        """创建票二维码"""
        from .CUser import CUser
        cuser = CUser()
        savepath, savedbpath = cuser._get_path('qrcode')
        secret_usid = cuser._base_encode(usid)
        filename = os.path.join(savepath, '{}.png'.format(omid))
        filedbname = os.path.join(savedbpath, '{}.png'.format(omid))
        current_app.logger.info('get basedir {0}'.format(current_app.config['BASEDIR']))
        text = 'omid={}&secret={}'.format(omid, secret_usid)
        current_app.logger.info('get text content {0}'.format(text))
        qrcodeWithtext(text, filename)

        # 二维码上传到七牛云
        if current_app.config.get('IMG_TO_OSS'):
            try:
                qiniu_oss.save(data=filename, filename=filedbname[1:])
            except Exception as e:
                current_app.logger.error('二维码转存七牛云失败 ： {}'.format(e))
        return filedbname

    def product_score_award(self, product):
        if not product:
            return
        count = 0
        oms = OrderMain.query.filter(OrderMain.isdelete == false(), OrderMain.PRid == product.PRid,
                                     OrderMain.OMstatus == OrderStatus.pending.value,
                                     OrderMain.OMpayType == PayType.scorepay.value,
                                     ).order_by(OrderMain.OMintegralpayed.desc(),
                                                OrderMain.createtime.desc()).limit(product.PRnum).all()
        omids = []
        for om in oms:
            omids.append(om.OMid)
            om.OMstatus = OrderStatus.has_won.value
            om.OMqrcode = self._ticket_order_qrcode(om.OMid, om.USid)
        # 未中的
        not_won_oms = OrderMain.query.filter(OrderMain.isdelete == false(),
                                             OrderMain.OMid.notin_(omids),
                                             OrderMain.PRid == product.PRid,
                                             OrderMain.OMstatus == OrderStatus.pending.value,
                                             OrderMain.OMpayType == PayType.scorepay.value).all()
        for nom in not_won_oms:
            nom.OMstatus = OrderStatus.not_won.value
            current_app.logger.info('not won order, omid: {}'.format(nom.OMid))
            count += 1
        current_app.logger.info('总名额: {}, 中签数: {}, 未中数: {}'.format(product.PRnum, len(oms), count))

    @staticmethod
    def _current_user(msg=None):
        return User.query.filter(User.isdelete == false(), User.USid == getattr(request, 'user').id).first_(msg)

    def _cancle(self, order_main):
        with db.auto_commit():
            # 主单状态修改
            order_main.OMstatus = OrderStatus.cancle.value
            omid = order_main.OMid
            db.session.add(order_main)

            # 库存修改
            # 库存不限量 暂时去除 0624
            # product = Product.query.filter(Product.PRid == order_main.PRid, Product.isdelete == false()).first()
            # if product:
            #     product.PRnum += 1
            #     db.session.add(product)

            # 扣除月销量
            today = datetime.now()
            month_sale_instance = ProductMonthSaleValue.query.filter(
                ProductMonthSaleValue.isdelete == false(),
                ProductMonthSaleValue.PRid == order_main.PRid,
                extract('month', ProductMonthSaleValue.createtime) == today.month,
                extract('year', ProductMonthSaleValue.createtime) == today.year,
            ).first()
            if month_sale_instance:
                month_sale_instance.update({'PMSVnum': month_sale_instance.PMSVnum - 1})
                db.session.add(month_sale_instance)

    @token_required
    def history_detail(self):
        if not is_supplizer() and not is_admin():
            raise AuthorityError()
        days = request.args.to_dict().get('days')
        if days:
            days = days.replace(' ', '').split(',')
            days = list(map(lambda x: datetime.strptime(x, '%Y-%m-%d').date(), days))
        else:
            days = []
        suid = request.user.id if is_supplizer() else None
        datas = []
        for day in days:
            data = {
                'day_total': self._history_order('total', day=day,
                                                 status=(OrderMain.OMstatus > OrderStatus.pending.value,
                                                         OrderMain.OMpayType == PayType.cash.value),
                                                 suid=suid),
                'day_count': self._history_order('count', day=day, suid=suid),
                'wai_pay_count': self._history_order('count', day=day,
                                                     status=(OrderMain.OMstatus == OrderStatus.wait_pay.value,),
                                                     suid=suid),
                # 'in_refund': self._inrefund(day=day, suid=suid),
                'in_refund': 0,
                'day': day
            }
            datas.append(data)
        if not days:
            # 获取系统全部
            data = {
                'day_total': self._history_order('total',
                                                 status=(OrderMain.OMstatus > OrderStatus.pending.value,
                                                         OrderMain.OMpayType == PayType.cash.value),
                                                 suid=suid),
                'day_count': self._history_order('count', suid=suid),
                'wai_pay_count': 0,
                'in_refund': 0,
                'day': None
            }
            datas.append(data)
        return Success(data=datas)

    def _history_order(self, *args, **kwargs):
        with db.auto_commit() as session:
            status = kwargs.get('status', None)
            day = kwargs.get('day', None)
            suid = kwargs.get('suid', None)
            if 'total' in args:
                query = session.query(func.sum(OrderMain.OMtrueMount))
            elif 'count' in args:
                query = session.query(func.count(OrderMain.OMid))
            # elif 'refund' in args:
            #     return self._inrefund(*args, **kwargs)
            query = query.filter(OrderMain.isdelete == False)
            if status is not None:
                query = query.filter(*status)
            if day is not None:
                query = query.filter(
                    cast(OrderMain.createtime, Date) == day,
                )
            if suid is not None:
                query = query.filter(OrderMain.PRcreateId == suid)
            return query.first()[0] or 0
