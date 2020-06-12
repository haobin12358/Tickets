import json
import uuid
from datetime import datetime
from flask import request
from sqlalchemy import false, func
from tickets.config.enums import UserStatus, ProductStatus
from tickets.extensions.error_response import ParamsError, AuthorityError
from tickets.extensions.interface.user_interface import admin_required, is_admin, is_supplizer, phone_required, is_user
from tickets.extensions.params_validates import parameter_required, validate_arg, validate_price
from tickets.extensions.register_ext import db
from tickets.extensions.success_response import Success
from tickets.models import Supplizer, Product, User


class CProduct(object):

    def list_product(self):
        """商品列表"""
        args = request.args.to_dict()
        filter_args = []
        if not is_admin():
            filter_args.append(Product.PRstatus != ProductStatus.interrupt.value)
        if is_supplizer():
            filter_args.append(Product.SUid == getattr(request, 'user').id)
        products = Product.query.filter(Product.isdelete == false(), *filter_args
                                        ).order_by(func.field(Product.PRstatus, ProductStatus.active.value,
                                                              ProductStatus.ready.value, ProductStatus.over.value),
                                                   Product.PRissueStartTime.asc(),
                                                   Product.createtime.desc()).all_with_page()
        products_fields = ['PRid', 'PRname', 'PRimg', 'PRlinePrice', 'PRtruePrice', 'PRnum', 'PRtimeLimeted',
                           'PRstatus']
        for product in products:
            product.fields = products_fields
            product.fill('prstatus_zh', ProductStatus(product.PRstatus).zh_value)
        return Success(data=products)

    def get_product(self):
        """商品详情"""
        args = parameter_required(('prid',))
        prid = args.get('prid')
        secret_usid = args.get('secret_usid')
        product = Product.query.filter(Product.isdelete == false(), Product.PRid == prid).first_('未找到商品信息')
        self._fill_product(product)
        return Success(data=product)

    def _fill_product(self, product):
        product.hide('CreatorId', 'CreatorType', 'SUid', 'address', 'longitude', 'latitude')
        now = datetime.now()
        if product.PRtimeLimeted:
            if product.PRstatus == ProductStatus.ready.value and product.PRissueStartTime > now:  # 距抢票开始倒计时
                countdown = product.PRissueStartTime - now
            elif product.PRstatus == ProductStatus.active.value and product.PRissueEndTime > now:  # 距抢票结束倒计时
                countdown = product.PRissueEndTime - now
            else:
                countdown = None
            if countdown:
                hours = str(countdown.days * 24 + (countdown.seconds // 3600))
                minutes = str((countdown.seconds % 3600) // 60)
                seconds = str((countdown.seconds % 3600) % 60)
                countdown = "{}:{}:{}".format('0' + hours if len(hours) == 1 else hours,
                                              '0' + minutes if len(minutes) == 1 else minutes,
                                              '0' + seconds if len(seconds) == 1 else seconds)

            product.fill('countdown', countdown)
        product.fill('prstatus_zh', ProductStatus(product.PRstatus).zh_value)
        # product.fill('scorerule', self._query_rules(RoleType.activationrole.value))
        # ticket.fill('ticategory', json.loads(ticket.TIcategory))  # 2.0版多余
        verified = True if is_user() and User.query.filter(User.isdelete == false(),
                                                           User.USid == getattr(request, 'user').id
                                                           ).first().USidentification else False
        product.fill('verified', verified)
        product.fill('position', {'tiaddress': product.address,
                                  'longitude': product.longitude,
                                  'latitude': product.latitude})

    def create_product(self):
        """创建商品"""
        if not (is_admin or is_supplizer):
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
                                 'PRstatus': ProductStatus.ready.value if product_dict.get(
                                     'PRtimeLimeted') else ProductStatus.active.value
                                 })
            product = Product.create(product_dict)
            db.session.add(product)
        # if product.PRtimeLimeted:

        # todo 分限时 不 限时
        # 异步任务: 开始
        # self._create_celery_task(ticket.TIid, ticket_dict.get('TIstartTime'))
        # # 异步任务: 结束
        # self._create_celery_task(ticket.TIid, ticket_dict.get('TIendTime'), start=False)
        # self.BaseAdmin.create_action(AdminActionS.insert.value, 'Ticket', ticket.TIid)
        return Success('创建成功', data={'prid': product.PRid})

    @admin_required
    def update_product(self):
        """编辑商品"""
        data = parameter_required('prid')
        product = Product.query.filter(Product.isdelete == false(),
                                       Product.PRid == data.get('prid')).first_('未找到该商品信息')
        if Product.query.filter(Product.isdelete == false(), Product.PRname == data.get('prname'),
                                Product.PRid != Product.PRid, Product.PRstatus != ProductStatus.over.value).first():
            raise ParamsError('该商品名已存在')
        with db.auto_commit():
            if data.get('delete'):
                if product.PRstatus == ProductStatus.active.value:
                    raise ParamsError('无法直接删除正在发放中的商品')
                # if TicketsOrder.query.filter(TicketsOrder.isdelete == false(),
                #                              TicketsOrder.TSOstatus != TicketsOrderStatus.not_won.value,
                #                              TicketsOrder.TIid == ticket.TIid).first():
                #     raise StatusError('暂时无法直接删除已产生购买记录的门票')
                # ticket.update({'isdelete': True})
                # TicketLinkage.query.filter(TicketLinkage.isdelete == false(),
                #                            TicketLinkage.TIid == ticket.TIid).delete_(synchronize_session=False)
                # self._cancle_celery_task('start_ticket{}'.format(ticket.TIid))
                # self._cancle_celery_task('end_ticket{}'.format(ticket.TIid))
                # self.BaseAdmin.create_action(AdminActionS.delete.value, 'Ticket', ticket.TIid)
            # elif data.get('interrupt'):
            # if ticket.TIstatus > TicketStatus.active.value:
            #     raise StatusError('该状态下无法中止')
            # if ticket.TIstatus == TicketStatus.active.value:  # 抢票中的退押金
            #     current_app.logger.info('interrupt active ticket')
            #     ticket_orders = TicketsOrder.query.filter(
            #         TicketsOrder.isdelete == false(),
            #         TicketsOrder.TIid == ticket.TIid,
            #         TicketsOrder.TSOstatus == TicketsOrderStatus.pending.value,
            #         TicketsOrder.TSOtype != TicketPayType.cash.value).all()
            #     row_count = self._deposit_refund(ticket_orders, ticket)  # 活动临时中断，除购买外全退钱
            #     current_app.logger.info('共退款{}条记录'.format(row_count))
            # ticket.update({'TIstatus': TicketStatus.interrupt.value})
            # self._cancle_celery_task('start_ticket{}'.format(ticket.TIid))
            # self._cancle_celery_task('end_ticket{}'.format(ticket.TIid))
            else:
                if product.PRstatus < ProductStatus.interrupt.value:
                    raise ParamsError('仅可编辑已中止发放或已结束的商品')
                product_dict = self._validate_ticket_param(data)
                product_dict.update({'PRname': data.get('prname'),
                                     'PRimg': data.get('primg'),
                                     'PRdetails': data.get('prdetails'),
                                     'PRstatus': ProductStatus.ready.value if product_dict.get(
                                         'PRtimeLimeted') else ProductStatus.active.value
                                     })
            # todo

            #     if ticket.TIstatus == TicketStatus.interrupt.value:  # 中止的情况
            #         current_app.logger.info('edit interrupt ticket')
            #         ticket.update(ticket_dict)
            #         TicketLinkage.query.filter(TicketLinkage.isdelete == false(),
            #                                    TicketLinkage.TIid == ticket.TIid).delete_()  # 删除原来的关联
            #     else:  # 已结束的情况，重新发起
            #         current_app.logger.info('edit ended ticket')
            #         ticket_dict.update({'TIid': str(uuid.uuid1()),
            #                             'ADid': getattr(request, 'user').id})
            #         ticket = Ticket.create(ticket_dict)
            #     self._cancle_celery_task('start_ticket{}'.format(ticket.TIid))
            #     self._cancle_celery_task('end_ticket{}'.format(ticket.TIid))
            #     self._create_celery_task(ticket.TIid, ticket_dict.get('TIstartTime'))
            #     self._create_celery_task(ticket.TIid, ticket_dict.get('TIendTime'), start=False)
            # instance_list.append(ticket)
            # db.session.add_all(instance_list)
            # self.BaseAdmin.create_action(AdminActionS.update.value, 'Ticket', ticket.TIid)
        return Success('编辑成功', data={'prid': product.PRid})

    def _validate_ticket_param(self, data):
        valid_dict = {'prname': '商品名称', 'primg': '封面图', 'prlineprice': '原价', 'prtrueprice': '现价',
                      'suid': '供应商',
                      'prnum': '数量', 'prdetails': '详情', 'prbanner': '轮播图', 'address': '定位地点'
                      }
        prtimelimeted = int(data.get('prtimelimeted'), 0)
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
            if prusestarttime < pruseendtime:
                raise ParamsError('使用开始时间不能小于发放结束时间')
            if pruseendtime <= prusestarttime:
                raise ParamsError('使用结束时间应大于开始时间')

        prlineprice, prtrueprice = map(lambda x: validate_price(x, can_zero=False),
                                       (data.get('prlineprice'), data.get('prtrueprice')))
        latitude, longitude = self.check_lat_and_long(data.get('latitude'), data.get('longitude'))
        prnum = data.get('prnum')
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
                        'PRlinePrice': prlineprice,
                        'PRtruePrice': prtrueprice,
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
            prid, secret_usid = str(param).split('&')
        except ValueError:
            raise ParamsError('试用码无效')

        # todo

        return Success('门票验证成功', data='sdafsdagq2903217u45r8qfasdklh')
