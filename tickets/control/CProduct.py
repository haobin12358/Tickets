import json
import random
import uuid
from datetime import datetime
from flask import request, current_app
from sqlalchemy import false, func, cast, Date

from tickets.common.playpicture import PlayPicture
from tickets.config.enums import UserStatus, ProductStatus, ShareType, RoleType, OrderStatus, PayType, \
    ActivationTypeEnum, AdminActionS, ProductFrom, ApplyStatus
from tickets.config.http_config import API_HOST
from tickets.control.BaseControl import BaseAdmin, BaseApproval
from tickets.control.CActivation import CActivation
from tickets.control.CFile import CFile
from tickets.control.CUser import CUser
from tickets.extensions.error_response import ParamsError, AuthorityError, StatusError
from tickets.extensions.interface.user_interface import admin_required, is_admin, is_supplizer, phone_required, is_user, \
    token_required
from tickets.extensions.params_validates import parameter_required, validate_arg, validate_price
from tickets.extensions.register_ext import db
from tickets.extensions.success_response import Success
from tickets.extensions.tasks import add_async_task, start_product, end_product, cancel_async_task
from tickets.models import Supplizer, Product, User, Agreement, OrderMain, UserInvitation, SharingType, ProductVerifier, \
    ProductVerifiedRecord, ProductMonthSaleValue, Approval


class CProduct(object):
    cuser = CUser()
    cactivation = CActivation()
    base_admin = BaseAdmin()
    base_approval = BaseApproval()

    def list_product(self):
        """商品列表"""
        args = request.args.to_dict()
        filter_args = []
        if not (is_admin() or is_supplizer()):
            filter_args.append(Product.PRstatus != ProductStatus.interrupt.value)
        if is_supplizer():
            filter_args.append(Product.SUid == getattr(request, 'user').id)
        prlimited = args.get('prtimelimeted')
        if str(prlimited) in '01':
            filter_args.append(Product.PRtimeLimeted == prlimited)
        products = Product.query.filter(Product.isdelete == false(), *filter_args
                                        ).order_by(func.field(Product.PRstatus, ProductStatus.active.value,
                                                              ProductStatus.ready.value, ProductStatus.over.value),
                                                   Product.PRissueStartTime.asc(),
                                                   Product.createtime.desc()).all_with_page()
        products_fields = ['PRid', 'PRname', 'PRimg', 'PRlinePrice', 'PRtruePrice', 'PRnum', 'PRtimeLimeted',
                           'PRstatus', 'prstatus_zh', 'apply_num', 'PRissueStartTime', 'PRissueEndTime',
                           'PRuseStartTime', 'PRuseEndTime', 'interrupt', 'apply_num_str', 'buyer_avatar',
                           'start_time_str']
        for product in products:
            self._fill_product(product)
            product.fields = products_fields
            if not product.PRtimeLimeted:
                product.PRnum = '无限量'
        return Success(data=products)

    def get_product(self):
        """商品详情"""
        args = parameter_required(('prid',))
        prid = args.get('prid')
        secret_usid = args.get('secret_usid')
        if secret_usid:  # 创建邀请记录
            self._invitation_record(secret_usid, args)
        product = Product.query.filter(Product.isdelete == false(), Product.PRid == prid).first_('商品已下架')
        self._fill_product(product)

        month_sale_value = self._fill_month_sale_value(prid)
        product.fill('month_sale_value', month_sale_value)
        return Success(data=product)

    @staticmethod
    def _fill_month_sale_value(prid):
        month_sale_instance = ProductMonthSaleValue.query.filter(ProductMonthSaleValue.isdelete == false(),
                                                                 ProductMonthSaleValue.PRid == prid
                                                                 ).order_by(ProductMonthSaleValue.createtime.desc()
                                                                            ).first()
        with db.auto_commit():
            if not month_sale_instance:
                salevolume_dict = {'PMSVid': str(uuid.uuid1()),
                                   'PRid': prid,
                                   'PMSVfakenum': random.randint(15, 100)
                                   }
                month_sale_value = salevolume_dict['PMSVfakenum']
                current_app.logger.info('没有销量记录，现在创建 >>> {}'.format(month_sale_value))

            elif month_sale_instance.createtime.month != datetime.now().month:
                month_sale_value = getattr(month_sale_instance, 'PMSVnum')
                month_sale_value = random.randint(15, 100) if month_sale_value < 15 else month_sale_value

                salevolume_dict = {'PMSVid': str(uuid.uuid1()),
                                   'PRid': prid,
                                   'PMSVfakenum': month_sale_value
                                   }
                current_app.logger.info('没有本月销量记录，现在创建 >>> {}'.format(month_sale_value))

            else:
                salevolume_dict = None
                month_sale_value = getattr(month_sale_instance, 'PMSVnum')
                current_app.logger.info('存在本月销量 {}'.format(month_sale_value))
                if month_sale_value < 15:
                    month_sale_value = random.randint(15, 100)
                    month_sale_instance.update({'PMSVfakenum': month_sale_value})
                    db.session.add(month_sale_instance)
                    current_app.logger.info('本月销量更新为 {}'.format(month_sale_value))
            if salevolume_dict:
                db.session.add(ProductMonthSaleValue.create(salevolume_dict))
        return month_sale_value

    def _fill_product(self, product):
        product.hide('CreatorId', 'CreatorType')
        product.fill('prstatus_zh', ProductStatus(product.PRstatus).zh_value)
        product.fill('interrupt', False if product.PRstatus < ProductStatus.interrupt.value else True)  # 是否中止
        now = datetime.now()
        role_type = 'productrole'
        countdown = None
        if product.PRtimeLimeted:
            role_type = 'ticketrole'
            if product.PRstatus == ProductStatus.ready.value and product.PRissueStartTime > now:  # 距抢票开始倒计时
                countdown = product.PRissueStartTime - now
            elif product.PRstatus == ProductStatus.active.value and product.PRissueEndTime > now:  # 距抢票结束倒计时
                countdown = product.PRissueEndTime - now
            if countdown:
                hours = str(countdown.days * 24 + (countdown.seconds // 3600))
                minutes = str((countdown.seconds % 3600) // 60)
                seconds = str((countdown.seconds % 3600) % 60)
                countdown = "{}:{}:{}".format('0' + hours if len(hours) == 1 else hours,
                                              '0' + minutes if len(minutes) == 1 else minutes,
                                              '0' + seconds if len(seconds) == 1 else seconds)
                # product.fill('triptime', '{} - {}'.format(product.PRuseStartTime.strftime("%Y/%m/%d %H:%M:%S"),
                #                                           product.PRuseEndTime.strftime("%Y/%m/%d %H:%M:%S")))
        product.fill('countdown', countdown)
        product.fill('prstatus_zh', ProductStatus(product.PRstatus).zh_value)
        product.fill('interrupt', False if product.PRstatus < ProductStatus.interrupt.value else True)
        product.fill('tirules', self._query_rules(getattr(RoleType, role_type).value))
        product.fill('scorerule', self._query_rules(RoleType.activationrole.value))
        apply_num = self._query_award_num(product)
        product.fill('apply_num', apply_num)  # 已申请人数

        # ------ 0624 前台改版后补充字段 ------
        apply_num_str = f'{round(apply_num / 10000, 1)}w人参与' if apply_num > 10000 else f'{apply_num}人已参与'
        product.fill('apply_num_str', apply_num_str)
        buyer_avatar = []
        if apply_num:
            buyer_avatar = [i[0] if i[0].startswith('http') else API_HOST + i[0]
                            for i in db.session.query(User.USheader
                                                      ).filter(OrderMain.OMstatus >= OrderStatus.pending.value,
                                                               OrderMain.PRid == product.PRid,
                                                               OrderMain.USid == User.USid).limit(2).all()]
        product.fill('buyer_avatar', buyer_avatar)
        start_time_str = product.PRissueStartTime.strftime(
            '%m月%d日%H:%M') if product.PRtimeLimeted and product.PRstatus == ProductStatus.ready.value else ''
        product.fill('start_time_str', start_time_str)
        # -----------------------------------

        # show_record = True if product.PRstatus == ProductStatus.over.value else False
        # product.fill('show_record', show_record)  # 0618 fix 目前无需"动态"区域出现
        current_user = User.query.filter(User.isdelete == false(),
                                         User.USid == getattr(request, 'user').id).first() if is_user() else None
        verified = True if current_user and getattr(current_user, 'USidentification') else False
        product.fill('verified', verified)  # 是否已信用认证
        product.fill('position', {'tiaddress': product.address,
                                  'longitude': product.longitude,
                                  'latitude': product.latitude})
        traded = False
        if is_user() and product.PRtimeLimeted:
            traded = self._query_traded(product.PRid, getattr(request, 'user').id)
            if traded:
                scorerank, rank = self._query_single_score(traded, product)
                product.fill('scorerank', scorerank)  # 活跃分排名array
                product.fill('rank', rank)  # 自己所在排名
        product.fill('traded', bool(traded))  # 打开限时商品时检测是否已购买

    def _query_single_score(self, order_main, product):
        prnum = product.PRnum
        if order_main.OMpayType == PayType.cash.value or order_main.OMstatus > OrderStatus.pending.value:
            return [], 1
        tsoid_array = [i[0] for i in db.session.query(OrderMain.OMid).filter(
            OrderMain.isdelete == false(),
            OrderMain.PRid == order_main.PRid,
            OrderMain.OMstatus == OrderStatus.pending.value,
        ).order_by(OrderMain.OMintegralpayed.desc(),
                   OrderMain.createtime.asc(),
                   origin=True).all() if i is not None]
        res = [self._init_score_dict(order_main.OMid, '我的位置')]
        rank = 1
        if tsoid_array and len(tsoid_array) > 1:
            my_index = tsoid_array.index(order_main.OMid)
            rank = my_index + 1
            if my_index == 0:
                res.append(self._init_score_dict(tsoid_array[my_index + 1], '后一名'))
            elif my_index == len(tsoid_array) - 1:
                temp_index = prnum - 1 if rank > prnum else my_index - 1
                res.insert(0, self._init_score_dict(tsoid_array[temp_index], '前一名'))
            else:
                temp_index = prnum - 1 if rank > prnum else my_index - 1
                res.insert(0, self._init_score_dict(tsoid_array[temp_index], '前一名'))
                res.append(self._init_score_dict(tsoid_array[my_index + 1], '后一名'))
        return res, rank

    @staticmethod
    def _init_score_dict(tsoid, rank_zh):
        score_info = db.session.query(OrderMain.OMintegralpayed, User.USheader).outerjoin(
            User, User.USid == OrderMain.USid).filter(User.isdelete == false(), OrderMain.isdelete == false(),
                                                      OrderMain.OMid == tsoid).first()
        res = None
        if score_info:
            res = {'tsoactivation': score_info[0] or 0,
                   'usheader': score_info[1] if score_info[1].startswith('http') else API_HOST + score_info[1],
                   'rank_zh': rank_zh}
        return res

    def _invitation_record(self, secret_usid, args):
        try:
            superid = self.cuser._base_decode(secret_usid)
            current_app.logger.info('secret_usid --> superid {}'.format(superid))
            if is_user() and superid != getattr(request, 'user').id:
                with db.auto_commit():
                    today = datetime.now().date()
                    uin_exist = UserInvitation.query.filter(
                        cast(UserInvitation.createtime, Date) == today,
                        UserInvitation.USInviter == superid,
                        UserInvitation.USInvited == getattr(request, 'user').id,
                    ).first()
                    if uin_exist:
                        current_app.logger.info('{}今天已经邀请过这个人了{}'.format(superid, getattr(request, 'user').id))
                        return
                    uin = UserInvitation.create({
                        'UINid': str(uuid.uuid1()),
                        'USInviter': superid,
                        'USInvited': getattr(request, 'user').id,
                        'UINapi': request.path
                    })
                    current_app.logger.info('已创建邀请记录')
                    db.session.add(uin)
                    db.session.add(SharingType.create({
                        'STid': str(uuid.uuid1()),
                        'USid': superid,
                        'STtype': args.get('sttype', 0)
                    }))
                    self.cactivation.add_activation(
                        ActivationTypeEnum.share_old.value, superid, getattr(request, 'user').id)
        except Exception as e:
            current_app.logger.info('secret_usid 记录失败 error = {}'.format(e))

    @staticmethod
    def _query_rules(ruletype):
        return db.session.query(Agreement.AMcontent).filter(Agreement.isdelete == false(),
                                                            Agreement.AMtype == ruletype).scalar()

    @staticmethod
    def _query_award_num(product, filter_status=None):
        if not filter_status:
            filter_status = (OrderMain.OMstatus >= OrderStatus.pending.value,)
        count = db.session.query(func.count(OrderMain.OMid)
                                 ).filter(OrderMain.isdelete == false(),
                                          OrderMain.PRid == product.PRid,
                                          *filter_status
                                          ).scalar() or 0
        return count

    @staticmethod
    def _query_traded(prid, usid):
        return OrderMain.query.filter(OrderMain.isdelete == false(), OrderMain.PRid == prid, OrderMain.USid == usid,
                                      OrderMain.OMpayType != PayType.cash.value).first()

    @token_required
    def create_product(self):
        """创建商品"""
        if is_admin():
            product_from = ProductFrom.platform.value
        elif is_supplizer():
            product_from = ProductFrom.supplizer.value
        else:
            raise AuthorityError('当前用户无权进行该操作')
        data = request.json
        product_dict = self._validate_ticket_param(data)
        if Product.query.filter(Product.isdelete == false(), Product.PRname == data.get('prname')).first():
            raise ParamsError('该商品名称已存在')
        with db.auto_commit():
            product_dict.update({'PRid': str(uuid.uuid1()),
                                 'CreatorId': getattr(request, 'user').id,
                                 'CreatorType': getattr(request, 'user').model,
                                 'PRname': data.get('prname'),
                                 'PRimg': data.get('primg'),
                                 'PRdetails': data.get('prdetails'),
                                 # 'PRstatus': ProductStatus.ready.value if product_dict.get(
                                 #     'PRtimeLimeted') else ProductStatus.active.value,
                                 'PRstatus': ProductStatus.pending.value
                                 })
            product = Product.create(product_dict)
            db.session.add(product)
        # 0702 增加审批
        # if product.PRtimeLimeted:  # 限时商品，添加异步任务
        #     add_async_task(func=start_product, start_time=product.PRissueStartTime, func_args=(product.PRid,),
        #                    conn_id='start_product{}'.format(product.PRid))
        #     add_async_task(func=end_product, start_time=product.PRissueEndTime, func_args=(product.PRid,),
        #                    conn_id='end_product{}'.format(product.PRid))
        self.base_approval.create_approval('toshelves', request.user.id, product.PRid, product_from)
        self.base_admin.create_action(AdminActionS.insert.value, 'Product', product.PRid)
        return Success('创建成功', data={'prid': product.PRid})

    @token_required
    def update_product(self):
        """编辑商品"""
        if is_admin():
            product_from = ProductFrom.platform.value
        elif is_supplizer():
            product_from = ProductFrom.supplizer.value
        else:
            raise AuthorityError('当前用户无权进行该操作')
        data = parameter_required('prid')
        product = Product.query.filter(Product.isdelete == false(),
                                       Product.PRid == data.get('prid')).first_('未找到该商品信息')
        if Product.query.filter(Product.isdelete == false(), Product.PRname == data.get('prname'),
                                Product.PRid != Product.PRid, Product.PRstatus != ProductStatus.over.value).first():
            raise ParamsError('该商品名已存在')
        approval_flag = 0
        with db.auto_commit():
            if data.get('delete'):
                if product.PRstatus == ProductStatus.active.value:
                    raise ParamsError('无法直接删除正在发放中的商品')
                if OrderMain.query.filter(OrderMain.isdelete == false(),
                                          OrderMain.OMstatus > OrderStatus.not_won.value,
                                          OrderMain.PRid == product.PRid).first():
                    raise StatusError('暂时无法直接删除已产生购买记录的商品')
                product.update({'isdelete': True})
                # 取消异步任务
                cancel_async_task('start_product{}'.format(product.PRid))
                cancel_async_task('end_product{}'.format(product.PRid))
                self.base_admin.create_action(AdminActionS.delete.value, 'Product', product.PRid)
                # 同时将正在进行的审批流改为取消
                self.base_approval.cancel_approval(product.PRid, request.user.id)
            elif data.get('interrupt'):
                if product.PRstatus > ProductStatus.active.value:
                    raise StatusError('该状态下无法中止')
                product.update({'PRstatus': ProductStatus.interrupt.value})
                cancel_async_task('start_product{}'.format(product.PRid))
                cancel_async_task('end_product{}'.format(product.PRid))
                self.base_admin.create_action(AdminActionS.update.value, 'Product', product.PRid)
                # 同时将正在进行的审批流改为取消
                self.base_approval.cancel_approval(product.PRid, request.user.id)
            else:
                approval_flag = 1
                if product.PRstatus < ProductStatus.interrupt.value:
                    raise ParamsError('仅可编辑已中止发放或已结束的商品')
                product_dict = self._validate_ticket_param(data)
                product_dict.update({'PRname': data.get('prname'),
                                     'PRimg': data.get('primg'),
                                     'PRdetails': data.get('prdetails'),
                                     # 'PRstatus': ProductStatus.ready.value if product_dict.get(
                                     #     'PRtimeLimeted') else ProductStatus.active.value,
                                     'PRstatus': ProductStatus.pending.value
                                     })
                self.base_approval.cancel_approval(product.PRid, request.user.id)  # 同时将正在进行的审批流改为取消
                if product.PRstatus == ProductStatus.interrupt.value:  # 中止的情况
                    current_app.logger.info('edit interrupt ticket')
                    product.update(product_dict, null='not')
                else:  # 已结束的情况，重新发起
                    current_app.logger.info('edit ended ticket')
                    product_dict.update({'PRid': str(uuid.uuid1()),
                                         'CreatorId': getattr(request, 'user').id,
                                         'CreatorType': getattr(request, 'user').model})
                    product = Product.create(product_dict)
                cancel_async_task('start_product{}'.format(product.PRid))
                cancel_async_task('end_product{}'.format(product.PRid))

                self.base_admin.create_action(AdminActionS.insert.value, 'Product', product.PRid)
            db.session.add(product)
        if approval_flag:
            self.base_approval.create_approval('toshelves', request.user.id, product.PRid, product_from)
        return Success('编辑成功', data={'prid': product.PRid})

    def _validate_ticket_param(self, data):
        valid_dict = {'prname': '商品名称', 'primg': '封面图', 'purchaseprice': '采购价',
                      'suid': '供应商', 'prtimelimeted': '是否为限时商品',
                      'prnum': '数量', 'prdetails': '详情', 'prbanner': '轮播图', 'address': '定位地点'
                      }
        prtimelimeted = data.get('prtimelimeted') or 0
        if prtimelimeted:
            valid_dict.update({'prissuestarttime': '发放开始时间',
                               'prissueendtime': '发放结束时间',
                               'prusestarttime': '使用开始时间',
                               'pruseendtime': '使用结束时间'})
        parameter_required(valid_dict, datafrom=data)
        prissuestarttime = prissueendtime = prusestarttime = pruseendtime = None
        if prtimelimeted:
            prissuestarttime = validate_arg(r'^\d{4}(-\d{2}){2} \d{2}(:\d{2}){2}$', str(data.get('prissuestarttime')),
                                            '发放开始时间错误')
            prissueendtime = validate_arg(r'^\d{4}(-\d{2}){2} \d{2}(:\d{2}){2}$', str(data.get('prissueendtime')),
                                          '发放结束时间错误')
            prissuestarttime, prissueendtime = map(lambda x: datetime.strptime(x, '%Y-%m-%d %H:%M:%S'),
                                                   (prissuestarttime, prissueendtime))

            now = datetime.now()
            if prissuestarttime < now:
                raise ParamsError('发放开始时间应大于现在时间')
            if prissueendtime <= prissuestarttime:
                raise ParamsError('发放结束时间应大于开始时间')
            prusestarttime = validate_arg(r'^\d{4}(-\d{2}){2} \d{2}(:\d{2}){2}$', str(data.get('prusestarttime')),
                                          '使用开始时间')
            pruseendtime = validate_arg(r'^\d{4}(-\d{2}){2} \d{2}(:\d{2}){2}$', str(data.get('pruseendtime')),
                                        '使用结束时间')
            prusestarttime, pruseendtime = map(lambda x: datetime.strptime(x, '%Y-%m-%d %H:%M:%S'),
                                               (prusestarttime, pruseendtime))
            if prusestarttime < now:
                raise ParamsError('使用开始时间应大于现在时间')
            if prusestarttime < prissueendtime:
                raise ParamsError('使用开始时间不能小于发放结束时间')
            if pruseendtime <= prusestarttime:
                raise ParamsError('使用结束时间应大于开始时间')

        # prlineprice, prtrueprice = map(lambda x: validate_price(x, can_zero=False),  # 0702 改为采购价
        #                                (data.get('prlineprice'), data.get('prtrueprice')))
        purchaseprice = validate_price(data.get('purchaseprice'), can_zero=False)
        latitude, longitude = self.check_lat_and_long(data.get('latitude'), data.get('longitude'))
        prnum = data.get('prnum') if prtimelimeted else 99999999
        if not isinstance(prnum, int) or int(prnum) <= 0:
            raise ParamsError('请输入合理的商品数量')

        if not isinstance(data.get('prbanner'), list):
            raise ParamsError('prbanner 格式错误')
        prbanner = json.dumps(data.get('prbanner'))
        sup = Supplizer.query.filter(Supplizer.isdelete == false(), Supplizer.SUid == data.get('suid'),
                                     Supplizer.SUstatus == UserStatus.usual.value).first_('选择供应商异常')
        product_dict = {'PRissueStartTime': prissuestarttime,
                        'PRissueEndTime': prissueendtime,
                        'PRuseStartTime': prusestarttime,
                        'PRuseEndTime': pruseendtime,
                        'PRtimeLimeted': prtimelimeted,
                        'PurchasePrice': purchaseprice,
                        # 'PRtruePrice': prtrueprice,
                        'PRnum': prnum,
                        'PRbanner': prbanner,
                        'SUid': sup.SUid,
                        'longitude': longitude,
                        'latitude': latitude,
                        'address': data.get('address')
                        }
        return product_dict

    @staticmethod
    def check_lat_and_long(lat, long):
        try:
            if not -90 <= float(lat) <= 90:
                raise ParamsError('纬度错误，范围 -90 ~ 90')
            if not -180 <= float(long) <= 180:
                raise ParamsError('经度错误，范围 -180 ~ 180')
        except (TypeError, ValueError):
            raise ParamsError('经纬度应为合适范围内的浮点数')
        return str(lat), str(long)

    @phone_required
    def product_verified(self):
        """商品核销"""
        data = parameter_required('param')
        param = data.get('param')
        try:
            omid, secret_usid = str(param).split('&')
            if not omid.startswith('omid'):
                raise ValueError
        except ValueError:
            raise ParamsError('该二维码无效')
        current_app.logger.info('omid: {}, secret_usid: {}'.format(omid, secret_usid))
        omid = str(omid).split('=')[-1]
        secret_usid = str(secret_usid).split('=')[-1]
        current_app.logger.info('splited, omid: {}, secret_usid: {}'.format(omid, secret_usid))
        if not omid or not secret_usid:
            raise StatusError('该试用码无效')
        ticket_usid = self.cuser._base_decode(secret_usid)
        ticket_user = User.query.filter(User.isdelete == false(),
                                        User.USid == ticket_usid).first_('无效试用码')
        om = OrderMain.query.filter(OrderMain.isdelete == false(),
                                    OrderMain.OMid == omid).first_('订单状态异常')
        if om.OMstatus != OrderStatus.has_won.value:
            current_app.logger.error('om status: {}'.format(om.TSOstatus))
            raise StatusError('提示：该二维码已被核销过')
        pr = Product.query.filter(Product.PRid == om.PRid).first()
        if pr.PRtimeLimeted and (pr.PRuseStartTime <= datetime.now() <= pr.PRuseEndTime):
            raise StatusError('当前时间不在该券有效使用时间内')

        user = User.query.join(ProductVerifier, ProductVerifier.PVphone == User.UStelephone
                               ).join(Product, Product.SUid == ProductVerifier.SUid
                                      ).filter(User.isdelete == false(), User.USid == getattr(request, 'user').id,
                                               ProductVerifier.SUid == pr.SUid
                                               ).first_('请确认您是否拥有该券的核销权限')

        with db.auto_commit():
            # 订单改状态
            om.update({'OMstatus': OrderStatus.completed.value})
            db.session.add(om)
            # 核销记录
            tvr = ProductVerifiedRecord.create({'PVRid': str(uuid.uuid1()),
                                                'ownerId': ticket_user.USid,
                                                'VerifierId': user.USid,
                                                'OMid': om.OMid,
                                                'param': param})
            db.session.add(tvr)
        return Success('二维码验证成功', data=tvr.PVRid)

    def _check_time(self, time_model, fmt='%Y/%m/%d'):
        if isinstance(time_model, datetime):
            return time_model.strftime(fmt)
        else:
            try:
                return datetime.strptime(str(time_model), '%Y-%m-%d %H:%M:%S').strftime(fmt)
            except:
                current_app.logger.error('时间转换错误')
                raise StatusError('系统异常，请联系客服解决')

    @phone_required
    def get_promotion(self):
        data = parameter_required('prid')
        user = User.query.filter(User.isdelete == false(), User.USid == getattr(request, 'user').id).first_('请重新登录')
        prid = data.get('prid')
        params = data.get('params')
        product = Product.query.filter(
            Product.PRid == prid, Product.PRstatus < ProductStatus.interrupt.value,
            Product.isdelete == false()).first_('活动已结束')

        usid = user.USid
        starttime = endtime = starttime_g = endtime_g = None
        if product.PRtimeLimeted:
            starttime = self._check_time(product.PRuseStartTime)
            endtime = self._check_time(product.PRuseEndTime, fmt='%m/%d')

            starttime_g = self._check_time(product.PRissueStartTime)
            endtime_g = self._check_time(product.PRissueEndTime, fmt='%m/%d')

        # 获取微信二维码
        from ..control.CUser import CUser
        cuser = CUser()
        if not params or 'page=' not in params:
            params = 'page=/pages/index/freeDetail'
        if 'prid' not in params:
            params = '{}&prid={}'.format(params, prid)
        if 'secret_usid' not in params:
            params = '{}&secret_usid={}'.format(params, cuser._base_encode(usid))
        params = '{}&sttype={}'.format(params, ShareType.promotion.value)
        params_key = cuser.shorten_parameters(params, usid, 'params')
        wxacode_path = cuser.wxacode_unlimit(
            usid, {'params': params_key}, img_name='{}{}'.format(usid, prid), is_hyaline=True)
        local_path, promotion_path = PlayPicture().create_ticket(
            product.PRimg, product.PRname, str(0), usid, prid, wxacode_path, product.PRlinePrice,
            product.PRtruePrice, starttime, endtime, starttime_g, endtime_g)

        CFile().upload_to_oss(local_path, promotion_path[1:], '商品推广图')

        scene = cuser.dict_to_query_str({'params': params_key})
        current_app.logger.info('get scene = {}'.format(scene))
        return Success(data={
            'promotion_path': promotion_path,
            'scene': scene
        })
