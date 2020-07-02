import json
import uuid
from decimal import Decimal

from flask import current_app, request

from tickets.config.enums import ApplyStatus, ApprovalAction, AdminActionS, ApplyFrom, WXLoginFrom, CashFor, \
    ProductStatus
from tickets.control.BaseControl import BaseApproval, BaseAdmin
from tickets.extensions.error_response import NotFound, AuthorityError, ParamsError, SystemError
from tickets.extensions.interface.user_interface import token_required, is_admin, is_supplizer
from tickets.extensions.params_validates import parameter_required, validate_price
from tickets.extensions.register_ext import db
from tickets.extensions.success_response import Success
from tickets.extensions.tasks import add_async_task, start_product, end_product
from tickets.models import Admin, Approval, Permission, AdminPermission, Supplizer, PermissionType, ApprovalNotes, \
    CashNotes, UserWallet, CashFlow, Product


class CApproval(BaseApproval):

    @token_required
    def get_dealing_approval(self):
        """管理员查看自己名下可以处理的审批流 概览"""
        if is_admin():
            admin = Admin.query.filter_by_(ADid=request.user.id).first_('管理员账号已被回收')
            if not admin:
                current_app.logger.info('get admin failed id is {0}'.format(admin.ADid))
                raise NotFound("该管理员已被删除")
            # pttype = request.args.to_dict().get('pttypo')
            pt_list = PermissionType.query.filter(
                PermissionType.PTid == Permission.PTid, Permission.PIid == AdminPermission.PIid,
                AdminPermission.ADid == admin.ADid, PermissionType.isdelete == False,
                AdminPermission.isdelete == False, Permission.isdelete == False
            ).order_by(PermissionType.createtime.desc()).all()
            # pi_list = AdminPermission.query.filter_by_(ADid=admin.ADid).all()
            for pt in pt_list:
                ap_num = Approval.query.filter(
                    Approval.PTid == pt.PTid, Approval.AVlevel == Permission.PELevel, Permission.PTid == pt.PTid,
                    Permission.PIid == AdminPermission.PIid, AdminPermission.ADid == admin.ADid,
                    Approval.AVstatus == ApplyStatus.wait_check.value,
                    Approval.isdelete == False, Permission.isdelete == False, AdminPermission.isdelete == False
                ).count()
                pt.fill('approval_num', ap_num)
        elif is_supplizer():
            sup = Supplizer.query.filter_by_(SUid=request.user.id).first_('供应商账号已回收')
            pt_list = PermissionType.query.filter(
                PermissionType.PTid == Approval.PTid, Approval.AVstartid == sup.SUid,
                Approval.AVstatus == ApplyStatus.wait_check.value,
                PermissionType.isdelete == False, Approval.isdelete == False
            ).all()
            if not pt_list:
                pt_list = PermissionType.query.filter_by_(PTid='tointegral').all()
            # todo 供应商的审批类型筛选
            for pt in pt_list:
                ap_num = Approval.query.filter(
                    Approval.AVstartid == sup.SUid,
                    Approval.PTid == pt.PTid,
                    Approval.isdelete == False
                ).count()

                pt.fill('approval_num', ap_num)
        else:
            pt_list = []

        return Success('获取审批流类型成功', data=pt_list)

    @token_required
    def get_approval_list(self):
        data = parameter_required(('ptid',))
        filter_starttime, filter_endtime = data.get('starttime', '2018-12-01'), data.get('endtime', '2100-01-01')
        avstatus = data.get('avstatus', "")
        current_app.logger.info('get avstatus {0} '.format(avstatus))
        if avstatus and avstatus != 'all':
            avstatus = getattr(ApplyStatus, data.get('avstatus'), None)
        else:
            avstatus = None

        if is_admin():
            admin = Admin.query.filter_by_(ADid=request.user.id).first_()
            if not admin:
                current_app.logger.info('get admin failed id is {0}'.format(request.user.id))
                raise NotFound("该管理员已被删除")

            pt = PermissionType.query.filter_by_(PTid=data.get('ptid')).first()
            # ptytype = ActivityType(int(data.get('pttype'))).name
            ap_querry = Approval.query.filter(
                Approval.PTid == pt.PTid, Approval.AVlevel == Permission.PELevel, Permission.PTid == Approval.PTid,
                Permission.PIid == AdminPermission.PIid, AdminPermission.ADid == admin.ADid,
                Approval.isdelete == False, Permission.isdelete == False, AdminPermission.isdelete == False,
            )
            if avstatus is not None:
                current_app.logger.info('sql avstatus = {0}'.format(avstatus.value))
                ap_querry = ap_querry.filter(Approval.AVstatus == avstatus.value)

            ap_list = ap_querry.order_by(Approval.AVstatus.desc(), Approval.createtime.desc()).all_with_page()
        else:
            try:
                status = getattr(ApplyStatus, data.get('avstatus', 'wait_check'), 'wait_check').value
            except Exception as e:
                current_app.logger.error("sup approval list status error :{}".format(e))
                status = None
            pt = PermissionType.query.filter_by_(PTid=data.get('ptid')).first_('审批类型不存在')
            sup = Supplizer.query.filter_by_(SUid=request.user.id).first_('供应商不存在')

            ap_list = Approval.query.filter_by_(AVstartid=sup.SUid).all_with_page()
        res = []
        for ap in ap_list:
            if not ap.AVstartdetail:
                continue
            ap.hide('AVcontentdetail', 'AVstartdetail')
            content = ap.AVcontentdetail or 'null'
            content = json.loads(content)
            start = ap.AVstartdetail or 'null'

            ap.fill('content', content)
            ap.fill('start', json.loads(start))
            ap.add('createtime')
            ap.fill('avstatus_en', ApplyStatus(ap.AVstatus).name)
            ap.fill('avstatus_zh', ApplyStatus(ap.AVstatus).zh_value)
            res.append(ap)

        return Success('获取待审批列表成功', data=res)

    @token_required
    def get_approvalnotes(self):
        """查看审批的所有流程"""
        if not (is_admin() or is_supplizer()):
            raise AuthorityError('权限不足')
        data = parameter_required(('avid',))
        an_list = ApprovalNotes.query.filter_by_(AVid=data.get('avid')).order_by(ApprovalNotes.createtime).all()
        for an in an_list:
            an.fill('anaction', ApprovalAction(an.ANaction).zh_value)
        return Success('获取审批记录成功', data=an_list)

    @token_required
    def deal_approval(self):
        """管理员处理审批流"""
        if is_admin():
            admin = Admin.query.filter_by_(ADid=request.user.id).first_("该管理员已被删除")
            sup = None
        elif is_supplizer():
            sup = Supplizer.query.filter_by_(SUid=request.user.id).first_("账号状态错误，请重新登录")
            admin = None
        else:
            raise AuthorityError('权限不足')

        receive_data = request.json
        with db.auto_commit():
            if isinstance(receive_data, list):
                for data in receive_data:
                    self.deal_single_approval(data, admin, sup)
            else:
                self.deal_single_approval(receive_data, admin, sup)

        return Success("审批操作完成")

    def deal_single_approval(self, data, admin=None, sup=None):
        parameter_required(('avid', 'anaction', 'anabo'), datafrom=data)
        approval_model = Approval.query.filter_by_(AVid=data.get('avid'),
                                                   AVstatus=ApplyStatus.wait_check.value).first_('审批已处理')
        if is_admin():
            Permission.query.filter(
                Permission.isdelete == False, AdminPermission.isdelete == False,
                Permission.PIid == AdminPermission.PIid,
                AdminPermission.ADid == request.user.id,
                Permission.PTid == approval_model.PTid,
                Permission.PELevel == approval_model.AVlevel
            ).first_('权限不足')
            avadname = admin.ADname
            adid = admin.ADid
        else:
            avadname = sup.SUname
            adid = sup.SUid
        # 审批流水记录
        approvalnote_dict = {
            "ANid": str(uuid.uuid1()),
            "AVid": data.get("avid"),
            "AVadname": avadname,
            "ADid": adid,
            "ANaction": data.get('anaction'),
            "ANabo": data.get("anabo")
        }
        apn_instance = ApprovalNotes.create(approvalnote_dict)
        db.session.add(apn_instance)
        if is_admin():
            BaseAdmin().create_action(AdminActionS.insert.value, 'ApprovalNotes', str(uuid.uuid1()))

        if int(data.get("anaction")) == ApprovalAction.agree.value:
            # 审批操作是否为同意
            pm_model = Permission.query.filter(
                Permission.isdelete == False,
                Permission.PTid == approval_model.PTid,
                Permission.PELevel == int(approval_model.AVlevel) + 1
            ).first()
            if pm_model:
                # 如果还有下一级审批人
                approval_model.AVlevel = str(int(approval_model.AVlevel) + 1)
            else:
                # 没有下一级审批人了
                approval_model.AVstatus = ApplyStatus.agree.value
                self.agree_action(approval_model, data)
        else:
            # 审批操作为拒绝
            approval_model.AVstatus = ApplyStatus.reject.value
            self.refuse_action(approval_model, data.get('anabo'))

    def agree_action(self, approval_model, data):
        if not approval_model:
            return
        if approval_model.PTid == 'tocash':
            self.agree_cash(approval_model)
        elif approval_model.PTid == 'toshelves':
            self.agree_shelves(approval_model, data)

        else:
            return ParamsError('参数异常，请检查审批类型是否被删除。如果新增了审批类型，请联系开发实现后续逻辑')

    def refuse_action(self, approval_model, refuse_abo):
        if not approval_model:
            return
        if approval_model.PTid == 'tocash':
            self.refuse_cash(approval_model, refuse_abo)
        elif approval_model.PTid == 'toshelves':
            self.refuse_shelves(approval_model, refuse_abo)
        else:
            return ParamsError('参数异常，请检查审批类型是否被删除。如果新增了审批类型，请联系开发实现后续逻辑')

    def agree_cash(self, approval_model):
        if not approval_model:
            return
        from tickets.control.COrder import COrder
        corder = COrder()
        cn = CashNotes.query.filter_by_(CNid=approval_model.AVcontent).first()
        uw = UserWallet.query.filter_by_(USid=approval_model.AVstartid).first()
        if not cn or not uw:
            raise SystemError('提现数据异常,请处理')
        flow_dict = dict(CFWid=str(uuid.uuid1()), CNid=cn.CNid)
        if cn.CommisionFor == ApplyFrom.user.value:
            res = corder.pay_to_user(cn)  # 小程序提现
            flow_dict['amout'] = int(Decimal(cn.CNcashNum).quantize(Decimal('0.00')) * 100)
            flow_dict['CFWfrom'] = CashFor.wechat.value
        else:
            res = corder._pay_to_bankcard(cn)
            flow_dict['amout'] = res.amount
            flow_dict['cmms_amt'] = res.cmms_amt
            flow_dict['CFWfrom'] = CashFor.bankcard.value
        flow_dict['partner_trade_no'] = res.partner_trade_no
        response = json.dumps(res)
        flow_dict['response'] = response
        db.session.add(CashFlow.create(flow_dict))

        cn.CNstatus = ApprovalAction.agree.value
        uw.UWbalance = Decimal(str(uw.UWbalance)) - Decimal(str(cn.CNcashNum))

    def refuse_cash(self, approval_model, refuse_abo):
        if not approval_model:
            return
        cn = CashNotes.query.filter_by_(CNid=approval_model.AVcontent).first()
        if not cn:
            # raise SystemError('提现数据异常,请处理')
            return
        cn.CNstatus = ApprovalAction.refuse.value
        cn.CNrejectReason = refuse_abo
        uw = UserWallet.query.filter_by_(USid=cn.USid).first_("提现审批异常数据")
        # 拒绝提现时，回退申请的钱到可提现余额里
        uw.UWcash = Decimal(str(uw.UWcash)) + Decimal(str(cn.CNcashNum))

    def agree_shelves(self, approval_model, data):
        parameter_required({'prlineprice': '划线价格', 'prtrueprice': '实际价格'}, datafrom=data)
        product = Product.query.filter_by_(
            PRid=approval_model.AVcontent,
            PRstatus=ProductStatus.pending.value
        ).first_('商品已处理')
        prlineprice = validate_price(data.get('prlineprice'), can_zero=False)
        prtrueprice = validate_price(data.get('prtrueprice'), can_zero=True if product.PRtimeLimeted else False)
        current_app.logger.info(f'划线价, 实际价 = {prlineprice}, {prtrueprice}')
        from datetime import datetime
        now = datetime.now()
        if product.PRtimeLimeted:
            if product.PRissueStartTime > now:  # 同意时未到发放开始时间
                product.PRstatus = ProductStatus.ready.value  # 状态为 未开始
                add_async_task(func=start_product, start_time=product.PRissueStartTime, func_args=(product.PRid,),
                               conn_id='start_product{}'.format(product.PRid))
                add_async_task(func=end_product, start_time=product.PRissueEndTime, func_args=(product.PRid,),
                               conn_id='end_product{}'.format(product.PRid))
            elif product.PRissueStartTime <= now < product.PRissueEndTime:  # 已到开始发放时间 未到 结束时间
                product.PRstatus = ProductStatus.active.value  # 状态为 活动中
                add_async_task(func=end_product, start_time=product.PRissueEndTime, func_args=(product.PRid,),
                               conn_id='end_product{}'.format(product.PRid))
            else:
                raise ParamsError('当前时间已超出商品发放时间范围，请联系供应商重新提交申请')

        else:
            product.PRstatus = ProductStatus.active.value
        product.PRlinePrice = prlineprice
        product.PRtruePrice = prtrueprice

    def refuse_shelves(self, approval_model, refuse_abo):
        product = Product.query.filter_by_(PRid=approval_model.AVcontent).first()
        if not product:
            return
        product.PRstatus = ProductStatus.reject.value
