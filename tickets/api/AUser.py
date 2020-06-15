from ..control.CUser import CUser
from ..extensions.base_resource import Resource


class AUser(Resource):
    def __init__(self):
        self.cuser = CUser()

    def get(self, user):
        apis = {
            'get_home': self.cuser.get_home,
            'secret_usid': self.cuser.get_secret_usid,
            'my_wallet': self.cuser.my_wallet,
            'identification': self.cuser.identification,
            'get_admin_list': self.cuser.get_admin_list,  # 获取管理员列表
            'list_user_commison': self.cuser.list_user_commison,  # 销售商列表(后台佣金)
            'list_fans': self.cuser.list_fans,  # 获取某人粉丝列表
        }
        return apis

    def post(self, user):
        apis = {
            'mp_login': self.cuser.mini_program_login,
            'bind_phone': self.cuser.bind_phone,
            'test_login': self.cuser.test_login,
            'update_usinfo': self.cuser.update_usinfo,
            'apply_cash': self.cuser.apply_cash,
            'user_certification': self.cuser.user_certification,
            'admin_login': self.cuser.admin_login,  # 管理员登录
            'add_admin_by_superadmin': self.cuser.add_admin_by_superadmin,  # 添加管理员
            'update_admin': self.cuser.update_admin,  # 更新管理员信息
            'update_admin_password': self.cuser.update_admin_password,  # 修改管理员密码
        }
        return apis
