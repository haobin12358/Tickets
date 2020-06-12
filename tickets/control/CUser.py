import os
import datetime
import re
import uuid

import requests
from flask import current_app, request
from sqlalchemy import false
from tickets.common.default_head import GithubAvatarGenerator
from tickets.config.enums import MiniUserGrade
from tickets.config.secret import MiniProgramAppId, MiniProgramAppSecret
from tickets.extensions.error_response import ParamsError, TokenError, WXLoginError, NotFound
from tickets.extensions.interface.user_interface import token_required
from tickets.extensions.params_validates import parameter_required
from tickets.extensions.register_ext import db, mp_miniprogram, qiniu_oss
from tickets.extensions.request_handler import _get_user_agent
from tickets.extensions.success_response import Success
from tickets.extensions.token_handler import usid_to_token
from tickets.extensions.weixin import WeixinLogin
from tickets.models import User, SharingParameters, UserLoginTime, UserWallet, ProductVerifier, AddressProvince, \
    AddressArea, AddressCity


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
        time_now = datetime.datetime.now()
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
