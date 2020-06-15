import json
import os
import uuid
from datetime import datetime
from flask import current_app, request
from tickets.extensions.error_response import StatusError, ParamsError
from tickets.extensions.register_ext import mp_miniprogram, db
from tickets.extensions.weixin.mp import WeixinMPError
from tickets.models import AdminActions


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
