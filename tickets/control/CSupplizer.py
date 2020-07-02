import datetime
import re
import uuid
from collections import namedtuple
from flask import current_app, request
from sqlalchemy import false
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

# from planet.common.Inforsend import SendSMS
from wtforms import StringField, DecimalField, FieldList, DateField, IntegerField
from wtforms.validators import DataRequired, Regexp

from tickets.config.enums import ApplyFrom, UserStatus, SupplizerGrade, AdminActionS, WexinBankCode
from tickets.control.BaseControl import BaseAdmin
from tickets.extensions.base_form import BaseForm
from tickets.extensions.error_response import AuthorityError, ParamsError, DumpliError, StatusError
from tickets.extensions.interface.user_interface import admin_required, is_admin, token_required, is_supplizer, \
    is_anonymous
from tickets.extensions.params_validates import parameter_required
from tickets.extensions.register_ext import db
from tickets.extensions.success_response import Success
from tickets.models import Supplizer, UserWallet, Admin, ProductVerifier, User, SupplizerAccount
from tickets.control.CUser import CUser


class CSupplizer:
    def __init__(self):
        self.base_admin = BaseAdmin()
        self.cuser = CUser()

    @token_required
    def list(self):
        """供应商列表"""
        form = SupplizerListForm().valid_data()
        kw = form.kw.data
        mobile = form.mobile.data
        sustatus = form.sustatus.data
        option = form.option.data
        sugrade = form.sugrade.data
        # if sugrade is not None or sugrade:
        #     sugrade = int(sugrade)
        if str(sugrade).isdigit():
            sugrade = int(sugrade)
        else:
            sugrade = None

        if option == 'ticket':
            return self._list_ticket_sup()
        filter_args = {
            Supplizer.isdelete == false(),
        }
        if sugrade:
            filter_args.add(Supplizer.SUgrade == sugrade)
        if sustatus or sustatus == 0:
            filter_args.add(Supplizer.SUstatus == sustatus)
        if kw:
            filter_args.add(Supplizer.SUname.contains(kw))
        if mobile:
            filter_args.add(Supplizer.SUlinkPhone.contains(mobile))
        if is_supplizer():
            filter_args.add(Supplizer.SUid == getattr(request, 'user').id)
        supplizers = Supplizer.query.filter(*filter_args).order_by(Supplizer.createtime.desc()).all_with_page()

        for supplizer in supplizers:
            supplizer.hide('SUpassword')
            if is_admin():
                # pbs = ProductBrand.query.filter(
                #     ProductBrand.isdelete == False,
                #     ProductBrand.SUid == supplizer.SUid
                # ).all()
                # for pb in pbs:
                #     if pb:
                #         pb.pbstatus_zh = ProductBrandStatus(pb.PBstatus).zh_value
                #         pb.add('pbstatus_zh')
                pb = namedtuple('ProductBrand', ['PBid', 'PBlogo', 'PBname', 'PBdesc', 'PBlinks',
                                                 'PBbackgroud', 'PBstatus', 'SUid', 'PBintegralPayRate',
                                                 'PBslogan', 'PBthemeColor', 'PBpublicity', 'PBsort'])
                # pbs = [pb('', '', '', '', '', '', 0, '', 0, '', '', '', 1)]
                pbs = []
                supplizer.fill('pbs', pbs)
            # 收益
            favor = UserWallet.query.filter(
                UserWallet.isdelete == False,
                UserWallet.USid == supplizer.SUid,
                UserWallet.CommisionFor == ApplyFrom.supplizer.value
            ).first()
            supplizer.fill('uwbalance', getattr(favor, 'UWbalance', 0))
            supplizer.fill('uwtotal', getattr(favor, 'UWtotal', 0))
            supplizer.fill('uwcash', getattr(favor, 'UWcash', 0))
            supplizer.fill('uwexpect', getattr(favor, 'UWexpect', 0))
            supplizer.fill('subaserate', 0)
            supplizer.fill('sustatus_zh', UserStatus(supplizer.SUstatus).zh_value)
            supplizer.fill('sustatus_en', UserStatus(supplizer.SUstatus).name)
        return Success(data=supplizers)

    @staticmethod
    def _list_ticket_sup():
        sups = Supplizer.query.filter(Supplizer.isdelete == false(), Supplizer.SUstatus == UserStatus.usual.value,
                                      Supplizer.SUgrade == SupplizerGrade.ticket.value)
        if is_supplizer():
            sups = sups.filter(Supplizer.SUid == getattr(request, 'user').id)
        sups = sups.all_with_page()

        for sup in sups:
            sup.fields = ['SUid', 'SUname', 'SUgrade', 'SUstatus']
            sup.fill('sustatus_zh', UserStatus(sup.SUstatus).zh_value)
            sup.fill('sugrade_zh', SupplizerGrade(sup.SUgrade).zh_value)
        return Success(data=sups)

    def create(self):
        """添加"""
        if is_admin():
            Admin.query.filter_by_(ADid=request.user.id).first_('账号状态异常')
            current_app.logger.info(">>>  Admin Create a Supplizer  <<<")
        elif is_anonymous():
            current_app.logger.info(">>>  Tourist Uploading Supplizer Files  <<<")
        else:
            raise AuthorityError('无权限')
        form = SupplizerCreateForm().valid_data()
        if isinstance(form.sugrade.data, int) and form.sugrade.data == 0:
            raise AuthorityError('暂时只支持添加虚拟商品供应商')
        suid = str(uuid.uuid1())
        if is_admin():
            sustatus = UserStatus.usual.value
            sudeposit = form.sudeposit.data
        else:
            sustatus = UserStatus.auditing.value
            sudeposit = 0
        supassword = generate_password_hash(form.supassword.data) if form.supassword.data else None
        try:
            with db.auto_commit():
                supperlizer = Supplizer.create({
                    'SUid': suid,
                    'SUlinkPhone': form.sulinkphone.data,
                    'SUloginPhone': form.suloginphone.data,
                    'SUname': form.suname.data,
                    'SUlinkman': form.sulinkman.data,
                    # 'SUbaseRate': form.subaserate.data,
                    'SUaddress': form.suaddress.data,
                    'SUdeposit': sudeposit,
                    'SUstatus': sustatus,  # 管理员添加的可直接上线
                    'SUbanksn': form.subanksn.data,
                    'SUbankname': form.subankname.data,
                    'SUpassword': supassword,
                    'SUheader': form.suheader.data,
                    'SUcontract': form.sucontract.data,
                    'SUbusinessLicense': form.subusinesslicense.data,
                    'SUregisteredFund': form.suregisteredfund.data,
                    'SUmainCategory': form.sumaincategory.data,
                    'SUregisteredTime': form.suregisteredtime.data,
                    'SUlegalPerson': form.sulegalperson.data,
                    'SUemail': form.suemail.data,
                    'SUlegalPersonIDcardFront': form.sulegalpersonidcardfront.data,
                    'SUlegalPersonIDcardBack': form.sulegalpersonidcardback.data,
                    'SUgrade': form.sugrade.data or 0,
                })
                db.session.add(supperlizer)
                if is_admin():
                    self.base_admin.create_action(AdminActionS.insert.value, 'Supplizer', suid)
                # if pbiminActionS.insert.value, 'SupplizerDepositLog', str(uuid.uuid1()))
        except IntegrityError:
            raise ParamsError('手机号重复')
        return Success('创建成功', data={'suid': supperlizer.SUid})

    @token_required
    def update(self):
        """更新供应商信息"""
        if not is_admin() and not is_supplizer():
            raise AuthorityError()
        form = SupplizerUpdateForm().valid_data()
        pbids = form.pbids.data
        with db.auto_commit():
            supplizer = Supplizer.query.filter(Supplizer.isdelete == False, Supplizer.SUid == form.suid.data
                                               ).first_('供应商不存在')
            supplizer_dict = {
                'SUlinkPhone': form.sulinkphone.data,
                'SUname': form.suname.data,
                'SUlinkman': form.sulinkman.data,
                'SUaddress': form.suaddress.data,
                'SUbanksn': form.subanksn.data,
                'SUbankname': form.subankname.data,
                # 'SUpassword': generate_password_hash(form.supassword.data),  # 暂时去掉
                'SUheader': form.suheader.data,
                'SUcontract': form.sucontract.data,
                'SUbusinessLicense': form.subusinesslicense.data,
                'SUregisteredFund': form.suregisteredfund.data,
                'SUmainCategory': form.sumaincategory.data,
                # 'SUregisteredTime': form.suregisteredtime.data,
                'SUlegalPerson': form.sulegalperson.data,
                'SUemail': form.suemail.data,
                'SUlegalPersonIDcardFront': form.sulegalpersonidcardfront.data,
                'SUlegalPersonIDcardBack': form.sulegalpersonidcardback.data,
            }
            if is_admin():
                # if form.subaserate.data:
                #     supplizer_dict['SUbaseRate'] = form.subaserate.data,
                if isinstance(form.sustatus.data, int):
                    supplizer_dict['SUstatus'] = form.sustatus.data
                    if form.sustatus.data == UserStatus.usual.value and not supplizer.SUpassword:
                        supplizer_dict['SUpassword'] = generate_password_hash(supplizer.SUloginPhone)

            supplizer.update(supplizer_dict, null='dont ignore')
            db.session.add(supplizer)
            if is_admin():
                self.base_admin.create_action(AdminActionS.update.value, 'Supplizer', form.suid.data)
        return Success('更新成功')

    # @token_required
    def get(self):
        if not is_admin() and not is_supplizer():
            raise AuthorityError()
        form = SupplizerGetForm().valid_data()
        supplizer = form.supplizer
        self._fill_supplizer(supplizer)
        # pbs = ProductBrand.query.filter(
        #     ProductBrand.isdelete == False,
        #     ProductBrand.SUid == supplizer.SUid
        # ).all()
        # for pb in pbs:
        #     if pb:
        #         pb.pbstatus_zh = ProductBrandStatus(pb.PBstatus).zh_value
        #         pb.add('pbstatus_zh')
        supplizer.fill('pbs', [])
        supplizer.fill('SUbaseRate', 0)
        return Success(data=supplizer)

    def _fill_supplizer(self, supplizer):
        supplizer.hide('SUpassword')
        favor = UserWallet.query.filter(
            UserWallet.isdelete == False,
            UserWallet.USid == supplizer.SUid,
            UserWallet.CommisionFor == ApplyFrom.supplizer.value
        ).first()
        supplizer.fill('uwbalance', getattr(favor, 'UWbalance', 0))
        supplizer.fill('uwtotal', getattr(favor, 'UWtotal', 0))
        supplizer.fill('uwcash', getattr(favor, 'UWcash', 0))
        supplizer.fill('sustatus_zh', UserStatus(supplizer.SUstatus).zh_value)
        supplizer.fill('sustatus_en', UserStatus(supplizer.SUstatus).name)

    @admin_required
    def offshelves(self):
        current_app.logger.info('下架供应商')
        data = parameter_required(('suid',))
        suid = data.get('suid')
        with db.auto_commit():
            supplizer = Supplizer.query.filter(
                Supplizer.isdelete == False,
                Supplizer.SUid == suid
            ).first_('供应商不存在')
            supplizer.SUstatus = UserStatus.forbidden.value
            db.session.add(supplizer)
            self.base_admin.create_action(AdminActionS.update.value, 'Supplizer', suid)
        return Success('供应商下架成功')

    @admin_required
    def delete(self):
        """删除"""
        raise AuthorityError('暂不提供该功能')
        # data = parameter_required(('suid',))
        # suid = data.get('suid')
        # with db.auto_commit():
        #     supplizer = Supplizer.query.filter(
        #         Supplizer.isdelete == False,
        #         Supplizer.SUid == suid
        #     ).first_('供应商不存在')
        #     if self._check_lasting_order(suid=suid):
        #         raise StatusError('供应商部分订单正在进行')
        #
        #     supplizer.isdelete = True
        #     db.session.add(supplizer)
        #     self.base_admin.create_action(AdminActionS.delete.value, 'Supplizer', suid)
        #     current_app.logger.info('删除供应商{}'.format(supplizer.SUname))
        # return Success('删除成功')

    @token_required
    def change_password(self):
        if not is_supplizer() and not is_admin():
            raise AuthorityError()
        form = SupplizerChangePasswordForm().valid_data()
        old_password = form.oldpassword.data
        supassword = form.supassword.data
        suid = form.suid.data
        with db.auto_commit():
            supplizer = Supplizer.query.filter(
                Supplizer.isdelete == False,
                Supplizer.SUid == suid
            ).first_('不存在的供应商')
            if not is_admin() and not check_password_hash(supplizer.SUpassword, old_password):
                raise AuthorityError('原密码错误')
            supplizer.SUpassword = generate_password_hash(supassword)
            db.session.add(supplizer)
            if is_admin():
                self.base_admin.create_action(AdminActionS.update.value, 'Supplizer', suid)
        return Success('修改成功')

    @token_required
    def reset_password(self):
        form = SupplizerResetPasswordForm().valid_data()
        mobile = form.suloginphone.data
        password = form.supassword.data
        # if is_supplizer():
        #     code = form.code.data
        #     correct_code = conn.get(mobile + '_code')
        #     if correct_code:
        #         correct_code = correct_code.decode()
        #     current_app.logger.info('correct code is {}, code is {}'.format(correct_code, code))
        #     if code != correct_code:
        #         raise ParamsError('验证码错误')
        if not is_admin():
            raise AuthorityError()
        with db.auto_commit():
            supplizer = Supplizer.query.filter(
                Supplizer.isdelete == False,
                Supplizer.SUloginPhone == mobile
            ).first()
            supplizer.update({
                'SUpassword': generate_password_hash(password)
            })
            db.session.add(supplizer)
            self.base_admin.create_action(AdminActionS.update.value, 'Supplizer', supplizer.SUid)
        return Success('修改成功')

    @token_required
    def send_reset_password_code(self):
        """发送修改验证码"""
        raise AuthorityError('功能暂未开放')

    #     if not is_supplizer():
    #         raise AuthorityError()
    #     form = SupplizerSendCodeForm().valid_data()
    #     mobile = form.suloginphone.data
    #     Supplizer.query.filter(
    #         Supplizer.isdelete == False,
    #         Supplizer.SUloginPhone == mobile
    #     ).first_('不存在的供应商')
    #     exist_code = conn.get(mobile + '_code')
    #     if exist_code:
    #         return DumpliError('重复发送')
    #     nums = [str(x) for x in range(10)]
    #     code = ''.join([random.choice(nums) for _ in range(6)])
    #     key = mobile + '_code'
    #     conn.set(key, code, ex=60)  # 60s过期
    #     params = {"code": code}
    #     app = current_app._get_current_object()
    #     send_task = Thread(target=self._async_send_code, args=(mobile, params, app), name='send_code')
    #     send_task.start()
    #     return Success('发送成功')
    #
    # def _async_send_code(self, mobile, params, app):
    #     with app.app_context():
    #         response_send_message = SendSMS(mobile, params)
    #         if not response_send_message:
    #             current_app.logger.error('发送失败')

    @token_required
    def set_supplizeraccount(self):
        if not is_supplizer():
            raise AuthorityError
        data = request.json
        cardno = data.get('sacardno')
        cardno = re.sub(r'\s', '', str(cardno))
        self.cuser._CUser__check_card_num(cardno)
        check_res = self.cuser._verify_cardnum(cardno)  # 检验卡号
        if not check_res.data.get('validated'):
            raise ParamsError('请输入正确的银行卡号')
        checked_res = self.cuser._verify_cardnum(data.get('sabankaccount'))
        # if not checked_res.data.get('validated'):
        #     raise ParamsError('请输入正确的开票账户银行卡号')
        checked_name = self.cuser._verify_chinese(data.get('sacardname'))
        if not checked_name or len(checked_name[0]) < 2:
            raise ParamsError('请输入正确的开户人姓名')
        current_app.logger.info('用户输入银行名为:{}'.format(data.get('sabankname')))
        bankname = check_res.data.get('cnbankname')
        try:
            WexinBankCode(bankname)
        except Exception:
            raise ParamsError('系统暂不支持该银行提现，请更换银行后重新保存')
        data['sabankname'] = bankname
        current_app.logger.info('校验后更改银行名为:{}'.format(data.get('sabankname')))

        sa = SupplizerAccount.query.filter(
            SupplizerAccount.SUid == request.user.id, SupplizerAccount.isdelete == false()).first()
        if sa:
            for key in sa.__dict__:
                if str(key).lower() in data:
                    if re.match(r'^(said|suid)$', str(key).lower()):
                        continue
                    if str(key).lower() == 'sacardno':
                        setattr(sa, key, cardno)
                        continue
                    setattr(sa, key, data.get(str(key).lower()))
        else:
            sa_dict = {}
            for key in SupplizerAccount.__dict__:

                if str(key).lower() in data:
                    if not data.get(str(key).lower()):
                        continue
                    if str(key).lower() == 'suid':
                        continue
                    if str(key).lower() == 'sacardno':
                        sa_dict.setdefault(key, cardno)
                        continue
                    sa_dict.setdefault(key, data.get(str(key).lower()))
            sa_dict.setdefault('SAid', str(uuid.uuid1()))
            sa_dict.setdefault('SUid', request.user.id)
            sa = SupplizerAccount.create(sa_dict)
            db.session.add(sa)

        return Success('设置供应商账户信息成功')

    @token_required
    def get_supplizeraccount(self):
        sa = SupplizerAccount.query.filter(
            SupplizerAccount.SUid == request.user.id, SupplizerAccount.isdelete == false()).first()
        return Success('获取供应商账户信息成功', data=sa)

    @token_required
    def get_verifier(self):
        form = GetVerifier().valid_data()
        suid = form.suid.data
        if is_supplizer():
            suid = request.user.id
        if not suid:
            raise ParamsError('未指定供应商')
        tv_list = ProductVerifier.query.filter_by(SUid=suid, isdelete=False
                                                  ).order_by(ProductVerifier.createtime.desc()).all()

        phone_list = [tv.PVphone for tv in tv_list]
        return Success(data=phone_list)

    @token_required
    def set_verifier(self):
        form = SetVerifier().valid_data()
        if is_admin():
            suid = form.suid.data
            assert suid, '供应商未指定'
        elif is_supplizer():
            suid = request.user.id
        else:
            raise AuthorityError()
        sup = Supplizer.query.filter(Supplizer.isdelete == false(),
                                     Supplizer.SUstatus == UserStatus.usual.value,
                                     Supplizer.SUid == suid).first_('供应商状态异常')
        if sup.SUgrade != SupplizerGrade.ticket.value:
            raise StatusError('仅虚拟商品供应商可设置核销员')
        phone_list = form.phone_list.data
        tvid_list = []
        instence_list = []
        phone_list = {}.fromkeys(phone_list).keys()
        with db.auto_commit():
            for phone in phone_list:
                User.query.filter(User.isdelete == false(), User.UStelephone == phone).first_(f'没有手机号为 {phone} 用户 ')
                tv = ProductVerifier.query.filter_by(SUid=suid, PVphone=phone).first()
                if not tv:
                    tv = ProductVerifier.create({
                        'PVid': str(uuid.uuid1()),
                        'SUid': suid,
                        'PVphone': phone
                    })
                    instence_list.append(tv)
                tvid_list.append(tv.PVid)

            db.session.add_all(instence_list)
            # 删除无效的
            ProductVerifier.query.filter(
                ProductVerifier.isdelete == false(),
                ProductVerifier.SUid == suid,
                ProductVerifier.PVid.notin_(tvid_list)
            ).delete_(synchronize_session=False)
        return Success('修改成功', data=suid)


class SupplizerListForm(BaseForm):
    kw = StringField('关键词', default=None)
    mobile = StringField('手机号', default=None)
    sustatus = StringField('筛选状态', default='all')
    option = StringField('供应商类型')
    sugrade = StringField('供应商类型')

    def validate_sustatus(self, raw):
        from tickets.config.enums import UserStatus
        try:
            self.sustatus.data = getattr(UserStatus, raw.data).value
        except:
            raise ParamsError('状态参数不正确')


class SupplizerCreateForm(BaseForm):
    suloginphone = StringField('登录手机号', validators=[
        DataRequired('手机号不可以为空'),
        Regexp(r'^1\d{10}$', message='手机号格式错误'),
    ])
    sulinkphone = StringField('联系电话')
    suname = StringField('供应商名字')
    sulinkman = StringField('联系人', validators=[DataRequired('联系人不可为空')])
    suaddress = StringField('地址', validators=[DataRequired('地址不可以为空')])
    subaserate = DecimalField('最低分销比', default=0)
    sudeposit = DecimalField('押金', default=0)
    subanksn = StringField('卡号')
    subankname = StringField('银行名字')
    # supassword = StringField('密码', validators=[DataRequired('密码不可为空')])
    supassword = StringField('密码')
    suheader = StringField('头像')
    sucontract = FieldList(StringField(validators=[DataRequired('合同列表不可以为空')]))
    pbids = FieldList(StringField('品牌'))
    subusinesslicense = StringField('营业执照')
    suregisteredfund = StringField('注册资金', )
    sumaincategory = StringField('主营类目', )
    suregisteredtime = DateField('注册时间', )
    sulegalperson = StringField('法人', )
    suemail = StringField('联系邮箱', )
    sulegalpersonidcardfront = StringField('法人身份证正面', )
    sulegalpersonidcardback = StringField('法人身份证反面', )
    sugrade = IntegerField('供应商类型')

    def validate_suloginphone(self, raw):
        is_exists = Supplizer.query.filter_by_().filter_(
            Supplizer.SUloginPhone == raw.data, Supplizer.isdelete == False
        ).first()
        if is_exists:
            raise DumpliError('登陆手机号已存在')

    def validate_sulinkphone(self, raw):
        if raw.data:
            if not re.match('^1\d{10}$', raw.data):
                raise ParamsError('联系人手机号格''式错误')

    def validate_suemail(self, raw):
        if raw.data:
            if not re.match(r'^[A-Za-z\d]+([\-\_\.]+[A-Za-z\d]+)*@([A-Za-z\d]+[-.])+[A-Za-z\d]{2,4}$', raw.data):
                raise ParamsError('联系邮箱格式错误')


class SupplizerUpdateForm(BaseForm):
    suid = StringField()
    sulinkphone = StringField('联系电话')
    suname = StringField('供应商名字')
    sulinkman = StringField('联系人', validators=[DataRequired('联系人不可为空')])
    sudeposit = DecimalField('押金')
    suaddress = StringField('地址', validators=[DataRequired('地址不可以为空')])
    sustatus = StringField('供应商状态', )
    subanksn = StringField('卡号')
    subankname = StringField('银行名字')
    suheader = StringField('头像')
    sucontract = FieldList(StringField(validators=[DataRequired('合同列表不可以为空')]))
    subaserate = DecimalField('最低分销比')
    suemail = StringField('邮箱')
    pbids = FieldList(StringField('品牌'))
    subusinesslicense = StringField('营业执照')
    suregisteredfund = StringField('注册资金', )
    sumaincategory = StringField('主营类目', )
    suregisteredtime = StringField('注册时间', )
    sulegalperson = StringField('法人', )
    sulegalpersonidcardfront = StringField('法人身份证正面', )
    sulegalpersonidcardback = StringField('法人身份证反面', )

    def valid_suregisteredtime(self, raw):
        try:
            if re.match(r'^\d{4}-\d{1,2}-\d{1,2}$', raw):
                self.suregisteredtime.date = datetime.datetime.strptime(raw, '%Y-%m-%d')
            elif re.match(r'^\d{4}-\d{1,2}-\d{1,2}\s\d{1,2}:\d{1,2}:\d{1,2}$', raw):
                self.suregisteredtime.date = datetime.datetime.strptime(raw, '%Y-%m-%d %H:%M:%S')
        except Exception:
            raise ParamsError('注册时间格式错误')

    def validate_sustatus(self, raw):
        from tickets.config.enums import UserStatus
        try:
            self.sustatus.data = getattr(UserStatus, raw.data).value
        except:
            raise ParamsError('状态参数不正确')

    def validate_suid(self, raw):
        if is_supplizer():
            self.suid.data = request.user.id
        else:
            if not raw.data:
                raise ParamsError('供应商suid不可为空')

    def validate_sulinkphone(self, raw):
        if raw.data:
            if not re.match('^1\d{10}$', raw.data):
                raise ParamsError('联系人手机号格'
                                  '式错误')


class SupplizerGetForm(BaseForm):
    suid = StringField()

    def validate_suid(self, raw):
        if is_supplizer():
            self.suid.data = request.user.id
        else:
            if not raw.data:
                raise ParamsError('供应商suid不可为空')
        supplizer = Supplizer.query.filter(Supplizer.SUid == raw.data,
                                           Supplizer.isdelete == False).first_('供应商不存在')
        self.supplizer = supplizer


class SupplizerChangePasswordForm(BaseForm):
    suid = StringField('供应商id')
    supassword = StringField(validators=[DataRequired('新密码不可为空')])
    oldpassword = StringField('旧密码')

    def validate_suid(self, raw):
        if is_supplizer():
            self.suid.data = request.user.id


class SupplizerResetPasswordForm(BaseForm):
    suloginphone = StringField('登录手机号', validators=[
        DataRequired('手机号不可以为空'),
        Regexp('^1\d{10}$', message='手机号格式错误'),
    ])
    suid = StringField('供应商id')
    code = StringField('验证码')
    supassword = StringField(validators=[DataRequired('新密码不可为空')])

    def validate_suid(self, raw):
        if is_supplizer():
            self.suid.data = request.user.id


class SupplizerSendCodeForm(BaseForm):
    suloginphone = StringField('登录手机号', validators=[
        DataRequired('手机号不可以为空'),
        Regexp('^1\d{10}$', message='手机号格式错误'),
    ])


class GetVerifier(BaseForm):
    suid = StringField('供应商id')


class SetVerifier(BaseForm):
    suid = StringField('供应商id')
    phone_list = FieldList(StringField())
