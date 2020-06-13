from ..control.CIndex import CIndex
from ..extensions.base_resource import Resource


class AIndex(Resource):
    def __init__(self):
        self.index = CIndex()

    def get(self, index):
        apis = {
            'list_mp_banner': self.index.list_mp_banner,
            'list_linkcontent': self.cindex.list_linkcontent,
        }
        return apis

    def post(self, index):
        apis = {
            'set_linkcontent': self.index.set_linkcontent,
            'set_mp_banner': self.index.set_mp_banner
        }
        return apis
