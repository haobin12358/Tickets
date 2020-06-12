from ..control.CUser import CUser
from ..extensions.base_resource import Resource


class AUser(Resource):
    def __init__(self):
        self.cuser = CUser()

    def get(self, user):
        apis = {
            'get_home': self.cuser.get_home,  # 获取个人首页
        }
        return apis

    def post(self, user):
        apis = {
            'mp_login': self.cuser.mini_program_login,
            'bind_phone': self.cuser.bind_phone,
            'test_login': self.cuser.test_login,
        }
        return apis
