import os
from datetime import datetime
import re
import uuid
from decimal import Decimal

import requests
from flask import current_app, request
from sqlalchemy import false
from tickets.common.default_head import GithubAvatarGenerator
from tickets.common.id_check import DOIDCheck
from tickets.config.enums import MiniUserGrade, ApplyFrom, WXLoginFrom
from tickets.config.secret import MiniProgramAppId, MiniProgramAppSecret
from tickets.control.BaseControl import BaseController
from tickets.extensions.error_response import ParamsError, TokenError, WXLoginError, NotFound, \
    InsufficientConditionsError
from tickets.extensions.interface.user_interface import token_required, phone_required, is_admin, is_supplizer, is_user
from tickets.extensions.params_validates import parameter_required, validate_arg
from tickets.extensions.register_ext import db, mp_miniprogram, qiniu_oss
from tickets.extensions.request_handler import _get_user_agent
from tickets.extensions.success_response import Success
from tickets.extensions.token_handler import usid_to_token
from tickets.extensions.weixin import WeixinLogin
from tickets.extensions.weixin.mp import WeixinMPError
from tickets.models import User, SharingParameters, UserLoginTime, UserWallet, ProductVerifier, AddressProvince, \
    AddressArea, AddressCity, IDCheck, UserMedia


class CUser(object):
    @staticmethod
    def _decrypt_encrypted_user_data(encrypteddata, session_key, iv):
        """小程序信息解密"""
        from ..common.WXBizDataCrypt import WXBizDataCrypt
        pc = WXBizDataCrypt(MiniProgramAppId, session_key)
        plain_text = pc.decrypt(encrypteddata, iv)
        return plain_text

    def mini_program_login(self):
        args = request.json
        code = args.get("code")
        info = args.get("info")
        current_app.logger.info('info: {}'.format(info))
        userinfo = info.get('userInfo')
        if not userinfo:
            raise TokenError

        mplogin = WeixinLogin(MiniProgramAppId, MiniProgramAppSecret)
        try:
            get_data = mplogin.jscode2session(code)
            current_app.logger.info('get_code2session_response: {}'.format(get_data))
            session_key = get_data.get('session_key')
            openid = get_data.get('openid')
            unionid = get_data.get('unionid')
        except Exception as e:
            current_app.logger.error('mp_login_error : {}'.format(e))
            raise WXLoginError
        if not unionid or not openid:
            current_app.logger.info('pre get unionid: {}'.format(unionid))
            current_app.logger.info('pre get openid: {}'.format(openid))
            encrypteddata = info.get('encryptedData')
            iv = info.get('iv')
            try:
                encrypted_user_info = self._decrypt_encrypted_user_data(encrypteddata, session_key, iv)
                unionid = encrypted_user_info.get('unionId')
                openid = encrypted_user_info.get('openId')
                current_app.logger.info('encrypted_user_info: {}'.format(encrypted_user_info))
            except Exception as e:
                current_app.logger.error('用户信息解密失败: {}'.format(e))

        current_app.logger.info('get unionid is {}'.format(unionid))
        current_app.logger.info('get openid is {}'.format(openid))
        user = self._get_exist_user((User.USunionid == openid,))
        if user:
            current_app.logger.info('get exist user by openid: {}'.format(user.__dict__))
        elif unionid:
            user = self._get_exist_user((User.USunionid == unionid,))
            if user:
                current_app.logger.info('get exist user by unionid: {}'.format(user.__dict__))

        head = self._get_local_head(userinfo.get("avatarUrl"), openid)
        sex = userinfo.get('gender')
        sex = int(sex) if str(sex) in '12' else 0
        if args.get('secret_usid'):
            try:
                superid = self._base_decode(args.get('secret_usid'))
                current_app.logger.info('secret_usid --> superid {}'.format(superid))
                upperd = self._get_exist_user((User.USid == superid))
                current_app.logger.info('mp_login get supper user : {0}'.format(upperd.__dict__))
                if user and upperd.USid == user.USid:
                    upperd = None
            except Exception as ee:
                current_app.logger.info('解析secret_usid时失败： {}'.format(ee))
                upperd = None
        else:
            upperd = None

        user_update_dict = {'USheader': head,
                            'USname': userinfo.get('nickName'),
                            'USopenid1': openid,
                            'USgender': sex,
                            'USunionid': unionid
                            }
        with db.auto_commit():

            if user:
                usid = user.USid
                if not user.USwxacode:
                    user_update_dict['USwxacode'] = self.wxacode_unlimit(usid)
                user.update(user_update_dict)
            else:
                current_app.logger.info('This is a new guy : {}'.format(userinfo.get('nickName')))
                usid = str(uuid.uuid1())
                user_dict = {
                    'USid': usid,
                    'USname': userinfo.get('nickName'),
                    'USgender': sex,
                    'USheader': head,
                    'USintegral': 0,
                    'USlevel': 1,
                    'USopenid1': openid,
                    'USunionid': unionid,
                    'USwxacode': self.wxacode_unlimit(usid)
                }
                if upperd:
                    # 有邀请者
                    user_dict.setdefault('USsupper1', upperd.USid)
                    user_dict.setdefault('USsupper2', upperd.USsupper1)
                    user_dict.setdefault('USsupper3', upperd.USsupper2)
                user = User.create(user_dict)
            db.session.add(user)

            userloggintime = UserLoginTime.create({"ULTid": str(uuid.uuid1()),
                                                   "USid": usid,
                                                   "USTip": request.remote_addr
                                                   })
            useragent = _get_user_agent()
            if useragent:
                setattr(userloggintime, 'OSVersion', useragent[0])
                setattr(userloggintime, 'PhoneModel', useragent[1])
                setattr(userloggintime, 'WechatVersion', useragent[2])
                setattr(userloggintime, 'NetType', useragent[3])
                setattr(userloggintime, 'UserAgent', useragent[4])
            db.session.add(userloggintime)

        token = usid_to_token(user.USid, level=user.USlevel, username=user.USname)
        binded_phone = True if user and user.UStelephone else False
        data = {'token': token, 'binded_phone': binded_phone, 'session_key': session_key}
        current_app.logger.info('return_data : {}'.format(data))
        return Success('登录成功', data=data)

    @staticmethod
    def _get_exist_user(filter_args, msg=None):
        return User.query.filter(User.isdelete == false(), *filter_args).first_(msg)

    @token_required
    def bind_phone(self):
        """小程序绑定手机号更新用户"""
        data = parameter_required(('session_key',))
        phone = data.get('phonenumber')
        if not phone:
            raise ParamsError('为获得更优质的服务，请允许授权您的手机号码')

        user = self._get_exist_user((User.USid == getattr(request, 'user').id,))
        if user.UStelephone:
            raise TokenError('您已绑定过手机号码')

        session_key = data.get('session_key')
        current_app.logger.info('手机加密数据为{}'.format(phone))
        encrypteddata = phone.get('encryptedData')
        iv = phone.get('iv')

        try:
            encrypted_user_info = self._decrypt_encrypted_user_data(encrypteddata, session_key, iv)
        except Exception as e:
            current_app.logger.error('手机号解密失败: {}'.format(e))
            raise WXLoginError()

        current_app.logger.info(f'plain_text: {encrypted_user_info}')
        phonenumber = encrypted_user_info.get('phoneNumber')
        covered_number = str(phonenumber).replace(str(phonenumber)[3:7], '*' * 4)

        if self._get_exist_user((User.USid != getattr(request, 'user').id, User.UStelephone == phonenumber)):
            raise ParamsError(f'该手机号({covered_number})已被其他用户绑定，请联系客服处理')

        with db.auto_commit():
            user.update({'UStelephone': phonenumber})
            db.session.add(user)
            res_user = user

        token = usid_to_token(res_user.USid, level=res_user.USlevel, username=res_user.USname)  # 更换token
        response = {'phonenumber': covered_number, 'token': token}
        current_app.logger.info('return_data: {}'.format(response))
        return Success('绑定成功', response)

    def _get_local_head(self, headurl, openid):
        """转置微信头像到服务器，用以后续二维码生成"""
        if not headurl:
            return GithubAvatarGenerator().save_avatar(openid)
        data = requests.get(headurl)
        filename = openid + '.png'
        filepath, filedbpath = self._get_path('avatar')
        filedbname = os.path.join(filedbpath, filename)
        filename = os.path.join(filepath, filename)
        with open(filename, 'wb') as head:
            head.write(data.content)

        # 头像上传到七牛云
        if current_app.config.get('IMG_TO_OSS'):
            try:
                qiniu_oss.save(data=filename, filename=filedbname[1:])
            except Exception as e:
                current_app.logger.error('头像转存七牛云出错 : {}'.format(e))
        return filedbname

    def _get_path(self, fold):
        """获取服务器上文件路径"""
        time_now = datetime.now()
        year = str(time_now.year)
        month = str(time_now.month)
        day = str(time_now.day)
        filepath = os.path.join(current_app.config['BASEDIR'], 'img', fold, year, month, day)
        file_db_path = os.path.join('/img', fold, year, month, day)
        if not os.path.isdir(filepath):
            os.makedirs(filepath)
        return filepath, file_db_path

    def _base_decode(self, raw, raw_name='secret_usid'):
        import base64
        if raw_name == 'secret_usid' and len(raw) < 20:
            raw = self.get_origin_parameters(raw, raw_name)
        decoded = base64.b64decode(raw + '=' * (4 - len(raw) % 4)).decode()
        return decoded

    def _base_encode(self, raw):
        import base64
        raw = raw.encode()
        return base64.b64encode(raw).decode()

    @staticmethod
    def shorten_parameters(raw, usid, raw_name):
        """
        缩短分享参数
        :param raw: 要分享的参数
        :param usid: 用户id
        :param raw_name: 分享参数名
        :return: 缩短后的参数
        """
        spsid = db.session.query(SharingParameters.SPSid).filter(SharingParameters.SPScontent == raw,
                                                                 SharingParameters.USid == usid,
                                                                 SharingParameters.SPSname == raw_name
                                                                 ).scalar()
        current_app.logger.info('exist spsid : {}'.format(spsid))
        if not spsid:
            with db.auto_commit():
                sps = SharingParameters.create({'USid': usid, 'SPScontent': raw, 'SPSname': raw_name})
                db.session.add(sps)
            spsid = sps.SPSid
        return spsid

    @staticmethod
    def get_origin_parameters(param, spsname):
        """
        恢复被缩短的分享参数
        :param param:  缩短的参数
        :param spsname: 缩短的参数名
        :return:  恢复好的原来的参数
        """
        return db.session.query(SharingParameters.SPScontent).filter(SharingParameters.SPSid == param,
                                                                     SharingParameters.SPSname == spsname
                                                                     ).scalar()

    def wxacode_unlimit(self, usid, scene=None, img_name=None, **kwargs):
        """
        生成带参数的小程序码
        :param usid: 用户id
        :param scene: 需要携带的参数，dict型参数
        :param img_name: 图片名，同一日再次生成同名图片会被替换
        """
        savepath, savedbpath = self._get_path('qrcode')
        secret_usid = self._base_encode(usid)
        if not img_name:  # 默认图片名称，再次生成会替换同名图片
            img_name = secret_usid
        filename = os.path.join(savepath, '{}.jpg'.format(img_name))
        filedbname = os.path.join(savedbpath, '{}.jpg'.format(img_name))
        current_app.logger.info('filename: {} ; filedbname: {}'.format(filename, filedbname))
        if not scene:
            scene = {'params': self.shorten_parameters('secret_usid={}'.format(secret_usid), usid, 'params')}
        scene_str = self.dict_to_query_str(scene)
        current_app.logger.info('get scene str: {}'.format(scene_str))
        try:
            with open(filename, 'wb') as f:
                buffer = mp_miniprogram.get_wxacode_unlimit(scene_str, **kwargs)
                if len(buffer) < 500:
                    current_app.logger.error('buffer error：{}'.format(buffer))
                    filedbname = None
                f.write(buffer)
        except Exception as e:
            current_app.logger.error('生成个人小程序码失败：{}'.format(e))
            filedbname = None

        # 二维码上传到七牛云
        if current_app.config.get('IMG_TO_OSS'):
            try:
                qiniu_oss.save(data=filename, filename=filedbname[1:])
            except Exception as e:
                current_app.logger.error('个人小程序码转存七牛云失败 ： {}'.format(e))
        return filedbname

    @staticmethod
    def dict_to_query_str(kwargs):
        """
        :param kwargs: {'name':'python'， ‘age’:30}
        :return 'name=python&age=30'
        """
        if not isinstance(kwargs, dict):
            return
        return '&'.join(map(lambda x: '{}={}'.format(x, kwargs.get(x)), kwargs.keys()))

    @staticmethod
    def test_login():
        """测试登录"""
        data = parameter_required()
        tel = data.get('ustelephone')
        user = User.query.filter(User.isdelete == false(), User.UStelephone == tel).first()
        if not user:
            raise NotFound
        token = usid_to_token(user.USid, model='User', username=user.USname)
        return Success(data={'token': token, 'usname': user.USname})

    @token_required
    def get_secret_usid(self):
        """获取base64编码后的usid"""
        secret_usid = self._base_encode(getattr(request, 'user').id)
        return Success(data={
            'secret_usid': secret_usid,
        })

    @token_required
    def update_usinfo(self):
        """更新个人资料"""
        user = self._get_exist_user((User.USid == getattr(request, 'user').id,), '请重新登录')
        data = parameter_required()
        usheader = data.get('usheader')
        usareaid, usbirthday = data.get('aaid'), data.get('usbirthday')
        usbirthday = validate_arg(r'^\d{4}-\d{2}-\d{2}$', usbirthday, '请按正确的生日格式填写')
        if usareaid:
            db.session.query(AddressArea.AAid).filter(AddressArea.AAid == usareaid).first_('请选择正确的地区')
        try:  # 检查昵称填写
            check_content = data.get('usname')
            check_res = mp_miniprogram.msg_sec_check(check_content)
            current_app.logger.info('content_sec_check: {}'.format(check_res))
        except WeixinMPError as e:
            current_app.logger.info('check result: {}'.format(e))
            raise ParamsError('您输入的昵称含有部分敏感词汇,请检查后重新填写')
        # 图片校验
        usheader_dir = usheader
        filepath = os.path.join(current_app.config['BASEDIR'],
                                str(usheader).split('.com')[-1].split('.cn')[-1][1:].split('_')[0])
        BaseController().img_check(filepath, '您上传的头像')

        with db.auto_commit():
            user.update({'UScustomizeName': data.get('usname'),
                         'UScustomizeBirthday': usbirthday,
                         'USareaId': usareaid,
                         'UScustomizeHeader': data.get('usheader'),
                         })
            db.session.add(user)
        return Success('修改成功')

    @token_required
    def get_home(self):
        """获取个人主页信息"""
        user = User.query.filter(User.USid == getattr(request, 'user').id, User.isdelete == false()).first()
        if not user:
            raise TokenError('请重新登录')
        user.fields = ['USname', 'USname', 'USgender', 'USheader', 'USwxacode']
        user.fill('usbirthday', str(user.USbirthday)[:10])
        user.fill('usminilevel', MiniUserGrade(user.USminiLevel).zh_value)
        self.__user_fill_uw_total(user)
        user.fill('verified', bool(user.USidentification))  # 是否信用认证
        if not user.USwxacode:
            with db.auto_commit():
                user.USwxacode = self.wxacode_unlimit(user.USid)

        address = db.session.query(AddressProvince.APid, AddressProvince.APname, AddressCity.ACid,
                                   AddressCity.ACname, AddressArea.AAid, AddressArea.AAname).filter(
            AddressArea.ACid == AddressCity.ACid, AddressCity.APid == AddressProvince.APid,
            AddressArea.AAid == user.USareaId).first()
        usarea_info = [{'apid': address[0], 'apname': address[1]},
                       {'acid': address[2], 'acname': address[3]},
                       {'aaid': address[4], 'aaname': address[5]}] if address else []
        user.fill('usarea_info', usarea_info)
        user.fill('usarea_str', '-'.join(map(lambda x: address[x], (1, 3, 5))) if address else '')

        user.fill('product_verifier', (False if not user.UStelephone else
                                       True if ProductVerifier.query.filter(ProductVerifier.isdelete == false(),
                                                                            ProductVerifier.PVphone == user.UStelephone
                                                                            ).first() else False))
        return Success('获取用户信息成功', data=user)

    def __user_fill_uw_total(self, user):
        """用户增加用户余额和用户总收益"""
        # 增加待结算佣金
        uw = UserWallet.query.filter(UserWallet.USid == user.USid).first()
        if not uw:
            user.fill('usbalance', 0)
            # user.fill('ustotal', 0)
            # user.fill('uscash', 0)
        else:
            user.fill('usbalance', uw.UWbalance or 0)
            # user.fill('ustotal', uw.UWtotal or 0)
            # user.fill('uscash', uw.UWcash or 0)
        # todo 佣金部分
        # ucs = UserCommission.query.filter(
        #     UserCommission.USid == user.USid,
        #     UserCommission.UCstatus == UserCommissionStatus.preview.value,
        #     UserCommission.isdelete == False).all()
        # uc_total = sum([Decimal(str(uc.UCcommission)) for uc in ucs])
        #
        # uswithdrawal = db.session.query(func.sum(CashNotes.CNcashNum)
        #                                 ).filter(CashNotes.USid == user.USid,
        #                                          CashNotes.isdelete == False,
        #                                          CashNotes.CNstatus == ApprovalAction.submit.value
        #                                          # CashNotes.CNstatus.in_([CashStatus.submit.value,
        #                                          #                        CashStatus.agree.value])
        #                                          ).scalar()
        #
        # user.fill('uswithdrawal', uswithdrawal or 0)
        #
        # user.fill('usexpect', float('%.2f' % uc_total))

    @phone_required
    def my_wallet(self):
        """我的钱包页（消费记录、提现记录）"""
        args = request.args.to_dict()
        date, option = args.get('date'), args.get('option')
        user = User.query.filter(User.isdelete == false(), User.USid == getattr(request, 'user').id).first_('请重新登录')
        if date and not re.match(r'^20\d{2}-\d{2}$', str(date)):
            raise ParamsError('date 格式错误')
        year, month = str(date).split('-') if date else (datetime.now().year, datetime.now().month)

        # todo mock data
        transactions = [{
            "amount": "-¥3.05",
            "time": "2019-07-01 16:38:29",
            "title": "西安-宝鸡-咸阳·二日"
        }]
        total = '-3.05'
        uwcash = 11

        if option == 'expense':  # 消费记录
            # transactions, total = self._get_transactions(user, year, month, args)
            pass
        elif option == 'withdraw':  # 提现记录
            # transactions, total = self._get_withdraw(user, year, month)
            pass
        elif option == 'commission':  # 佣金收入
            pass
        else:
            raise ParamsError('type 参数错误')
        # user_wallet = UserWallet.query.filter(UserWallet.isdelete == false(), UserWallet.USid == user.USid).first()
        # if user_wallet:
        #     uwcash = user_wallet.UWcash
        # else:
        #     with db.auto_commit():
        #         user_wallet_instance = UserWallet.create({
        #             'UWid': str(uuid.uuid1()),
        #             'USid': user.USid,
        #             'CommisionFor': ApplyFrom.user.value,
        #             'UWbalance': Decimal('0.00'),
        #             'UWtotal': Decimal('0.00'),
        #             'UWcash': Decimal('0.00'),
        #             'UWexpect': Decimal('0.00')
        #         })
        #         db.session.add(user_wallet_instance)
        #         uwcash = 0
        response = {'uwcash': uwcash,
                    'transactions': transactions,
                    'total': total
                    }
        return Success(data=response).get_body(total_count=1, total_page=1)

    @phone_required
    def apply_cash(self):
        if is_admin():
            commision_for = ApplyFrom.platform.value
        elif is_supplizer():
            commision_for = ApplyFrom.supplizer.value
        else:
            commision_for = ApplyFrom.user.value
        # 提现资质校验
        # self.__check_apply_cash(commision_for)
        # data = parameter_required(('cncashnum', 'cncardno', 'cncardname', 'cnbankname', 'cnbankdetail'))
        data = parameter_required(('cncashnum',))
        try:
            cncashnum = data.get('cncashnum')
            if not re.match(r'(^[1-9](\d+)?(\.\d{1,2})?$)|(^0$)|(^\d\.\d{1,2}$)', str(cncashnum)):
                raise ValueError
            cncashnum = float(cncashnum)
        except Exception as e:
            current_app.logger.error('cncashnum value error: {}'.format(e))
            raise ParamsError('提现金额格式错误')
        uw = UserWallet.query.filter(
            UserWallet.USid == request.user.id,
            UserWallet.isdelete == False,
            UserWallet.CommisionFor == commision_for
        ).first()
        balance = uw.UWcash if uw else 0
        if cncashnum > float(balance):
            current_app.logger.info('提现金额为 {0}  实际余额为 {1}'.format(cncashnum, balance))
            raise ParamsError('提现金额超出余额')
        elif not (0.30 <= cncashnum <= 5000):
            raise ParamsError('当前测试版本单次可提现范围(0.30 ~ 5000元)')

        uw.UWcash = Decimal(str(uw.UWcash)) - Decimal(cncashnum)
        kw = {}
        if commision_for == ApplyFrom.supplizer.value:
            pass
            # todo 供应商提现
            # sa = SupplizerAccount.query.filter(
            #     SupplizerAccount.SUid == request.user.id, SupplizerAccount.isdelete == False).first()
            # cn = CashNotes.create({
            #     'CNid': str(uuid.uuid1()),
            #     'USid': request.user.id,
            #     'CNbankName': sa.SAbankName,
            #     'CNbankDetail': sa.SAbankDetail,
            #     'CNcardNo': sa.SAcardNo,
            #     'CNcashNum': Decimal(cncashnum).quantize(Decimal('0.00')),
            #     'CNcardName': sa.SAcardName,
            #     'CommisionFor': commision_for
            # })
            # kw.setdefault('CNcompanyName', sa.SACompanyName)
            # kw.setdefault('CNICIDcode', sa.SAICIDcode)
            # kw.setdefault('CNaddress', sa.SAaddress)
            # kw.setdefault('CNbankAccount', sa.SAbankAccount)
        else:
            user = User.query.filter(User.USid == request.user.id, User.isdelete == False).first()

        #     cn = CashNotes.create({
        #         'CNid': str(uuid.uuid1()),
        #         'USid': user.USid,
        #         'CNcashNum': Decimal(cncashnum).quantize(Decimal('0.00')),
        #         'CommisionFor': commision_for
        #     })
        #     if str(applyplatform) == str(WXLoginFrom.miniprogram.value):
        #         setattr(cn, 'ApplyPlatform', WXLoginFrom.miniprogram.value)
        # db.session.add(cn)
        # if is_admin():
        #     BASEADMIN().create_action(AdminActionS.insert.value, 'CashNotes', str(uuid.uuid1()))
        # db.session.flush()
        # # 创建审批流
        #
        # self.create_approval('tocash', request.user.id, cn.CNid, commision_for, **kw)
        return Success('已成功提交提现申请， 我们将在3个工作日内完成审核，请及时关注您的账户余额')

    def __check_apply_cash(self, commision_for):
        """校验提现资质"""
        user = User.query.filter(User.USid == request.user.id, User.isdelete == False).first()
        if not user or not (user.USrealname and user.USidentification):
            raise InsufficientConditionsError('没有实名认证')
        #
        # elif commision_for == ApplyFrom.supplizer.value:
        #     sa = SupplizerAccount.query.filter(
        #         SupplizerAccount.SUid == request.user.id, SupplizerAccount.isdelete == False).first()
        #     if not sa or not (sa.SAbankName and sa.SAbankDetail and sa.SAcardNo and sa.SAcardName and sa.SAcardName
        #                       and sa.SACompanyName and sa.SAICIDcode and sa.SAaddress and sa.SAbankAccount):
        #         raise InsufficientConditionsError('账户信息和开票不完整，请补全账户信息和开票信息')
        #     try:
        #         WexinBankCode(sa.SAbankName)
        #     except Exception:
        #         raise ParamsError('系统暂不支持提现账户中的银行，请在 "设置 - 商户信息 - 提现账户" 重新设置银行卡信息。 ')

    def _verify_chinese(self, name):
        """
        校验是否是纯汉字
        :param name:
        :return: 汉字, 如果有其他字符返回 []
        """
        RE_CHINESE = re.compile(r'^[\u4e00-\u9fa5]{1,8}$')
        return RE_CHINESE.findall(name)

    @token_required
    def user_certification(self):
        """实名认证"""
        data = parameter_required(('usrealname', 'usidentification'))
        user = self._get_exist_user((User.USid == getattr(request, 'user').id, ))
        if user.USidentification:
            raise ParamsError('已提交过认证')
        usrealname, ustelephone = data.get('usrealname'), data.get('ustelephone')
        usidentification = data.get('usidentification')
        if not re.match(r'^1\d{10}$', ustelephone):
            raise ParamsError('请填写正确的手机号码')
        checked_name = self._verify_chinese(usrealname)
        if not checked_name or len(checked_name[0]) < 2:
            raise ParamsError('请正确填写真实姓名')
        if len(usidentification) < 18:
            raise ParamsError('请正确填写身份证号码')
        with db.auto_commit():
            res = self.check_idcode(data, user)
        return res

    def check_idcode(self, data, user):
        """验证用户身份姓名是否正确"""

        name = data.get("usrealname")
        idcode = data.get("usidentification")
        if not (name and idcode):
            raise ParamsError('姓名和身份证号码不能为空')
        idcheck = self.get_idcheck_by_name_code(name, idcode)
        if not idcheck:
            idcheck = DOIDCheck(name, idcode)
            newidcheck_dict = {
                "IDCid": str(uuid.uuid1()),
                "IDCcode": idcheck.idcode,
                "IDCname": idcheck.name,
                "IDCresult": idcheck.result
            }
            if idcheck.result:
                newidcheck_dict['IDCrealName'] = idcheck.check_response.get('result').get('realName')
                newidcheck_dict['IDCcardNo'] = idcheck.check_response.get('result').get('cardNo')
                newidcheck_dict['IDCaddrCode'] = idcheck.check_response.get('result').get('details').get('addrCode')
                newidcheck_dict['IDCbirth'] = idcheck.check_response.get('result').get('details').get('birth')
                newidcheck_dict['IDCsex'] = idcheck.check_response.get('result').get('details').get('sex')
                newidcheck_dict['IDCcheckBit'] = idcheck.check_response.get('result').get('details').get('checkBit')
                newidcheck_dict['IDCaddr'] = idcheck.check_response.get('result').get('details').get('addr')
                newidcheck_dict['IDCerrorCode'] = idcheck.check_response.get('error_code')
                newidcheck_dict['IDCreason'] = idcheck.check_response.get('reason')
            else:
                newidcheck_dict['IDCerrorCode'] = idcheck.check_response.get('error_code')
                newidcheck_dict['IDCreason'] = idcheck.check_response.get('reason')
            newidcheck = IDCheck.create(newidcheck_dict)
            check_result = idcheck.result
            check_message = idcheck.check_response.get('reason')
            db.session.add(newidcheck)
        else:
            check_message = idcheck.IDCreason
            check_result = idcheck.IDCresult

        if check_result:
            # 如果验证成功，更新用户信息
            # update_result = self.update_user_by_filter(us_and_filter=[User.USid == request.user.id], us_or_filter=[],
            #                            usinfo={"USrealname": name, "USidentification": idcode})
            # if not update_result:
            #     gennerc_log('update user error usid = {0}, name = {1}, identification = {2}'.format(
            #         request.user.id, name, idcode), info='error')
            #     raise SystemError('服务器异常')
            user.USrealname = name
            user.USplayName = name
            user.USidentification = idcode
            UserMedia.query.filter(UserMedia.USid == request.user.id,
                                   UserMedia.isdelete == false()).update({'isdelete': True})
            um_front = UserMedia.create({
                "UMid": str(uuid.uuid1()),
                "USid": request.user.id,
                "UMurl": data.get("umfront"),
                "UMtype": 1
            })
            um_back = UserMedia.create({
                "UMid": str(uuid.uuid1()),
                "USid": request.user.id,
                "UMurl": data.get("umback"),
                "UMtype": 2
            })
            db.session.add(um_front)
            db.session.add(um_back)
            return Success('实名认证成功', data=check_message)
        raise ParamsError('实名认证失败：{0}'.format(check_message))

    @staticmethod
    def get_idcheck_by_name_code(name, idcode):
        return IDCheck.query.filter(
            IDCheck.IDCcode == idcode,
            IDCheck.IDCname == name,
            IDCheck.IDCerrorCode != 80008,
            IDCheck.isdelete == False
        ).first_()
