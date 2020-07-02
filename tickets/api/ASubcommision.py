from ..control.CSubcommision import CSubcommision
from ..extensions.base_resource import Resource


class ASubcommision(Resource):
    def __init__(self):
        self.csubcommision = CSubcommision()

    def get(self, subcommision):
        apis = {
            "get_user_team": self.csubcommision.get_user_team,
            "get_subcommision_index": self.csubcommision.get_subcommision_index,
            "get_share_list": self.csubcommision.get_share_list,
            "get_distribute_list": self.csubcommision.get_distribute_list,
            "get_approval_list": self.csubcommision.get_approval_list

        }
        return apis

    def post(self, subcommision):
        apis = {
            "mock_distribute_user": self.csubcommision.mock_distribute_user,

        }
        return apis