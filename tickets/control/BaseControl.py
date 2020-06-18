import json
import os
import uuid
from datetime import datetime
from flask import current_app, request

from tickets.extensions.base_jsonencoder import JSONEncoder
from tickets.config.enums import ApplyStatus, ApplyFrom, ApprovalAction
from tickets.extensions.error_response import StatusError, ParamsError
from tickets.extensions.register_ext import mp_miniprogram, db
from tickets.extensions.weixin.mp import WeixinMPError
from tickets.models import AdminActions, Supplizer, Admin, User, CashNotes, UserWallet
from tickets.models.approval import Approval, ApprovalNotes, PermissionType


class BaseController:
    @staticmethod
    def img_check(filepath, msg='图片'):
        """
        图片校验
        :param msg: msg
        :param filepath: 完整的绝对路径
        :return:
        """
        try:
            filesize = os.path.getsize(filepath)
        except FileNotFoundError:
            current_app.logger.error('FileNotFoundError: {}'.format(filepath))
            raise StatusError('服务器繁忙， 请稍后再试')
        current_app.logger.info('size {} MB'.format(round(filesize / 1048576, 2)))
        if filesize > 1024 * 1024:
            current_app.logger.info('content size out of limit, path :{}'.format(filepath))
            # 图片太大
            from PIL import Image
            img = Image.open(filepath)
            x, y = img.size
            x_ = 750
            y_ = int(y * (x / x_))
            if y_ > 1000:
                y_ = 1000
            time_now = datetime.now()
            year = str(time_now.year)
            month = str(time_now.month)
            day = str(time_now.day)
            tmp_path = os.path.join(
                current_app.config['BASEDIR'], 'img', 'temp', year, month, day)
            if not os.path.isdir(tmp_path):
                os.makedirs(tmp_path)
            tmp_path = os.path.join(tmp_path, os.path.basename(filepath))
            img.resize((x_, y_), Image.LANCZOS).save(tmp_path)
            filepath = tmp_path
            current_app.logger.info('compressed size {} MB, path :{}'.format(
                round(os.path.getsize(filepath) / 1048576, 2), filepath))
        try:
            check_result = mp_miniprogram.img_sec_check(filepath)
            current_app.logger.info(check_result)
        except WeixinMPError as e:
            current_app.logger.info('error is {}'.format(e))
            current_app.logger.error('傻逼在发黄色图片  usid = {}'.format(getattr(request, 'user').id))
            raise ParamsError('{}可能存在违法违规等不良信息，请检查后重试'.format(msg))


class BaseAdmin:
    @staticmethod
    def create_action(AAaction, AAmodel, AAkey):
        detail = request.detail
        detail['data'] = detail['data'].decode()

        admin_action = {
            'AAid': str(uuid.uuid1()),
            'ADid': request.user.id,
            'AAaction': AAaction,
            'AAmodel': AAmodel,
            'AAdetail': json.dumps(detail),
            'AAkey': AAkey
        }
        aa_instance = AdminActions.create(admin_action)
        db.session.add(aa_instance)


class BaseApproval:

    def create_approval(self, avtype, startid, avcontentid, applyfrom=None, **kwargs):

        current_app.logger.info('start create approval ptid = {0}'.format(avtype))
        pt = PermissionType.query.filter_by_(PTid=avtype).first_('参数异常')

        start, content = self.__get_approvalcontent(pt, startid, avcontentid, applyfrom=applyfrom, **kwargs)
        db.session.expunge_all()
        av = Approval.create({
            "AVid": str(uuid.uuid1()),
            "AVname": avtype + datetime.now().strftime('%Y%m%d%H%M%S'),
            "PTid": avtype,
            "AVstartid": startid,
            "AVlevel": 1,
            "AVstatus": ApplyStatus.wait_check.value,
            "AVcontent": avcontentid,
            'AVstartdetail': json.dumps(start, cls=JSONEncoder),
            'AVcontentdetail': json.dumps(content, cls=JSONEncoder),
        })

        with db.auto_commit():

            if applyfrom == ApplyFrom.supplizer.value:
                sup = Supplizer.query.filter_by_(SUid=startid).first()
                name = getattr(sup, 'SUname', '')
            elif applyfrom == ApplyFrom.platform.value:
                admin = Admin.query.filter_by_(ADid=startid).first()
                name = getattr(admin, 'ADname', '')
            else:
                user = User.query.filter_by_(USid=startid).first()
                name = getattr(user, 'USname', '')

            aninstance = ApprovalNotes.create({
                "ANid": str(uuid.uuid1()),
                "AVid": av.AVid,
                "ADid": startid,
                "ANaction": ApprovalAction.submit.value,
                "AVadname": name,
                "ANabo": "发起申请",
                "ANfrom": applyfrom
            })
            db.session.add(av)
            db.session.add(aninstance)
        return av.AVid

    def __get_approvalcontent(self, pt, startid, avcontentid, **kwargs):
        start, content = self.__fill_approval(pt, startid, avcontentid, **kwargs)
        current_app.logger.info('get start {0} content {1}'.format(start, content))
        if not (start or content):
            raise ParamsError('审批流创建失败，发起人或需审批内容已被删除')
        return start, content

    def __fill_approval(self, pt, start, content, **kwargs):
        if pt.PTid == 'tocash':
            return self.__fill_cash(start, content, **kwargs)
        else:
            raise ParamsError('参数异常， 请检查审批类型是否被删除。如果新增了审批类型，请联系开发实现后续逻辑')

    def __fill_cash(self, startid, contentid, **kwargs):
        # 填充提现内容
        apply_from = kwargs.get('applyfrom', ApplyFrom.user.value)
        if apply_from == ApplyFrom.user.value:
            start_model = User.query.filter_by_(USid=startid).first()
        elif apply_from == ApplyFrom.supplizer.value:
            start_model = Supplizer.query.filter_by_(SUid=startid).first()
        elif apply_from == ApplyFrom.platform.value:
            start_model = Admin.query.filter(Admin.isdelete == False,
                                             Admin.ADid == startid).first()
        else:
            start_model = None
        content = CashNotes.query.filter_by_(CNid=contentid).first()
        uw = UserWallet.query.filter_by_(USid=startid,
                                         CommisionFor=apply_from).first()
        if not start_model or not content or not uw:
            start_model = None

        content.fill('uWbalance', uw.UWbalance)
        for key in kwargs:
            content.fill(key, kwargs.get(key))

        return start_model, content
