from ..control.CUser import CUser
from ..extensions.base_resource import Resource


class AUser(Resource):
    def __init__(self):
        self.cuser = CUser()

    def get(self, user):
        apis = {
            'get_home': self.cuser.get_home,
            'secret_usid': self.cuser.get_secret_usid,
        }
        return apis

    def post(self, user):
        apis = {
            'mp_login': self.cuser.mini_program_login,
            'bind_phone': self.cuser.bind_phone,
            'test_login': self.cuser.test_login,
        }
        return apis
