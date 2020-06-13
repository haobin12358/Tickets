from ..control.CProduct import CProduct
from ..extensions.base_resource import Resource


class AProduct(Resource):
    def __init__(self):
        self.product = CProduct()

    def get(self, product):
        apis = {
            'list': self.product.list_product,
            'get': self.product.get_product,
            'get_promotion': self.product.get_promotion,
            'list_role': self.product.list_role,
        }
        return apis

    def post(self, product):
        apis = {
            'verify': self.product.product_verified,
            'create': self.product.create_product,
            'update_role': self.product.update_role,
        }
        return apis
