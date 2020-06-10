# -*- coding: utf-8 -*-
import qiniu


class QiniuStorage(object):
    """
    官方SDK文档 https://developer.qiniu.com/kodo/sdk/1242/python
    """

    def __init__(self, access_key, secret_key, bucket_name):
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name

    @property
    def auth(self):
        return qiniu.Auth(self.access_key, self.secret_key)

    def save(self, data, filename=None):
        token = self.auth.upload_token(self.bucket_name, filename)
        return qiniu.put_file(token, filename, data)

    def delete(self, filename):
        bucket = qiniu.BucketManager(self.auth)
        return bucket.delete(self.bucket_name, filename)

    def url_to_storage(self, url, filename):
        auth = qiniu.Auth(self.access_key, self.secret_key)
        bucket = qiniu.BucketManager(auth)
        return bucket.fetch(url, self.bucket_name, filename)

# if __name__ == '__main__':
#     q = QiniuStorage()
#     ret, info = q.save('/home/wiilz/Desktop/JjfxnGdM7jSKIJGrMuvyd702def0-403a-11e9-b2cf-00163e13a3e3.jpeg_3225x2033.jpeg', 'first_picture')
#     print(ret)
