import uuid
from datetime import datetime

from flask import request, current_app
from sqlalchemy import false

from tickets.extensions.error_response import ParamsError, AuthorityError
from tickets.extensions.params_validates import parameter_required
from tickets.extensions.success_response import Success
from tickets.extensions.interface.user_interface import admin_required, token_required, is_user, is_admin
from tickets.config.enums import ActivationTypeEnum, OrderStatus
from tickets.extensions.register_ext import db
from tickets.models import ActivationType, Activation, ProductOrderActivation, Admin, OrderMain, Product


class CActivation():
    @admin_required
    def update_activationtype(self):
        data = parameter_required('attid')
        attid = data.pop('attid')
        with db.auto_commit():
            att = ActivationType.query.filter_by(ATTid=attid, isdelete=False).first_('活跃度获取方式未被记录')
            admin = Admin.query.filter(
                Admin.ADid == getattr(request, 'user').id, Admin.isdelete == false()).first_('用户信息有误')
            update_dict = {
                'ADid': admin.ADid
            }
            for key in att.keys():
                lower_key = str(key).lower()
                value = data.get(lower_key)
                if value or value == 0:
                    if key != 'ATTname' and not str(value).isdigit():
                        raise ParamsError('{} 只能是自然数'.format(getattr(ActivationType, key).comment))
                    update_dict.setdefault(key, value)
            att.update(update_dict)
            db.session.add(att)
        return Success('修改成功', data=attid)

    def get_activationtype(self):
        data = parameter_required('attid')
        att = ActivationType.query.filter_by(ATTid=data.get('attid'), isdelete=False).first_('活跃度获取方式未被记录')
        return Success(data=att)

    def list_activationtype(self):
        data = parameter_required()
        filter_args = {
            ActivationType.isdelete == false()
        }
        # if data.get('atttype'):
        #     filter_args.add(ActivationType.ATTtype == data.get('atttype'))
        att_list = ActivationType.query.filter(*filter_args).order_by(ActivationType.updatetime.desc()).all_with_page()
        return Success(data=att_list)

    @token_required
    def get_duration_activation(self):
        data = parameter_required('tistarttime', 'tiendtime')
        if is_admin():
            usid = data.get('usid')
        elif is_user():
            usid = getattr(request, 'user').id
        else:
            raise AuthorityError('请登录')
        start = self._trans_time(data.get('tistarttime'))
        end = self._trans_time(data.get('tiendtime'))

        at_list = Activation.query.filter(
            Activation.USid == usid, Activation.createtime >= start, Activation.createtime <= end).all_with_page()
        for at in at_list:
            self._fill_at(at)
        return Success(data=at_list)

    def _trans_time(self, time):
        if isinstance(time, datetime):
            return time
        try:
            time = datetime.strptime(str(time), '%Y-%m-%d %H:%M:%S')
            return time
        except Exception as e:
            current_app.logger.info('时间格式不正确 time str {} error {}'.format(time, e))
            raise ParamsError('时间格式不正确')

    def _fill_at(self, at):
        att = ActivationType.query.filter_by(ATTid=at.ATTid, isdelet=False).first()
        if not att:
            return
        at.fill('attname', att.ATTname)

    @staticmethod
    def add_activation(attid, usid, contentid, atnum=0, no_loop=False):
        att = ActivationType.query.filter_by(ATTid=attid).first()
        if not att:
            return
        if str(attid) != ActivationTypeEnum.reward.value:
            atnum = att.ATTnum

        atnum = int(atnum)
        at = Activation.create({
            'ATid': str(uuid.uuid1()),
            'USid': usid,
            'ATTid': attid,
            'ATnum': atnum
        })

        now = datetime.now()
        # 活跃分只给限时商品订单统计
        tso_list = OrderMain.query.join(Product, Product.PRid == OrderMain.PRid).filter(
            OrderMain.OMstatus == OrderStatus.pending.value,
            Product.PRissueStartTime <= now,
            Product.PRissueEndTime >= now,
            Product.PRtimeLimeted == 1,
            Product.isdelete == false(),
            OrderMain.USid == usid,
            Product.isdelete == false(),
            OrderMain.isdelete == false()).all()
        if not tso_list:
            current_app.logger.info('活动已结束预热，活跃分不获取')
            return

        db.session.add(at)

        for tso in tso_list:
            current_app.logger.info('tso status {}'.format(tso.OMstatus))
            if not no_loop:
                tso.OMintegralpayed += atnum
            db.session.add(ProductOrderActivation.create({
                'POAid': str(uuid.uuid1()),
                'OMid': tso.OMid,
                'ATid': at.ATid,
                'POAcontent': contentid
            }))
    #
    # @admin_required
    # def list_product_activation(self):
    #     data = parameter_required('prid')
    #     prid = data.get('prid')
    #     at_list = Activation.query.filter(
    #         Activation.USid == usid, Activation.createtime >= start, Activation.createtime <= end).all_with_page()
    #     for at in at_list:
    #         self._fill_at(at)
    #     return Success(data=at_list)