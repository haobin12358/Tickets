import os
from datetime import datetime, date, timedelta
import re
import uuid
from decimal import Decimal

import requests
from flask import current_app, request
from sqlalchemy import false, cast, Date, and_, or_, func, extract, distinct
from werkzeug.security import check_password_hash, generate_password_hash

from tickets.common.default_head import GithubAvatarGenerator
from tickets.common.id_check import DOIDCheck
from tickets.config.enums import MiniUserGrade, ApplyFrom, ActivationTypeEnum, UserLoginTimetype, \
    AdminLevel, AdminStatus, AdminAction, AdminActionS, UserStatus, ApprovalAction, OrderStatus, PayType, \
    UserCommissionStatus, WXLoginFrom, BankName, WexinBankCode
from tickets.config.secret import MiniProgramAppId, MiniProgramAppSecret
from tickets.control.BaseControl import BaseController, BaseAdmin, BaseApproval
from tickets.control.CFile import CFile
from tickets.extensions.error_response import ParamsError, TokenError, WXLoginError, NotFound, \
    InsufficientConditionsError, AuthorityError, StatusError
from tickets.extensions.interface.user_interface import token_required, phone_required, is_admin, is_supplizer, is_user, \
    get_current_admin, admin_required
from tickets.extensions.params_validates import parameter_required, validate_arg
from tickets.extensions.register_ext import db, mp_miniprogram
from tickets.extensions.request_handler import _get_user_agent
from tickets.extensions.success_response import Success
from tickets.extensions.token_handler import usid_to_token
from tickets.extensions.weixin import WeixinLogin
from tickets.extensions.weixin.mp import WeixinMPError
from tickets.models import User, SharingParameters, UserLoginTime, UserWallet, ProductVerifier, AddressProvince, \
    AddressArea, AddressCity, IDCheck, UserMedia, UserInvitation, Admin, AdminNotes, UserAccessApi, UserCommission, \
    Supplizer, CashNotes, OrderMain, SupplizerAccount, UserSubCommission


class CUser(object):
    base_admin = BaseAdmin()
    base_approval = BaseApproval()
    c_file = CFile()

    def __init__(self):
        from tickets.control.CSubcommision import CSubcommision
        self.subcommision = CSubcommision()

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
        user = self._get_exist_user((User.USopenid1 == openid,))
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
                upperd = self._get_exist_user((User.USid == superid,))
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
        user_dict = {}
        with db.auto_commit():
            isnewguy = ActivationTypeEnum.share_old.value
            if user:
                usid = user.USid
                if not user.USwxacode:
                    user_update_dict['USwxacode'] = self.wxacode_unlimit(usid)
                user.update(user_update_dict)
            else:
                current_app.logger.info('This is a new guy : {}'.format(userinfo.get('nickName')))
                isnewguy = ActivationTypeEnum.share_new.value
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
            db.session.flush()
            # 创建分佣表，更新一级分佣者状态
            if user_dict:
                current_app.logger.info('get user dict: {0}'.format(str(user_dict)))
                self.subcommision._mock_first_login(user_dict["USid"])
            else:
                pass
            if upperd:
                today = datetime.now().date()
                uin_exist = UserInvitation.query.filter(
                    cast(UserInvitation.createtime, Date) == today,
                    UserInvitation.USInviter == upperd.USid,
                    UserInvitation.USInvited == usid,
                ).first()
                if uin_exist:
                    current_app.logger.info('{}今天已经邀请过这个人了{}'.format(upperd.USid, usid))
                else:
                    uin = UserInvitation.create(
                        {'UINid': str(uuid.uuid1()), 'USInviter': upperd.USid, 'USInvited': usid,
                         'UINapi': request.path})
                    db.session.add(uin)
                    from .CActivation import CActivation
                    CActivation().add_activation(isnewguy, upperd.USid, usid)

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

        # 头像上传到oss
        self.c_file.upload_to_oss(filename, filedbname[1:], '用户头像')
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

        # 二维码上传到oss
        self.c_file.upload_to_oss(filename, filedbname[1:], '个人小程序二维码')
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
        user.USgender -= 1 if user.USgender > 0 else 1  # 仅是为了小程序端图标不修改，存储数据不变
        user.fill('usbirthday', str(user.USbirthday)[:10] if user.USbirthday else '')
        user.fill('usminilevel', MiniUserGrade(user.USminiLevel).zh_value)
        usersubcommission = UserSubCommission.query.filter(UserSubCommission.USid == getattr(request, 'user').id,
                                                           UserSubCommission.isdelete == false()) \
            .first()
        user.fill('ussuperlevel', usersubcommission.USCsuperlevel)
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

        user.fill('ticketverifier', (False if not user.UStelephone else
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
            user.fill('ustotal', 0)
            user.fill('uscash', 0)
        else:
            user.fill('usbalance', uw.UWbalance or 0)
            user.fill('ustotal', uw.UWtotal or 0)
            user.fill('uscash', uw.UWcash or 0)

    @phone_required
    def my_wallet(self):
        """我的钱包页（消费记录、提现记录）"""
        args = request.args.to_dict()
        date, option = args.get('date'), args.get('option')
        user = User.query.filter(User.isdelete == false(), User.USid == getattr(request, 'user').id).first_('请重新登录')
        if date and not re.match(r'^20\d{2}-\d{2}$', str(date)):
            raise ParamsError('date 格式错误')
        year, month = str(date).split('-') if date else (datetime.now().year, datetime.now().month)

        if option == 'expense':  # 消费记录
            transactions, total = self._get_transactions(user, year, month)
            pass
        elif option == 'withdraw':  # 提现记录
            transactions, total = self._get_withdraw(user, year, month)
        elif option == 'commission':  # 佣金收入
            transactions, total = self._get_commission(user, year, month)
        elif option == 'reward':
            transactions, total = self._get_reward(user, year, month)
        else:
            raise ParamsError('type 参数错误')
        user_wallet = UserWallet.query.filter(UserWallet.isdelete == false(), UserWallet.USid == user.USid).first()
        if user_wallet:
            uwcash = user_wallet.UWcash
        else:
            with db.auto_commit():
                user_wallet_instance = UserWallet.create({
                    'UWid': str(uuid.uuid1()),
                    'USid': user.USid,
                    'CommisionFor': ApplyFrom.user.value,
                    'UWbalance': Decimal('0.00'),
                    'UWtotal': Decimal('0.00'),
                    'UWcash': Decimal('0.00'),
                    'UWexpect': Decimal('0.00')
                })
                db.session.add(user_wallet_instance)
            uwcash = 0
        response = {'uwcash': uwcash,
                    'transactions': transactions,
                    'total': total
                    }
        return Success(data=response)

    @staticmethod
    def _get_transactions(user, year, month):
        order_mains = db.session.query(OrderMain.PRname, OrderMain.createtime,
                                       OrderMain.OMtrueMount, OrderMain.OMpayType
                                       ).filter(OrderMain.isdelete == false(),
                                                OrderMain.USid == user.USid,
                                                OrderMain.OMstatus > OrderStatus.wait_pay.value,
                                                extract('month', OrderMain.createtime) == month,
                                                extract('year', OrderMain.createtime) == year
                                                ).order_by(OrderMain.createtime.desc(), origin=True
                                                           ).all_with_page()
        transactions = [{'title': f'{"[活跃分申请] " if i[3] == PayType.scorepay.value else "[购买] "}' + i[0],
                         'time': i[1],
                         'amount': i[2],
                         } for i in order_mains if i[0] is not None]
        total = sum(i.get('amount', 0) for i in transactions)

        for item in transactions:
            item['amount'] = '- ¥{}'.format(item['amount']) if item['amount'] != 0 else '  ¥{}'.format(item['amount'])
        total = ' ¥{}'.format(total) if total == 0 else ' - ¥{}'.format(-total)
        return transactions, total

    @staticmethod
    def _get_withdraw(user, year, month):
        res = db.session.query(CashNotes.CNstatus, CashNotes.createtime, CashNotes.CNcashNum
                               ).filter(CashNotes.isdelete == false(), CashNotes.USid == user.USid,
                                        extract('month', CashNotes.createtime) == month,
                                        extract('year', CashNotes.createtime) == year
                                        ).order_by(CashNotes.createtime.desc(), origin=True).all_with_page()
        withdraw = [{'title': ApprovalAction(i[0]).zh_value, 'time': i[1], 'amount': i[2]}
                    for i in res if i[0] is not None]
        total = sum(i.get('amount', 0) for i in withdraw)
        for item in withdraw:
            item['amount'] = '¥{}'.format(item['amount'])
        total = ' ¥{}'.format(total)
        return withdraw, total

    @staticmethod
    def _get_reward(user, year, month):
        res = db.session.query(UserCommission.PRname, UserCommission.createtime,
                               UserCommission.UCcommission, UserCommission.UCstatus
                               ).filter(UserCommission.isdelete == false(),
                                        UserCommission.USid == user.USid,
                                        UserCommission.UCstatus > UserCommissionStatus.preview.value,
                                        UserCommission.UCtype == 5,
                                        extract('month', UserCommission.createtime) == month,
                                        extract('year', UserCommission.createtime) == year
                                        ).order_by(UserCommission.createtime.desc(),
                                                   origin=True).all_with_page()
        commission = [{'title': "[奖励金]" + i[0],
                       'time': i[1],
                       'amount': i[2]
                       }
                      for i in res if i[0] is not None]
        total = sum(i.get('amount', 0) for i in commission)
        for item in commission:
            item['amount'] = ' + ¥{}'.format(item['amount'])
        total = ' ¥{}'.format(total)
        return commission, total

    @staticmethod
    def _get_commission(user, year, month):
        res = db.session.query(UserCommission.PRname, UserCommission.createtime,
                               UserCommission.UCcommission, UserCommission.UCstatus
                               ).filter(UserCommission.isdelete == false(),
                                        UserCommission.USid == user.USid,
                                        UserCommission.UCstatus > UserCommissionStatus.preview.value,
                                        UserCommission.UCtype == 0,
                                        extract('month', UserCommission.createtime) == month,
                                        extract('year', UserCommission.createtime) == year
                                        ).order_by(UserCommission.createtime.desc(),
                                                   origin=True).all_with_page()
        commission = [{'title': f'[{UserCommissionStatus(i[3]).zh_value}] {i[0]}',
                       'time': i[1],
                       'amount': i[2]
                       }
                      for i in res if i[0] is not None]
        total = sum(i.get('amount', 0) for i in commission)
        for item in commission:
            item['amount'] = ' + ¥{}'.format(item['amount'])
        total = ' ¥{}'.format(total)
        return commission, total

    @phone_required
    def apply_cash(self):
        if is_admin():
            commision_for = ApplyFrom.platform.value
        elif is_supplizer():
            commision_for = ApplyFrom.supplizer.value
        else:
            commision_for = ApplyFrom.user.value
        # 提现资质校验
        self.__check_apply_cash(commision_for)
        # data = parameter_required(('cncashnum', 'cncardno', 'cncardname', 'cnbankname', 'cnbankdetail'))
        data = parameter_required(('cncashnum',))
        applyplatform = data.get('applyplatform')
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
            UserWallet.isdelete == false(),
            UserWallet.CommisionFor == commision_for
        ).first()
        balance = uw.UWcash if uw else 0
        if cncashnum > float(balance):
            current_app.logger.info('提现金额为 {0}  实际余额为 {1}'.format(cncashnum, balance))
            raise ParamsError('提现金额超出余额')
        elif not (100 <= cncashnum <= 5000):
            raise ParamsError('单次可提现范围(100 ~ 5000元)')

        uw.UWcash = Decimal(str(uw.UWcash)) - Decimal(cncashnum)
        kw = {}
        if commision_for == ApplyFrom.supplizer.value:
            sa = SupplizerAccount.query.filter(
                SupplizerAccount.SUid == request.user.id, SupplizerAccount.isdelete == false()).first()
            cn = CashNotes.create({
                'CNid': str(uuid.uuid1()),
                'USid': request.user.id,
                'CNbankName': sa.SAbankName,
                'CNbankDetail': sa.SAbankDetail,
                'CNcardNo': sa.SAcardNo,
                'CNcashNum': Decimal(cncashnum).quantize(Decimal('0.00')),
                'CNcardName': sa.SAcardName,
                'CommisionFor': commision_for
            })
            kw.setdefault('CNcompanyName', sa.SACompanyName)
            kw.setdefault('CNICIDcode', sa.SAICIDcode)
            kw.setdefault('CNaddress', sa.SAaddress)
            kw.setdefault('CNbankAccount', sa.SAbankAccount)
        else:
            user = User.query.filter(User.USid == request.user.id, User.isdelete == false()).first()

            cn = CashNotes.create({
                'CNid': str(uuid.uuid1()),
                'USid': user.USid,
                'CNcashNum': Decimal(cncashnum).quantize(Decimal('0.00')),
                'CommisionFor': commision_for,
            })
            if str(applyplatform) == str(WXLoginFrom.miniprogram.value):
                setattr(cn, 'ApplyPlatform', WXLoginFrom.miniprogram.value)
        db.session.add(cn)
        db.session.flush()
        # 创建审批流

        self.base_approval.create_approval('tocash', request.user.id, cn.CNid, commision_for, **kw)
        return Success('已成功提交提现申请， 我们将在3个工作日内完成审核，请及时关注您的账户余额')

    def __check_apply_cash(self, commision_for):
        """校验提现资质"""
        if commision_for == ApplyFrom.user.value:
            user = User.query.filter(User.USid == request.user.id, User.isdelete == false()).first()
            if str(request.json.get('applyplatform')) == str(WXLoginFrom.miniprogram.value):  # 小程序端提现跳过实名建议
                if not user:
                    raise InsufficientConditionsError('账户信息错误')
                else:
                    return
            if not user or not (user.USrealname and user.USidentification):
                raise InsufficientConditionsError('没有实名认证')

        elif commision_for == ApplyFrom.supplizer.value:
            sa = SupplizerAccount.query.filter(
                SupplizerAccount.SUid == request.user.id, SupplizerAccount.isdelete == false()).first()
            if not sa or not (sa.SAbankName and sa.SAbankDetail and sa.SAcardNo and sa.SAcardName and sa.SAcardName
                              and sa.SACompanyName and sa.SAICIDcode and sa.SAaddress and sa.SAbankAccount):
                raise InsufficientConditionsError('账户信息和开票不完整，请补全账户信息和开票信息')
            try:
                WexinBankCode(sa.SAbankName)
            except Exception:
                raise ParamsError('系统暂不支持提现账户中的银行，请在 "设置 - 商户信息 - 提现账户" 重新设置银行卡信息。 ')

    def _verify_chinese(self, name):
        """
        校验是否是纯汉字
        :param name:
        :return: 汉字, 如果有其他字符返回 []
        """
        RE_CHINESE = re.compile(r'^[\u4e00-\u9fa5]{1,8}$')
        return RE_CHINESE.findall(name)

    def get_all_province(self):
        """获取所有省份信息"""
        province_list = AddressProvince.query.all()
        current_app.logger.info('This is to get province list')
        if not province_list:
            raise NotFound('未找到省份信息')
        return Success(data=province_list)

    def get_citys_by_provinceid(self):
        """获取省份下的城市"""
        args = parameter_required(('apid',))
        current_app.logger.info('This to get city, provibceid is {0}'.format(args))
        provinceid = args.get('apid')
        city_list = AddressCity.query.filter(AddressCity.APid == provinceid).all()
        if not city_list:
            raise NotFound('未找到该省下的城市信息')
        return Success(data=city_list)

    def get_areas_by_cityid(self):
        """获取城市下的区县"""
        args = parameter_required(('acid',))
        current_app.logger.info('This to get area info, cityid is {0}'.format(args))
        cityid = args.get('acid')
        area_list = AddressArea.query.filter(AddressArea.ACid == cityid).all()
        if not area_list:
            raise NotFound('未找到该城市下的区县信息')
        return Success(data=area_list)

    @token_required
    def user_certification(self):
        """实名认证"""
        raise ParamsError('功能暂未开通，敬请期待')
        data = parameter_required(('usrealname', 'usidentification'))
        user = self._get_exist_user((User.USid == getattr(request, 'user').id,))
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

    @phone_required
    def identification(self):
        user = User.query.filter_by_(USid=getattr(request, 'user').id).first_('请重新登录')
        if not user.USidentification:
            return Success(data={})
        response = {'usrealname': user.USrealname,
                    'ustelephone': user.UStelephone,
                    'usidentification': user.USidentification
                    }
        return Success(data=response)

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

    @token_required
    def get_admin_list(self):
        """获取管理员列表"""
        superadmin = get_current_admin()
        if superadmin.ADlevel != AdminLevel.super_admin.value or \
                superadmin.ADstatus != AdminStatus.normal.value:
            raise AuthorityError('当前非超管权限')
        args = request.args.to_dict()
        page = args.get('page_num')
        count = args.get('page_size')
        if page and count:
            admins = Admin.query.filter(
                Admin.isdelete == False, Admin.ADlevel == AdminLevel.common_admin.value).order_by(
                Admin.createtime.desc()).all_with_page()
        else:
            admins = Admin.query.filter(
                Admin.isdelete == False, Admin.ADlevel == AdminLevel.common_admin.value).order_by(
                Admin.createtime.desc()).all()
        for admin in admins:
            admin.fields = ['ADid', 'ADname', 'ADheader', 'createtime', 'ADnum']
            admin.fill('adlevel', AdminLevel(admin.ADlevel).zh_value)
            admin.fill('adstatus', AdminStatus(admin.ADstatus).zh_value)
            admin.fill('adpassword', '*' * 6)
            admin.fill('adtelphone', admin.ADtelephone)
            admin_login = UserLoginTime.query.filter_by_(
                USid=admin.ADid, ULtype=UserLoginTimetype.admin.value).order_by(UserLoginTime.createtime.desc()).first()
            logintime = None
            if admin_login:
                logintime = admin_login.createtime
            admin.fill('logintime', logintime)

        return Success('获取管理员列表成功', data=admins)

    @token_required
    def list_user_commison(self):
        """查看代理商获取的佣金列表"""
        args = request.args.to_dict()
        mobile = args.get('mobile')
        name = args.get('name')
        user_query = User.query.filter(User.isdelete == false())
        if mobile:
            user_query = user_query.filter(User.UStelephone.contains(mobile.strip()))
        if name:
            user_query = user_query.filter(User.USname.contains(name.strip()))

        # users = user_query.order_by(User.createtime.desc()).all_with_page()
        # 排除审核机器人
        users = user_query.join(UserLoginTime, UserLoginTime.USid == User.USid
                                ).filter(UserLoginTime.NetType.isnot(None)
                                         ).order_by(User.createtime.desc()).all_with_page()
        for user in users:
            # 佣金
            user.fields = ['USid', 'USname', 'USheader', 'USCommission1',
                           'USCommission2', 'USCommission3', 'USlevel']
            usid = user.USid
            user_subcommision = UserSubCommission.query.filter(UserSubCommission.USid == usid,
                                                               UserSubCommission.isdelete == 0).first()
            user.fill('uscsuperlevel', user_subcommision.USCsuperlevel)
            user.fill('ustelphone', user.UStelephone)
            wallet = UserWallet.query.filter(
                UserWallet.isdelete == False,
                UserWallet.USid == usid,
            ).first()
            remain = getattr(wallet, 'UWbalance', 0)
            total = getattr(wallet, 'UWtotal', 0)
            cash = getattr(wallet, 'UWcash', 0)
            user.fill('remain', remain)
            user.fill('total', total)
            user.fill('cash', cash)
            # 粉丝数
            fans_num = User.query.filter(
                User.isdelete == False,
                User.USsupper1 == usid,
            ).count()
            user.fill('fans_num', fans_num)

            userlogintime = UserAccessApi.query.filter(
                UserAccessApi.isdelete == False,
                UserAccessApi.USid == usid
            ).order_by(
                UserAccessApi.createtime.desc()
            ).first() or UserLoginTime.query.filter(
                UserLoginTime.isdelete == False,
                UserLoginTime.USid == usid
            ).order_by(
                UserLoginTime.createtime.desc()
            ).first()
            user.fill('userlogintime',
                      getattr(userlogintime, 'createtime', user.updatetime) or user.updatetime)
            user.fill('usquery', 0)
        return Success(data=users)

    @admin_required
    def list_fans(self):
        data = parameter_required(('usid',))
        usid = data.get('usid')
        users = User.query.filter(
            User.isdelete == False,
            User.USsupper1 == usid
        ).all_with_page()
        for user in users:
            user.fields = ['USlevel', 'USname']
            user.fill('ustelphone', user.UStelephone)
            # 从该下级获得的佣金
            total = UserCommission.query.with_entities(func.sum(UserCommission.UCcommission)). \
                filter(
                UserCommission.isdelete == False,
                UserCommission.USid == usid,
                UserCommission.FromUsid == user.USid,
                UserCommission.UCstatus >= 0
            ).all()
            total = total[0][0] or 0
            user.fill('commision_from', total)
        return Success(data=users)

    @token_required
    def update_admin_password(self):
        """更新管理员密码"""
        if not is_admin():
            raise AuthorityError('权限不足')

        data = parameter_required(('password_old', 'password_new', 'password_repeat'))
        admin = get_current_admin()
        pwd_new = data.get('password_new')
        pwd_old = data.get('password_old')
        pwd_repeat = data.get('password_repeat')
        if pwd_new != pwd_repeat:
            raise ParamsError('两次输入的密码不同')
        if admin:
            if check_password_hash(admin.ADpassword, pwd_old):
                self.__check_password(pwd_new)
                with db.auto_commit():
                    admin.ADpassword = generate_password_hash(pwd_new)
                # BASEADMIN().create_action(AdminActionS.update.value, 'none', 'none')
                return Success('更新密码成功')
            current_app.logger.info('{0} update pwd failed'.format(admin.ADname))
            raise ParamsError('旧密码有误')

        raise AuthorityError('账号已被回收')

    def admin_login(self):
        """管理员登录"""
        data = parameter_required(('adname', 'adpassword'))
        admin = Admin.query.filter(Admin.isdelete == false(), Admin.ADname == data.get('adname')).first_('用户不存在')

        # 密码验证
        if admin and check_password_hash(admin.ADpassword, data.get("adpassword")):
            current_app.logger.info('管理员登录成功 %s' % admin.ADname)
            # 创建管理员登录记录
            ul_instance = UserLoginTime.create({
                "ULTid": str(uuid.uuid1()),
                "USid": admin.ADid,
                "USTip": request.remote_addr,
                "ULtype": UserLoginTimetype.admin.value,
                "UserAgent": request.user_agent.string
            })
            db.session.add(ul_instance)
            token = usid_to_token(admin.ADid, 'Admin', admin.ADlevel, username=admin.ADname)
            admin.fields = ['ADname', 'ADheader', 'ADlevel']

            admin.fill('adlevel', AdminLevel(admin.ADlevel).zh_value)
            admin.fill('adstatus', AdminStatus(admin.ADstatus).zh_value)

            return Success('登录成功', data={'token': token, "admin": admin})
        return ParamsError("用户名或密码错误")

    @token_required
    def add_admin_by_superadmin(self):
        """超级管理员添加普通管理"""
        superadmin = get_current_admin()
        if superadmin.ADlevel != AdminLevel.super_admin.value or \
                superadmin.ADstatus != AdminStatus.normal.value:
            raise AuthorityError('当前非超管权限')

        data = request.json
        current_app.logger.info("add admin data is %s" % data)
        parameter_required(('adname', 'adpassword', 'adtelphone'))
        adid = str(uuid.uuid1())
        password = data.get('adpassword')
        # 密码校验
        self.__check_password(password)

        adname = data.get('adname')
        adlevel = getattr(AdminLevel, data.get('adlevel', ''))
        adlevel = 2 if not adlevel else int(adlevel.value)
        header = data.get('adheader') or GithubAvatarGenerator().save_avatar(adid)
        # 等级校验
        if adlevel not in [1, 2, 3]:
            raise ParamsError('adlevel参数错误')
        telephone = data.get('adtelphone')
        if not re.match(r'^1[0-9]{10}$', str(telephone)):
            raise ParamsError('手机号格式错误')
        # 账户名校验
        self.__check_adname(adname, adid)
        adnum = self.__get_adnum()
        # 创建管理员
        with db.auto_commit():
            adinstance = Admin.create({
                'ADid': adid,
                'ADnum': adnum,
                'ADname': adname,
                'ADtelephone': telephone,
                'ADfirstpwd': password,
                'ADfirstname': adname,
                'ADpassword': generate_password_hash(password),
                'ADheader': header,
                'ADlevel': adlevel,
                'ADstatus': 0,
            })
            db.session.add(adinstance)

            # 创建管理员变更记录
            an_instance = AdminNotes.create({
                'ANid': str(uuid.uuid1()),
                'ADid': adid,
                'ANaction': '{0} 创建管理员{1} 等级{2}'.format(superadmin.ADname, adname, adlevel),
                "ANdoneid": request.user.id
            })

            db.session.add(an_instance)
        return Success('创建管理员成功')

    @token_required
    def update_admin(self):
        """更新管理员信息"""
        if not is_admin():
            raise AuthorityError('权限不足')
        data = request.json or {}
        admin = get_current_admin()
        if admin.ADstatus != AdminStatus.normal.value:
            raise AuthorityError('权限不足')
        update_admin = {}
        action_list = []
        with db.auto_commit():
            if data.get("adname"):
                update_admin['ADname'] = data.get("adname")
                action_list.append(str(AdminAction.ADname.value) + '为' + str(data.get("adname")) + '\n')

            if data.get('adheader'):
                update_admin['ADheader'] = data.get("adheader")
                action_list.append(str(AdminAction.ADheader.value) + '\n')
            if data.get('adtelphone'):
                # self.__check_identifyingcode(data.get('adtelphone'), data.get('identifyingcode'))
                update_admin['ADtelephone'] = data.get('adtelphone')
                action_list.append(str(AdminAction.ADtelphone.value) + '为' + str(data.get("adtelphone")) + '\n')
            password = data.get('adpassword')
            if password and password != '*' * 6:
                self.__check_password(password)
                password = generate_password_hash(password)
                update_admin['ADpassword'] = password
                action_list.append(str(AdminAction.ADpassword.value) + '为' + str(password) + '\n')

            if admin.ADlevel == AdminLevel.super_admin.value:
                filter_adid = data.get('adid') or admin.ADid
                if getattr(AdminLevel, data.get('adlevel', ""), ""):
                    update_admin['ADlevel'] = getattr(AdminLevel, data.get('adlevel')).value
                    action_list.append(
                        str(AdminAction.ADlevel.value) + '为' + getattr(AdminLevel, data.get('adlevel')).zh_value + '\n')
                if getattr(AdminStatus, data.get('adstatus', ""), ""):
                    update_admin['ADstatus'] = getattr(AdminStatus, data.get('adstatus')).value
                    action_list.append(
                        str(AdminAction.ADstatus.value) + '为' + getattr(AdminStatus,
                                                                        data.get('adstatus')).zh_value + '\n')
            else:
                filter_adid = admin.ADid
            self.__check_adname(data.get("adname"), filter_adid)

            update_admin = {k: v for k, v in update_admin.items() if v or v == 0}
            update_result = self.update_admin_by_filter(
                ad_and_filter=[Admin.ADid == filter_adid, Admin.isdelete == False],
                ad_or_filter=[], adinfo=update_admin)
            if not update_result:
                raise ParamsError('管理员不存在')
            filter_admin = Admin.query.filter(Admin.isdelete == false(), Admin.ADid == filter_adid).first_('管理员不存在')

            action_str = admin.ADname + '修改' + filter_admin.ADname + ','.join(action_list)

            an_instance = AdminNotes.create({
                'ANid': str(uuid.uuid1()),
                'ADid': filter_adid,
                'ANaction': action_str,
                "ANdoneid": request.user.id
            })
            db.session.add(an_instance)
        if is_admin():
            self.base_admin.create_action(AdminActionS.insert.value, 'AdminNotes', str(uuid.uuid1()))
        return Success("操作成功")

    def update_admin_by_filter(self, ad_and_filter, ad_or_filter, adinfo):
        return Admin.query.filter_(
            and_(*ad_and_filter), or_(*ad_or_filter), Admin.isdelete == False).update(adinfo)

    def supplizer_login(self):
        """供应商登录"""
        # 手机号登录
        data = parameter_required({'mobile': '账号', 'password': '密码'})
        mobile = data.get('mobile')
        password = data.get('password')
        supplizer = Supplizer.query.filter_by_({'SUloginPhone': mobile}).first_()

        if not supplizer:
            raise NotFound('登录账号错误')
        elif not supplizer.SUpassword:
            raise StatusError('账号正在审核中，请耐心等待')
        elif not check_password_hash(supplizer.SUpassword, password):
            raise StatusError('密码错误')
        elif supplizer.SUstatus == UserStatus.forbidden.value:
            raise StatusError('该账号已被冻结, 详情请联系管理员')
        jwt = usid_to_token(supplizer.SUid, 'Supplizer', username=supplizer.SUname)  # 供应商jwt
        supplizer.fields = ['SUlinkPhone', 'SUheader', 'SUname', 'SUgrade']
        return Success('登录成功', data={
            'token': jwt,
            'supplizer': supplizer
        })

    def __check_card_num(self, num):
        """初步校验卡号"""
        if not num:
            raise ParamsError('卡号不能为空')
        num = re.sub(r'\s+', '', str(num))
        if not num:
            raise ParamsError('卡号不能为空')
        if not (16 <= len(num) <= 19) or not self.__check_bit(num):
            raise ParamsError('请输入正确卡号')
        return True

    def __check_bit(self, num):
        """
        *从不含校验位的银行卡卡号采用Luhm校验算法获得校验位
        *该校验的过程：
        *1、从卡号最后一位数字开始，逆向将奇数位(1、3、5 等等)相加。
        *2、从卡号最后一位数字开始，逆向将偶数位数字(0、2、4等等)，先乘以2（如果乘积为两位数，则将其减去9或个位与十位相加的和），再求和。
        *3、将奇数位总和加上偶数位总和，如果可以被整除，末尾是0 ，如果不能被整除，则末尾为10 - 余数
        """
        num_str_list = list(num[:-1])
        num_str_list.reverse()
        if not num_str_list:
            return False

        num_list = []
        for num_item in num_str_list:
            num_list.append(int(num_item))

        sum_odd = sum(num_list[1::2])
        sum_even = sum([n * 2 if n * 2 < 10 else n * 2 - 9 for n in num_list[::2]])
        luhm_sum = sum_odd + sum_even

        if (luhm_sum % 10) == 0:
            check_num = 0
        else:
            check_num = 10 - (luhm_sum % 10)
        return check_num == int(num[-1])

    def _verify_cardnum(self, num):
        """获取所属行"""
        bank_url = 'https://ccdcapi.alipay.com/validateAndCacheCardInfo.json?cardNo={}&cardBinCheck=true'
        url = bank_url.format(num)
        response = requests.get(url).json()
        if response and response.get('validated'):
            validated = response.get('validated')
            bankname = getattr(BankName, response.get('bank'), None)
            if bankname:
                bankname = bankname.zh_value
            else:
                validated = False
                bankname = None
        else:
            bankname = None
            validated = False

        return Success('获取银行信息成功', data={'cnbankname': bankname, 'validated': validated})

    def __check_password(self, password):
        if not password or len(password) < 4:
            raise ParamsError('密码长度低于4位')
        zh_pattern = re.compile(r'[\u4e00-\u9fa5]+')
        match = zh_pattern.search(password)
        if match:
            raise ParamsError(u'密码包含中文字符')
        return True

    def __check_adname(self, adname, adid):
        """账户名校验"""
        if not adname or adid:
            return True
        suexist = Admin.query.filter_by(ADname=adname, isdelete=False).first()
        if suexist and suexist.ADid != adid:
            raise ParamsError('用户名已存在')
        return True

    def __get_adnum(self):
        admin = Admin.query.order_by(Admin.ADnum.desc()).first()
        if not admin:
            return 100000
        return admin.ADnum + 1

    @admin_required
    def user_data_overview(self):
        """用户数概览"""
        days = self._get_nday_list(7)
        user_count, ip_count, uv_count = [], [], []
        # user_count = db.session.query(*[func.count(cast(User.createtime, Date) <= day) for day in days]
        #                               ).filter(User.isdelete == False).all()
        for day in days:
            ucount = db.session.query(func.count(distinct(User.USid))
                                      ).join(UserLoginTime, UserLoginTime.USid == User.USid
                                             ).filter(User.isdelete == false(),
                                                      cast(User.createtime, Date) <= day,
                                                      UserLoginTime.USid == User.USid,
                                                      UserLoginTime.NetType.isnot(None)).scalar()
            user_count.append(ucount)
            ipcount = db.session.query(UserAccessApi.USTip).filter(UserAccessApi.isdelete == false(),
                                                                   cast(UserAccessApi.createtime, Date) == day,
                                                                   UserAccessApi.NetType.isnot(None),
                                                                   ).group_by(UserAccessApi.USTip).count()
            ip_count.append(ipcount)
            uvcount = db.session.query(UserAccessApi.USid).filter(UserAccessApi.isdelete == false(),
                                                                  cast(UserAccessApi.createtime, Date) == day,
                                                                  UserAccessApi.NetType.isnot(None),
                                                                  ).group_by(UserAccessApi.USid).count()
            uv_count.append(uvcount)

        series = [{'name': '用户数量', 'data': user_count},
                  {'name': '独立ip', 'data': ip_count},
                  {'name': 'uv', 'data': uv_count}]
        return Success(data={'days': days, 'series': series})

    @staticmethod
    def _get_nday_list(n):
        before_n_days = []
        for i in range(n)[::-1]:
            before_n_days.append(str(date.today() - timedelta(days=i)))
        return before_n_days

    @token_required
    def get_cash_notes(self):
        today = date.today()
        data = parameter_required()

        month = data.get('month') or today.month
        year = data.get('year') or today.year

        cash_notes = CashNotes.query.filter(
            CashNotes.USid == request.user.id,
            extract('year', CashNotes.createtime) == year,
            extract('month', CashNotes.createtime) == month
        ).order_by(
            CashNotes.createtime.desc()).all_with_page()

        cn_total = Decimal(0)
        for cash_note in cash_notes:
            # if cash_note.CNstatus == CashStatus.agree.value:
            #     cash_flow = CashFlow.query.filter(CashFlow.isdelete == False,
            #                                       CashFlow.CNid == cash_note.CNid
            #                                       ).first()
            #     if cash_flow and cash_flow.status == 'SUCCESS':
            #         cash_note = CashStatus.alreadyAccounted.value
            #         # todo 异步任务完成，这里只处理异常情况
            # if cash_note.CNstatus == CashStatus.alreadyAccounted.value:
            if cash_note.CNstatus == ApprovalAction.agree.value:  # todo ??? 可提现余额？？
                cn_total += Decimal(str(cash_note.CNcashNum))
            cash_note.fields = [
                'CNid',
                'createtime',
                'CNbankName',
                'CNbankDetail',
                'CNcardNo',
                'CNcardName',
                'CNcashNum',
                'CNstatus',
                'CNrejectReason',
            ]
            # cash_note.fill('cnstatus_zh', CashStatus(cash_note.CNstatus).zh_value)
            # cash_note.fill('cnstatus_en', CashStatus(cash_note.CNstatus).name)
            cash_note.fill('cnstatus_zh', ApprovalAction(cash_note.CNstatus).zh_value)
            cash_note.fill('cnstatus_en', ApprovalAction(cash_note.CNstatus).name)

        return Success('获取提现记录成功', data={'cash_notes': cash_notes, 'cntotal': cn_total})
