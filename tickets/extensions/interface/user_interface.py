from flask import request
from sqlalchemy import false

from ...extensions.error_response import AuthorityError, TokenError, NeedPhone
from ...models import User


def is_anonymous():
    """是否是游客"""
    return not hasattr(request, 'user')


def is_user():
    """是否是普通用户"""
    return hasattr(request, 'user') and request.user.model == 'User'


def is_admin():
    """是否是管理员"""
    return hasattr(request, 'user') and request.user.model == 'Admin'


def is_supplizer():
    return hasattr(request, 'user') and request.user.model == 'Supplizer'


def binded_phone():
    """是否已绑定手机号"""
    # return common_user() and getattr(get_current_user(), 'UStelphone', False)
    if is_user():
        return getattr(User.query.filter(User.isdelete == false(), User.USid == getattr(request, 'user').id).first(),
                       'UStelephone', False)
    raise TokenError()


def token_required(func):
    def inner(self, *args, **kwargs):
        if not is_anonymous():
            return func(self, *args, **kwargs)
        raise TokenError()

    return inner


def admin_required(func):
    def inner(self, *args, **kwargs):
        if not is_admin():
            raise AuthorityError()
        return func(self, *args, **kwargs)

    return inner


def phone_required(func):
    def inner(self, *args, **kwargs):
        if binded_phone():
            return func(self, *args, **kwargs)
        raise NeedPhone()

    return inner


def get_current_user():
    usid = request.user.id
    from ...models import User
    return User.query.filter(User.USid == usid, User.isdelete == False).first_('用户信息有误')


def get_current_admin():
    adid = request.user.id
    from ...models import Admin
    return Admin.query.filter(Admin.ADid == adid, Admin.isdelete == False).first_('用户信息有误')


def get_current_supplizer():
    suid = request.user.id
    from ...models import Supplizer
    return Supplizer.query.filter(Supplizer.SUid == suid, Supplizer.isdelete == False).first_('用户信息有误')
