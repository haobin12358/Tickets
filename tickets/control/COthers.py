import uuid

from flask import request, current_app

from tickets.config.enums import RoleType
from tickets.control.CUser import CUser
from tickets.extensions.error_response import ParamsError
from tickets.extensions.interface.user_interface import token_required, admin_required
from tickets.extensions.params_validates import parameter_required
from tickets.extensions.register_ext import db
from tickets.extensions.success_response import Success
from tickets.models import Agreement


class COthers:
    def __init__(self):
        self.user = CUser()

    def get_params(self):
        data = parameter_required()
        params_value = data.get('value')
        key = data.get('key')
        params = self.user.get_origin_parameters(params_value, key)
        return Success(data=params)

    @token_required
    def get_location(self):
        """获取定位"""
        # user = get_current_user()
        usid = getattr(request, 'user').id
        data = parameter_required(('longitude', 'latitude'))
        current_location = self.get_user_location(data.get('latitude'), data.get('longitude'), usid)
        return Success(data={'nelocation': current_location})

    @staticmethod
    def get_user_location(lat, lng, usid, ul=None):
        from tickets.common.get_location import GetLocation
        from tickets.models.user import UserLocation
        try:
            gl = GetLocation(lat, lng)
            result = gl.result
        except Exception as e:
            current_app.logger.error('解析地址失败 {}'.format(e))
            result = {
                'ULlng': lng,
                'ULlat': lat,
                'ULformattedAddress': '请稍后再试'
            }
        with db.auto_commit():
            if ul:
                ul.update(result)
                db.session.add(ul)
                return ul.ULformattedAddress
            result.setdefault('USid', usid)
            result.setdefault('ULid', str(uuid.uuid1()))
            ul = UserLocation.create(result)
            db.session.add(ul)
        return ul.ULformattedAddress

    @staticmethod
    def brand_list():
        return Success(data=[])

    @staticmethod
    def list_role():
        return Success(data=Agreement.query.filter_by(isdelete=False).order_by(Agreement.AMtype.asc()).all())

    @admin_required
    def update_role(self):
        data = parameter_required('amtype')
        # amtype = int(data.get('amtype', 0) or 0)
        with db.auto_commit():
            amtype = self._check_roletype(data.get('amtype', 0))
            role = Agreement.query.filter_by(AMtype=amtype, isdelete=False).first()
            if not role:
                raise ParamsError('规则失效')
            role.AMcontent = data.get('amcontent')
        return Success('更新成功')

    def _check_roletype(self, amtype):
        try:
            amtype_ = int(amtype or 0)
            amtype_ = RoleType(amtype_).value
            return amtype_
        except:
            current_app.logger.info('非法类型 {}'.format(amtype))
            raise ParamsError('规则不存在')
